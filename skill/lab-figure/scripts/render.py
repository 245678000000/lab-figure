"""Run a Python figure script; report outputs, timing, and the script line of
any error. Usage: python render.py figures/roc.py   (same output as render.R)"""

import os
import runpy
import sys
import time
import traceback
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python render.py <figure.py>", file=sys.stderr)
        return 2
    script = str(Path(sys.argv[1]).resolve())
    sys.path.insert(0, str(Path(script).parent))  # as `python script.py` does
    started = time.time()
    try:
        runpy.run_path(script, run_name="__main__")
    except SyntaxError as exc:
        print(f"ERROR (line {exc.lineno}): SyntaxError: {exc.msg}")
        return 1
    except Exception as exc:  # noqa: BLE001 - report every script error with its line
        frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == script]
        where = f" (line {frames[-1].lineno})" if frames else ""
        print(f"ERROR{where}: {type(exc).__name__}: {exc}")
        return 1

    outputs = []
    for root, dirs, files in os.walk("."):  # does not follow links (.venv is one)
        dirs[:] = [d for d in dirs if d not in {".venv", "node_modules", ".git"}]
        for name in files:
            path = os.path.join(root, name)
            if Path(name).suffix in {".pdf", ".png", ".svg", ".csv"} and os.path.getmtime(path) >= started:
                outputs.append(os.path.relpath(path))
    print(f"OK in {time.time() - started:.1f}s")
    for path in sorted(outputs):
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
