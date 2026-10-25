"""Live-preview worker for the editor extension (python -m labstyle_py.serve).
Same JSON-lines protocol as labstyle::serve() in R:

    {"id": 1, "cmd": "render", "path": "/abs/fig.py", "code": "...", "cwd": "/abs/project",
     "size": null | "wide" | [w, h]}
    {"id": 2, "cmd": "reset"}
    {"id": 3, "cmd": "ping"}

The data section (above "# ---- plot ----") runs only when its text or the
working directory changed; the plot section runs every time, in a copy of the
data namespace (DataFrames and arrays are copied so in-place edits do not leak
into the cache). save_fig() calls are captured and returned as SVG.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import io
import json
import math
import os
import re
import sys
import time
import traceback
import warnings

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from . import __version__  # noqa: E402
from .save import preview  # noqa: E402
from .style import resolve_size  # noqa: E402
from .theme import lab_rc  # noqa: E402

PLOT_MARKER = re.compile(r"^\s*#\s*-+\s*plot\s*-+\s*$")

_cache: dict = {}
_protocol_out = sys.stdout


def _reply(msg: dict) -> None:
    _protocol_out.write(json.dumps(msg, default=_json_default, allow_nan=False) + "\n")
    _protocol_out.flush()


def _json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if math.isnan(value) else float(value)
    return str(value)


def _records(df) -> list | None:
    if not isinstance(df, pd.DataFrame):
        return None
    return json.loads(df.to_json(orient="records"))


class ScriptError(Exception):
    def __init__(self, message: str, line: int | None):
        super().__init__(message)
        self.line = line


def _run(stmts: list[ast.stmt], namespace: dict, path: str) -> None:
    for stmt in stmts:
        code = compile(ast.Module(body=[stmt], type_ignores=[]), path, "exec")
        try:
            exec(code, namespace)
        except Exception as exc:  # noqa: BLE001 - every script error is reported, not raised
            frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == path]
            line = frames[-1].lineno if frames else stmt.lineno
            raise ScriptError(f"{type(exc).__name__}: {exc}", line) from None


def _copy_data(namespace: dict) -> dict:
    out = dict(namespace)
    for key, value in namespace.items():
        if isinstance(value, (pd.DataFrame, pd.Series, np.ndarray)):
            out[key] = value.copy()
        elif isinstance(value, (list, dict, set)):
            out[key] = copy.deepcopy(value)
    return out


def _svg(fig: Figure, size) -> str:
    fig.set_size_inches(*size)
    buf = io.StringIO()
    with matplotlib.rc_context(lab_rc()):
        fig.savefig(buf, format="svg")
    return buf.getvalue()


def render(req: dict) -> dict:
    started = time.perf_counter()
    path = req.get("path") or "<preview>"
    cwd = req.get("cwd") or os.getcwd()
    code = req.get("code") or ""
    output = io.StringIO()
    caught: list[warnings.WarningMessage] = []

    def result(**fields) -> dict:
        fields.setdefault("cached", False)
        fields["ms"] = round((time.perf_counter() - started) * 1000)
        fields["output"] = output.getvalue().strip()
        fields["warnings"] = sorted({str(w.message) for w in caught})
        return fields

    try:
        tree = ast.parse(code, filename=path)
    except SyntaxError as exc:
        return result(ok=False, error=f"SyntaxError: {exc.msg}", line=exc.lineno, section="parse")

    lines = code.split("\n")
    marker = next((i + 1 for i, line in enumerate(lines) if PLOT_MARKER.match(line)), None)
    data_stmts = [s for s in tree.body if marker is not None and s.lineno < marker]
    plot_stmts = [s for s in tree.body if s not in data_stmts]
    data_key = "\n".join([cwd, *lines[: (marker - 1) if marker else 0]])

    old_cwd = os.getcwd()
    os.chdir(cwd)
    script_dir = os.path.dirname(os.path.abspath(path))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)  # as `python script.py` does: helpers next to the script import
    try:
        with contextlib.redirect_stdout(output), warnings.catch_warnings(record=True) as caught_now:
            warnings.simplefilter("always")
            caught = caught_now
            cached = _cache.get("key") == data_key
            if not cached:
                _cache.clear()
                namespace = {"__name__": "__main__", "__file__": path}
                try:
                    _run(data_stmts, namespace, path)
                except ScriptError as exc:
                    return result(ok=False, error=str(exc), line=exc.line, section="data")
                _cache.update(key=data_key, namespace=namespace)

            namespace = _copy_data(_cache["namespace"])
            preview.active, preview.figures = True, []
            try:
                _run(plot_stmts, namespace, path)
            except ScriptError as exc:
                return result(ok=False, error=str(exc), line=exc.line, section="plot", cached=cached)
            figures = list(preview.figures)
            if not figures:
                for name in ("fig", "p"):
                    if isinstance(namespace.get(name), Figure):
                        fig = namespace[name]
                        figures = [{"figure": fig, "name": name,
                                    "size": resolve_size(getattr(fig, "lab_size", None) or "single")}]
                        break
            if not figures:
                return result(ok=False, error="no figure: call save_fig(fig, ...) or assign the figure to `fig`",
                              section="plot", cached=cached)

            out = []
            for f in figures:
                size = resolve_size(req["size"]) if req.get("size") else f["size"]
                try:
                    svg = _svg(f["figure"], size)
                except Exception as exc:  # noqa: BLE001
                    return result(ok=False, error=f"drawing {f['name']}: {exc}", section="draw", cached=cached)
                out.append({"name": f["name"], "width": size[0], "height": size[1], "svg": svg,
                            "stats": _records(getattr(f["figure"], "lab_stats", None))})
            return result(ok=True, figures=out, cached=cached)
    finally:
        preview.active, preview.figures = False, []
        os.chdir(old_cwd)
        pyplot = sys.modules.get("matplotlib.pyplot")
        if pyplot is not None:
            pyplot.close("all")


def main() -> None:
    _reply({"event": "ready", "python": sys.version.split()[0], "labstyle_py": __version__})
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            _reply({"ok": False, "error": "request is not valid JSON"})
            continue
        cmd = req.get("cmd")
        if cmd == "render":
            res = render(req)
        elif cmd == "reset":
            _cache.clear()
            res = {"ok": True}
        elif cmd == "ping":
            res = {"ok": True}
        else:
            res = {"ok": False, "error": f"unknown cmd: {cmd}"}
        res["id"] = req.get("id")
        _reply(res)


if __name__ == "__main__":
    main()
