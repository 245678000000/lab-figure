import * as vscode from "vscode";
import { PyWorker, RWorker, Worker, findPython, findRscript } from "./worker";
import { PREVIEW_LANGUAGES, PreviewPanel } from "./preview";

const workers = new Map<string, Worker>();

export function activate(context: vscode.ExtensionContext): void {
  const log = vscode.window.createOutputChannel("Lab Figure");
  const diagnostics = vscode.languages.createDiagnosticCollection("lab-figure");
  context.subscriptions.push(log, diagnostics);

  // one worker per language, started on the first preview of that language
  const getWorker = (languageId: string): Worker => {
    let worker = workers.get(languageId);
    if (!worker) {
      const cfg = vscode.workspace.getConfiguration("labFigure");
      const timeout = cfg.get<number>("renderTimeoutSeconds", 120) * 1000;
      if (languageId === "python") {
        const python = findPython(cfg.get<string>("pythonPath", ""));
        worker = new PyWorker(python, timeout);
        log.appendLine(`starting Python worker with ${python}`);
      } else {
        const rscript = findRscript(cfg.get<string>("rscriptPath", ""));
        worker = new RWorker(rscript, timeout);
        log.appendLine(`starting R worker with ${rscript}`);
      }
      worker.on("log", (line: string) => log.appendLine(line));
      workers.set(languageId, worker);
    }
    return worker;
  };

  context.subscriptions.push(
    vscode.commands.registerCommand("labFigure.openPreview", (uri?: vscode.Uri) => {
      const doc = uri
        ? vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString())
        : vscode.window.activeTextEditor?.document;
      if (!doc || !PREVIEW_LANGUAGES.includes(doc.languageId)) {
        vscode.window.showInformationMessage("Open an R or Python figure script first.");
        return;
      }
      PreviewPanel.show(context, getWorker, diagnostics, log, doc);
    }),
    vscode.commands.registerCommand("labFigure.exportAndCheck", () => PreviewPanel.current?.exportAndCheck()),
    vscode.commands.registerCommand("labFigure.restartWorker", () => {
      workers.forEach((w) => w.restart());
      PreviewPanel.current?.refresh();
    }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (["rscriptPath", "pythonPath", "renderTimeoutSeconds"].some((k) => e.affectsConfiguration(`labFigure.${k}`))) {
        workers.forEach((w) => w.dispose());
        workers.clear();
      }
    }),
  );
}

export function deactivate(): void {
  workers.forEach((w) => w.dispose());
  workers.clear();
}
