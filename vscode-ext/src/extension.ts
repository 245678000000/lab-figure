import * as vscode from "vscode";
import { RWorker, findRscript } from "./worker";
import { PreviewPanel } from "./preview";

let worker: RWorker | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const log = vscode.window.createOutputChannel("Lab Figure");
  const diagnostics = vscode.languages.createDiagnosticCollection("lab-figure");
  context.subscriptions.push(log, diagnostics);

  const getWorker = (): RWorker => {
    if (!worker) {
      const cfg = vscode.workspace.getConfiguration("labFigure");
      const rscript = findRscript(cfg.get<string>("rscriptPath", ""));
      worker = new RWorker(rscript, cfg.get<number>("renderTimeoutSeconds", 120) * 1000);
      worker.on("log", (line: string) => log.appendLine(line));
      log.appendLine(`starting R worker with ${rscript}`);
    }
    return worker;
  };

  context.subscriptions.push(
    vscode.commands.registerCommand("labFigure.openPreview", (uri?: vscode.Uri) => {
      const doc = uri
        ? vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString())
        : vscode.window.activeTextEditor?.document;
      if (!doc || doc.languageId !== "r") {
        vscode.window.showInformationMessage("Open an R figure script first.");
        return;
      }
      PreviewPanel.show(context, getWorker, diagnostics, log, doc);
    }),
    vscode.commands.registerCommand("labFigure.exportAndCheck", () => PreviewPanel.current?.exportAndCheck()),
    vscode.commands.registerCommand("labFigure.restartWorker", () => {
      worker?.restart();
      PreviewPanel.current?.refresh();
    }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("labFigure.rscriptPath") || e.affectsConfiguration("labFigure.renderTimeoutSeconds")) {
        worker?.dispose();
        worker = undefined;
      }
    }),
  );
}

export function deactivate(): void {
  worker?.dispose();
  worker = undefined;
}
