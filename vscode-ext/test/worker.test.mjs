// Drives the real R worker through the compiled client (npm test).
import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { RWorker, findRscript, renderedFiles } = require("../out/worker.js");

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const example = (name) => path.join(repo, "examples", `${name}.R`);
const read = (name) => readFileSync(example(name), "utf8");

let worker;
before(() => {
  worker = new RWorker(findRscript(""), 60_000);
});
after(() => worker.dispose());

test("renders a template script to SVG with its stats", async () => {
  const r = await worker.render(example("roc"), read("roc"), repo);
  assert.equal(r.ok, true, r.error);
  assert.equal(r.figures.length, 1);
  const fig = r.figures[0];
  assert.equal(fig.name, "roc");
  assert.deepEqual([fig.width, fig.height], [2.7, 2.2]);
  assert.match(fig.svg, /<svg[\s\S]*AUC = 0\.74/);
  assert.equal(fig.stats[0].n_pos, 6);
  assert.match(r.output, /predictor\s+auc/); // lab_stats(p) printed by the script
});

test("data section is cached until it changes", async () => {
  const code = read("box");
  await worker.render(example("box"), code, repo);
  const plotEdit = code.replace('ylab = "B cells (%)"', 'ylab = "B cell share (%)"');
  const r1 = await worker.render(example("box"), plotEdit, repo);
  assert.equal(r1.cached, true);
  assert.match(r1.figures[0].svg, /B cell share/);
  const dataEdit = code.replace('c("CR", "PR")', 'c("CR", "PR", "SD")');
  const r2 = await worker.render(example("box"), dataEdit, repo);
  assert.equal(r2.cached, false);
});

test("an error reports its script line and section", async () => {
  const code = read("roc").replace('outcome = "Response"', 'outcome = "Nope"');
  const r = await worker.render(example("roc"), code, repo);
  assert.equal(r.ok, false);
  assert.equal(r.section, "plot");
  assert.match(r.error, /column 'Nope' not found/);
  const line = code.split("\n").findIndex((l) => l.includes('"Nope"')) + 1;
  assert.equal(r.line, line);
});

test("a syntax error reports its line", async () => {
  const code = read("roc").replace("positive = \"R\")", "positive = \"R\"");
  const r = await worker.render(example("roc"), code, repo);
  assert.equal(r.ok, false);
  assert.equal(r.section, "parse");
  assert.ok(r.line > 0);
});

test("size override, composite KM plot, and no-save_fig scripts", async () => {
  const wide = await worker.render(example("km"), read("km"), repo, "wide");
  assert.equal(wide.ok, true, wide.error);
  assert.deepEqual([wide.figures[0].width, wide.figures[0].height], [4.6, 2.7]);
  assert.match(wide.figures[0].svg, /Number at risk/);

  const bare = 'library(labstyle)\n# ---- plot ----\np <- lab_pie(mtcars, "cyl")\n';
  const r = await worker.render(path.join(repo, "unsaved.R"), bare, repo, [3, 2]);
  assert.equal(r.ok, true, r.error);
  assert.equal(r.figures[0].name, "p");
  assert.deepEqual([r.figures[0].width, r.figures[0].height], [3, 2]);
});

test("export lists only the files labfig render wrote", () => {
  const out = [
    "saved 3.30 x 3.00 in: examples/out/km.pdf, examples/out/km.png",
    "         hr     lower     upper          p test reference cutoff  n",
    "1 0.3904898 0.1755338 0.8686777 0.02116313  cox       Low   2.51 34",
    "  n_by_group",
    "OK in 0.7s",
    "  examples/out/km.pdf",
    "  examples/out/km.png",
  ].join("\n");
  assert.deepEqual(renderedFiles(out), ["examples/out/km.pdf", "examples/out/km.png"]);
  assert.deepEqual(renderedFiles("ERROR (line 6): column 'x' not found"), []);
});

test("restart gives a fresh worker that still renders", async () => {
  worker.restart();
  const r = await worker.render(example("pie"), read("pie"), repo);
  assert.equal(r.ok, true, r.error);
  assert.equal(r.cached, false);
});
