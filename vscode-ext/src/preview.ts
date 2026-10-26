// The preview panel beside the editor: redraws the tracked R script on every
// edit (typed or written to disk by an agent), shows errors in the editor, and
// runs the skill's render + QA for "Export and check".
import { execFile } from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { Size, Worker, findLabfig, findPython, findRscript, renderedFiles } from "./worker";

export const PREVIEW_LANGUAGES = ["r", "python"];

// Only figure scripts are followed when the active editor changes, so opening
// an ordinary Python module does not replace the preview with an error.
function looksLikeFigureScript(doc: vscode.TextDocument): boolean {
  return PREVIEW_LANGUAGES.includes(doc.languageId) && /labstyle|#\s*-+\s*plot\s*-+/.test(doc.getText());
}

export class PreviewPanel {
  static current: PreviewPanel | undefined;

  private doc: vscode.TextDocument;
  private size: Size = null;
  private busy = false;
  private queued = false;
  private timer: NodeJS.Timeout | undefined;
  private watcher: vscode.FileSystemWatcher | undefined;
  private disposables: vscode.Disposable[] = [];

  static show(
    context: vscode.ExtensionContext,
    getWorker: (languageId: string) => Worker,
    diagnostics: vscode.DiagnosticCollection,
    log: vscode.OutputChannel,
    doc: vscode.TextDocument,
  ): void {
    if (PreviewPanel.current) {
      PreviewPanel.current.track(doc);
      PreviewPanel.current.panel.reveal(vscode.ViewColumn.Beside, true);
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "labFigurePreview",
      "Figure preview",
      { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
      { enableScripts: true, retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, "media")] },
    );
    PreviewPanel.current = new PreviewPanel(panel, context, getWorker, diagnostics, log, doc);
  }

  private constructor(
    private panel: vscode.WebviewPanel,
    context: vscode.ExtensionContext,
    private getWorker: (languageId: string) => Worker,
    private diagnostics: vscode.DiagnosticCollection,
    private log: vscode.OutputChannel,
    doc: vscode.TextDocument,
  ) {
    this.doc = doc;
    panel.webview.html = this.html(context);
    panel.onDidDispose(() => this.dispose(), null, this.disposables);
    panel.webview.onDidReceiveMessage((msg) => this.onMessage(msg), null, this.disposables);

    this.disposables.push(
      // typing, and agent edits to an open, unmodified document, both arrive here
      vscode.workspace.onDidChangeTextDocument((e) => {
        if (e.document === this.doc) this.schedule();
      }),
      vscode.window.onDidChangeActiveTextEditor((editor) => {
        const d = editor?.document;
        if (d && d !== this.doc && looksLikeFigureScript(d)) this.track(d);
      }),
    );
    this.track(doc);
  }

  private track(doc: vscode.TextDocument): void {
    if (this.doc !== doc) this.diagnostics.delete(this.doc.uri);
    this.doc = doc;
    // once the editor tab is closed, edits to the file only show up on disk
    this.watcher?.dispose();
    this.watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(path.dirname(doc.fileName), path.basename(doc.fileName)),
    );
    this.watcher.onDidChange(() => {
      if (this.doc.isClosed) this.schedule();
    });
    this.panel.title = `Preview: ${path.basename(doc.fileName)}`;
    this.post({ type: "file", name: path.basename(doc.fileName) });
    this.refresh();
  }

  refresh(): void {
    this.schedule(0);
  }

  private schedule(delay?: number): void {
    const ms = delay ?? vscode.workspace.getConfiguration("labFigure").get<number>("debounceMs", 300);
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => this.render(), ms);
  }

  private cwd(): string {
    const folder = vscode.workspace.getWorkspaceFolder(this.doc.uri);
    return folder ? folder.uri.fsPath : path.dirname(this.doc.fileName);
  }

  // One render at a time; edits made meanwhile collapse into one follow-up render.
  private async render(): Promise<void> {
    if (this.busy) {
      this.queued = true;
      return;
    }
    this.busy = true;
    this.post({ type: "busy" });
    const doc = this.doc;
    try {
      const code = doc.isClosed ? fs.readFileSync(doc.fileName, "utf8") : doc.getText();
      const result = await this.getWorker(doc.languageId).render(doc.fileName, code, this.cwd(), this.size);
      this.showDiagnostic(doc, result.ok ? undefined : result.line, result.error);
      this.post({ type: "result", result });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.log.appendLine(message);
      this.post({ type: "result", result: { ok: false, error: message, section: "worker" } });
    } finally {
      this.busy = false;
      if (this.queued) {
        this.queued = false;
        this.render();
      }
    }
  }

  private showDiagnostic(doc: vscode.TextDocument, line: number | undefined, message?: string): void {
    if (line === undefined || !message || doc.isClosed) {
      this.diagnostics.delete(doc.uri);
      return;
    }
    const range = doc.lineAt(Math.min(Math.max(line - 1, 0), doc.lineCount - 1)).range;
    const d = new vscode.Diagnostic(range, message, vscode.DiagnosticSeverity.Error);
    d.source = "lab-figure";
    this.diagnostics.set(doc.uri, [d]);
  }

  private async onMessage(msg: { type: string; size?: Size; line?: number }): Promise<void> {
    switch (msg.type) {
      case "setSize":
        this.size = msg.size ?? null;
        this.refresh();
        break;
      case "refresh":
        this.refresh();
        break;
      case "clearCache":
        await this.getWorker(this.doc.languageId).reset().catch(() => undefined);
        this.refresh();
        break;
      case "export":
        await this.exportAndCheck();
        break;
      case "goToLine":
        if (msg.line) {
          const shown = vscode.window.visibleTextEditors.find((e) => e.document === this.doc);
          const editor = await vscode.window.showTextDocument(this.doc, shown?.viewColumn ?? vscode.ViewColumn.One);
          const pos = new vscode.Position(msg.line - 1, 0);
          editor.selection = new vscode.Selection(pos, pos);
          editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenter);
        }
        break;
    }
  }

  // Runs the script for real (writes the files) and the QA audits on each PDF.
  async exportAndCheck(): Promise<void> {
    const labfig = findLabfig(vscode.workspace.getConfiguration("labFigure").get<string>("labfigPath", ""));
    if (!labfig) {
      this.post({ type: "export", error: "labfig not found: install the lab-figure skill or set labFigure.labfigPath" });
      return;
    }
    if (this.doc.isDirty) await this.doc.save();
    this.post({ type: "exporting" });
    const cwd = this.cwd();
    const render = await run(labfig, ["render", this.doc.fileName], cwd);
    if (render.code !== 0) {
      this.post({ type: "export", error: render.out.trim() });
      return;
    }
    const files = renderedFiles(render.out);
    const checks = [];
    for (const pdf of files.filter((f) => f.endsWith(".pdf"))) {
      const qa = await run(labfig, ["qa", pdf], cwd);
      const verdicts = [...qa.out.matchAll(/^verdict:\s*(.+)$/gm)].map((m) => m[1].trim());
      checks.push({ pdf, font: verdicts[0] ?? "?", collision: verdicts[1] ?? "?", report: qa.out });
    }
    this.post({ type: "export", files, checks, log: render.out });
  }

  private post(msg: unknown): void {
    this.panel.webview.postMessage(msg);
  }

  private html(context: vscode.ExtensionContext): string {
    const webview = this.panel.webview;
    const media = (f: string) => webview.asWebviewUri(vscode.Uri.joinPath(context.extensionUri, "media", f));
    const nonce = Array.from({ length: 24 }, () => Math.floor(Math.random() * 36).toString(36)).join("");
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource} data:; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="${media("preview.css")}">
<title>Figure preview</title>
</head>
<body>
<header>
  <span id="file"></span>
  <label>Size <select id="size">
    <option value="">template</option>
    <option>single</option><option>wide</option><option>narrow</option><option>bar2</option>
    <option>roc</option><option>roc_multi</option><option>km</option><option>forest</option>
    <option>violin</option><option>auc_bar</option><option>pie</option>
  </select></label>
  <label>Zoom <select id="zoom"><option value="fit">fit</option><option value="1">100%</option><option value="2">200%</option></select></label>
  <button id="refresh" title="Redraw now">Redraw</button>
  <button id="clear" title="Reload the data section on the next redraw">Reload data</button>
  <button id="export" title="Write the files and run the font-size and collision checks">Export and check</button>
</header>
<div id="status">Waiting for the first render…</div>
<div id="error" hidden></div>
<main id="figures"></main>
<section id="stats"></section>
<details id="output-box" hidden><summary>Script output</summary><pre id="output"></pre></details>
<section id="export-result" hidden></section>
<script nonce="${nonce}" src="${media("preview.js")}"></script>
</body>
</html>`;
  }

  dispose(): void {
    PreviewPanel.current = undefined;
    if (this.timer) clearTimeout(this.timer);
    this.watcher?.dispose();
    this.diagnostics.delete(this.doc.uri);
    this.disposables.forEach((d) => d.dispose());
    this.panel.dispose();
  }
}

function run(cmd: string, args: string[], cwd: string): Promise<{ code: number; out: string }> {
  const cfg = vscode.workspace.getConfiguration("labFigure");
  const env = { ...process.env, LABFIG_RSCRIPT: findRscript(cfg.get<string>("rscriptPath", "")), PYTHONUTF8: "1" };
  if (cmd.toLowerCase().endsWith(".py")) {
    args = [cmd, ...args];
    cmd = findPython(cfg.get<string>("pythonPath", ""));
  }
  return new Promise((resolve) => {
    execFile(cmd, args, { cwd, env, windowsHide: true, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
      const code = err ? (typeof err.code === "number" ? err.code : 1) : 0;
      resolve({ code, out: `${stdout}${stderr}` });
    });
  });
}
