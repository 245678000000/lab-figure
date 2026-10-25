// Drives the real R worker through the compiled client (npm test).
import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { RWorker, PyWorker, findRscript, findPython, renderedFiles } = require("../out/worker.js");

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const example = (name) => path.join(repo, "examples", `${name}.R`);
const read = (name) => readFileSync(example(name), "utf8");

let worker;
let py;
before(() => {
  worker = new RWorker(findRscript(""), 60_000);
  py = new PyWorker(findPython(""), 60_000);
});
after(() => {
  worker.dispose();
  py.dispose();
});

const pyExample = (name) => path.join(repo, "examples", "py", `${name}.py`);
const readPy = (name) => readFileSync(pyExample(name), "utf8");

test("python: renders a labstyle_py script, then from the cache", async () => {
  const first = await py.render(pyExample("roc"), readPy("roc"), repo);
  assert.equal(first.ok, true, first.error);
  assert.equal(first.cached, false);
  assert.deepEqual([first.figures[0].width, first.figures[0].height], [2.7, 2.2]);
  assert.match(first.figures[0].svg, /<svg[\s\S]*AUC = 0\.74/);
  assert.equal(first.figures[0].stats[0].n_pos, 6);
  const plotEdit = readPy("roc").replace('positive="R")', 'positive="R", show_n=False)');
  const second = await py.render(pyExample("roc"), plotEdit, repo, "wide");
  assert.equal(second.ok, true, second.error);
  assert.equal(second.cached, true);
  assert.equal(second.figures[0].width, 4.6);
  assert.doesNotMatch(second.figures[0].svg, /n: R 6/);
});

test("python: an error reports its script line", async () => {
  const code = readPy("box").replace('y="B_cells"', 'y="Nope"');
  const r = await py.render(pyExample("box"), code, repo);
  assert.equal(r.ok, false);
  assert.equal(r.section, "plot");
  assert.match(r.error, /column 'Nope' not found/);
  assert.equal(r.line, code.split("\n").findIndex((l) => l.includes('"Nope"')) + 1);
});

test("python: in-place edits in the plot section do not leak into the cache", async () => {
  const code = [
    "import pandas as pd",
    "from labstyle_py import lab_box",
    'd = pd.DataFrame({"g": ["a", "a", "b", "b"], "v": [1.0, 2.0, 3.0, 4.0]})',
    "# ---- plot ----",
    'd.loc[0, "v"] += 100',
    'print("first value", d.loc[0, "v"])',
    'fig = lab_box(d, "g", "v")',
  ].join("\n");
  const file = path.join(repo, "unsaved_copy_test.py");
  const r1 = await py.render(file, code, repo);
  const r2 = await py.render(file, code, repo);
  assert.equal(r2.cached, true);
  assert.match(r1.output, /first value 101\.0/);
  assert.match(r2.output, /first value 101\.0/);
});

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
