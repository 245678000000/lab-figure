// Long-running R process running labstyle::serve(): one JSON request per line
// on stdin, one JSON response per line on stdout (see labstyle/R/serve.R).
import { ChildProcess, spawn } from "child_process";
import { EventEmitter } from "events";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

export interface Figure {
  name: string;
  width: number;
  height: number;
  svg: string;
  stats?: Record<string, unknown>[] | null;
}

export interface RenderResult {
  id?: number;
  ok: boolean;
  figures?: Figure[];
  cached?: boolean;
  ms?: number;
  output?: string;
  warnings?: string[];
  error?: string;
  line?: number;
  section?: string;
}

export type Size = string | [number, number] | null;

interface Pending {
  resolve: (r: RenderResult) => void;
  reject: (e: Error) => void;
  timer: NodeJS.Timeout;
}

const RSCRIPT_LOCATIONS = [
  "/usr/local/bin/Rscript",
  "/opt/homebrew/bin/Rscript",
  "/Library/Frameworks/R.framework/Resources/bin/Rscript",
];

// Editors started from the Dock do not get the shell PATH, so look in the
// usual install locations too.
export function findRscript(configured: string): string {
  if (configured) return configured;
  for (const dir of (process.env.PATH ?? "").split(path.delimiter)) {
    const candidate = path.join(dir, process.platform === "win32" ? "Rscript.exe" : "Rscript");
    if (dir && fs.existsSync(candidate)) return candidate;
  }
  return RSCRIPT_LOCATIONS.find((p) => fs.existsSync(p)) ?? "Rscript";
}

// The lab-figure Python env (outside iCloud, see the repo README), else PATH.
export function findPython(configured: string): string {
  if (configured) return configured;
  const venv = path.join(os.homedir(), ".local/share/lab-figure/venv/bin/python");
  return fs.existsSync(venv) ? venv : process.platform === "win32" ? "python" : "python3";
}

export function findLabfig(configured: string): string | undefined {
  if (configured) return configured;
  const home = os.homedir();
  return [
    path.join(home, ".agents/skills/lab-figure/scripts/labfig"),
    path.join(home, ".claude/skills/lab-figure/scripts/labfig"),
  ].find((p) => fs.existsSync(p));
}

// Files written by `labfig render`: the indented lines after its "OK in" line
// (the script's own printed output, which can also be indented, comes before it).
export function renderedFiles(output: string): string[] {
  const lines = output.split("\n");
  const ok = lines.findIndex((l) => l.startsWith("OK in "));
  if (ok < 0) return [];
  return lines.slice(ok + 1).filter((l) => l.startsWith("  ")).map((l) => l.trim());
}

// A preview worker process: labstyle::serve() in R or labstyle_py.serve in
// Python, both speaking the same protocol.
export class Worker extends EventEmitter {
  private proc?: ChildProcess;
  private buffer = "";
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private starting?: Promise<void>;

  constructor(private command: string, private args: string[], private timeoutMs = 120_000) {
    super();
  }

  private start(): Promise<void> {
    if (this.starting) return this.starting;
    this.starting = new Promise((resolve, reject) => {
      const proc = spawn(this.command, this.args, {
        stdio: ["pipe", "pipe", "pipe"], windowsHide: true,
        env: { ...process.env, PYTHONUTF8: "1" },
      });
      this.proc = proc;
      this.buffer = "";
      let ready = false;
      proc.stdout!.setEncoding("utf8");
      proc.stdout!.on("data", (chunk: string) => {
        this.buffer += chunk;
        let nl: number;
        while ((nl = this.buffer.indexOf("\n")) >= 0) {
          const line = this.buffer.slice(0, nl).trim();
          this.buffer = this.buffer.slice(nl + 1);
          if (!line) continue;
          let msg: RenderResult & { event?: string };
          try {
            msg = JSON.parse(line);
          } catch {
            this.emit("log", `worker: ${line}`);
            continue;
          }
          if (msg.event === "ready") {
            ready = true;
            this.emit("log", `worker ready (${JSON.stringify(msg)})`);
            resolve();
          } else if (msg.id !== undefined && this.pending.has(msg.id)) {
            const p = this.pending.get(msg.id)!;
            this.pending.delete(msg.id);
            clearTimeout(p.timer);
            p.resolve(msg);
          }
        }
      });
      proc.stderr!.setEncoding("utf8");
      proc.stderr!.on("data", (chunk: string) => this.emit("log", chunk.trimEnd()));
      // a restarted worker's late events must not touch its replacement
      proc.on("error", (err) => {
        if (this.proc === proc) this.cleanup(new Error(`could not start ${this.command}: ${err.message}`));
        if (!ready) reject(err);
      });
      proc.on("exit", (code, signal) => {
        this.emit("log", `worker exited (${signal ?? code})`);
        if (this.proc === proc) this.cleanup(new Error(`preview worker exited (${signal ?? code})`));
        if (!ready) reject(new Error(`preview worker exited before it was ready (${signal ?? code})`));
      });
    });
    return this.starting;
  }

  private cleanup(err: Error): void {
    for (const p of this.pending.values()) {
      clearTimeout(p.timer);
      p.reject(err);
    }
    this.pending.clear();
    this.proc = undefined;
    this.starting = undefined;
  }

  private async request(msg: Record<string, unknown>): Promise<RenderResult> {
    await this.start();
    const proc = this.proc;
    if (!proc?.stdin) throw new Error("preview worker is not running");
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`no answer after ${this.timeoutMs / 1000} s; the preview worker was restarted`));
        this.restart();
      }, this.timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      proc.stdin!.write(JSON.stringify({ ...msg, id }) + "\n");
    });
  }

  render(file: string, code: string, cwd: string, size: Size = null): Promise<RenderResult> {
    // R's parse(text=...) rejects carriage returns left by Windows CRLF files.
    return this.request({ cmd: "render", path: file, code: code.replace(/\r\n?/g, "\n"), cwd, size });
  }

  reset(): Promise<RenderResult> {
    return this.request({ cmd: "reset" });
  }

  restart(): void {
    const proc = this.proc;
    this.cleanup(new Error("preview worker restarted"));
    proc?.kill();
  }

  dispose(): void {
    this.restart();
    this.removeAllListeners();
  }
}

export class RWorker extends Worker {
  constructor(rscript: string, timeoutMs?: number) {
    super(rscript, ["-e", "labstyle::serve()"], timeoutMs);
  }
}

export class PyWorker extends Worker {
  constructor(python: string, timeoutMs?: number) {
    super(python, ["-u", "-m", "labstyle_py.serve"], timeoutMs);
  }
}
