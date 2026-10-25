// Webview side of the figure preview. Receives render results from the
// extension and posts back toolbar actions.
(function () {
  const vscode = acquireVsCodeApi();
  const $ = (id) => document.getElementById(id);
  const state = vscode.getState() || { size: "", zoom: "fit" };

  $("size").value = state.size;
  $("zoom").value = state.zoom;
  if (state.size) vscode.postMessage({ type: "setSize", size: state.size });

  $("size").addEventListener("change", () => {
    state.size = $("size").value;
    vscode.setState(state);
    vscode.postMessage({ type: "setSize", size: state.size || null });
  });
  $("zoom").addEventListener("change", () => {
    state.zoom = $("zoom").value;
    vscode.setState(state);
    applyZoom();
  });
  $("refresh").addEventListener("click", () => vscode.postMessage({ type: "refresh" }));
  $("clear").addEventListener("click", () => vscode.postMessage({ type: "clearCache" }));
  $("export").addEventListener("click", () => vscode.postMessage({ type: "export" }));

  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (msg.type === "file") $("file").textContent = msg.name;
    else if (msg.type === "busy") $("status").classList.add("busy");
    else if (msg.type === "result") showResult(msg.result);
    else if (msg.type === "exporting") showExporting();
    else if (msg.type === "export") showExport(msg);
  });

  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function showResult(r) {
    const status = $("status");
    status.classList.remove("busy");
    const error = $("error");
    if (!r.ok) {
      error.hidden = false;
      error.replaceChildren();
      const where = { parse: "Syntax error", data: "Error in the data section",
                      plot: "Error in the plot section", draw: "Error while drawing",
                      worker: "Preview worker problem" }[r.section] || "Error";
      error.append(el("strong", {}, where));
      if (r.line) {
        const link = el("a", { href: "#" }, ` (line ${r.line})`);
        link.addEventListener("click", (e) => {
          e.preventDefault();
          vscode.postMessage({ type: "goToLine", line: r.line });
        });
        error.append(link);
      }
      error.append(el("pre", {}, r.error || ""));
      document.querySelectorAll(".figure").forEach((f) => f.classList.add("stale"));
      status.textContent = $("figures").children.length ? "Showing the last figure that worked." : "";
    } else {
      error.hidden = true;
      status.textContent = `${r.ms} ms · data ${r.cached ? "from cache" : "loaded"}` +
        (r.warnings && r.warnings.length ? ` · ${r.warnings.length} warning(s)` : "");
      showFigures(r.figures || []);
    }
    showWarnings(r.warnings || []);
    const out = (r.output || "").trim();
    $("output-box").hidden = !out;
    $("output").textContent = out;
  }

  function showFigures(figures) {
    const box = $("figures");
    box.replaceChildren();
    const stats = $("stats");
    stats.replaceChildren();
    for (const f of figures) {
      const card = el("div", { class: "figure" });
      card.append(el("div", { class: "caption" },
        `${f.name} · ${f.width.toFixed(2)} × ${f.height.toFixed(2)} in`));
      const canvas = el("div", { class: "canvas" });
      canvas.innerHTML = f.svg.replace(/^<\?xml[^>]*>\s*/, "");
      const svg = canvas.querySelector("svg");
      if (svg) {
        svg.dataset.w = f.width;
        svg.dataset.h = f.height;
      }
      card.append(canvas);
      box.append(card);
      if (Array.isArray(f.stats) && f.stats.length) stats.append(statsTable(f.name, f.stats));
    }
    applyZoom();
  }

  function applyZoom() {
    document.querySelectorAll(".figure svg").forEach((svg) => {
      if (state.zoom === "fit") {
        svg.style.width = "100%";
        svg.style.height = "auto";
        svg.style.maxHeight = "70vh";
      } else {
        const k = Number(state.zoom);
        svg.style.width = `${svg.dataset.w * 72 * k}pt`;
        svg.style.height = `${svg.dataset.h * 72 * k}pt`;
        svg.style.maxHeight = "none";
      }
    });
  }

  function fmt(v) {
    if (typeof v !== "number") return v === null || v === undefined ? "" : String(v);
    if (Number.isInteger(v)) return String(v);
    return Math.abs(v) < 0.001 ? v.toExponential(2) : String(Number(v.toPrecision(3)));
  }

  function statsTable(name, rows) {
    const wrap = el("div", { class: "stats" });
    wrap.append(el("div", { class: "caption" }, `lab_stats(${name})`));
    const table = el("table");
    const keys = Object.keys(rows[0]);
    const head = el("tr");
    keys.forEach((k) => head.append(el("th", {}, k)));
    table.append(head);
    rows.slice(0, 50).forEach((row) => {
      const tr = el("tr");
      keys.forEach((k) => tr.append(el("td", {}, fmt(row[k]))));
      table.append(tr);
    });
    wrap.append(table);
    if (rows.length > 50) wrap.append(el("div", { class: "caption" }, `… ${rows.length - 50} more rows`));
    return wrap;
  }

  function showWarnings(warnings) {
    let box = $("warnings");
    if (!box) {
      box = el("ul", { id: "warnings" });
      $("status").after(box);
    }
    box.replaceChildren(...warnings.map((w) => el("li", {}, w)));
    box.hidden = !warnings.length;
  }

  function showExporting() {
    const box = $("export-result");
    box.hidden = false;
    box.replaceChildren(el("p", {}, "Writing the files and running the checks…"));
  }

  function showExport(msg) {
    const box = $("export-result");
    box.hidden = false;
    box.replaceChildren(el("h3", {}, "Export and check"));
    if (msg.error) {
      box.append(el("pre", { class: "bad" }, msg.error));
      return;
    }
    const files = el("ul");
    (msg.files || []).forEach((f) => files.append(el("li", {}, f)));
    box.append(el("p", {}, "Written:"), files);
    if ((msg.checks || []).length) {
      const table = el("table");
      const head = el("tr");
      ["PDF", "Font size", "Collisions"].forEach((h) => head.append(el("th", {}, h)));
      table.append(head);
      msg.checks.forEach((c) => {
        const tr = el("tr");
        tr.append(el("td", {}, c.pdf));
        [c.font, c.collision].forEach((v) => tr.append(el("td", { class: v === "PASS" ? "good" : "bad" }, v)));
        table.append(tr);
      });
      box.append(table);
      const details = el("details");
      details.append(el("summary", {}, "Check reports"));
      details.append(el("pre", {}, msg.checks.map((c) => c.report).join("\n")));
      box.append(details);
    }
  }
})();
