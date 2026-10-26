"""Native Windows entry point for inspect, render, qa and doctor."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[2]
RSCRIPT = os.environ.get("LABFIG_RSCRIPT") or str(REPO / ".runtime/R/bin/Rscript.exe")
if not Path(RSCRIPT).exists():
    RSCRIPT = shutil.which("Rscript") or RSCRIPT


def run(args):
    return subprocess.run([str(x) for x in args], env={**os.environ, "PYTHONUTF8": "1"}).returncode


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    args = sys.argv[2:]
    if cmd == "doctor":
        print(f"repo: {REPO}", flush=True)
        rc = run([RSCRIPT, "-e", 'cat(R.version.string, "\\nlabstyle:", as.character(packageVersion("labstyle")), "\\n")'])
        rc2 = run([sys.executable, "-c", 'import pandas,pymupdf,labstyle_py; print("Python, pandas, PyMuPDF, labstyle_py: OK")'])
        return rc or rc2
    if cmd == "inspect":
        return run([sys.executable, "-I", SCRIPTS / "inspect_data.py", *args])
    if cmd == "render" and len(args) == 1:
        suffix = Path(args[0]).suffix.lower()
        if suffix == ".r":
            return run([RSCRIPT, SCRIPTS / "render.R", *args])
        if suffix == ".py":
            return run([sys.executable, SCRIPTS / "render.py", *args])
    if cmd == "qa" and len(args) == 1:
        pdf = Path(args[0])
        print("== font size (min 5 pt)", flush=True)
        font = run([sys.executable, "-I", SCRIPTS / "qa/audit_pdf_text.py", "--min-pt", "5", pdf])
        print("== collisions", flush=True)
        collision = run([sys.executable, "-I", SCRIPTS / "qa/audit_figure_collisions.py", pdf,
                         "--json-out", pdf.with_suffix(".collision-audit.json")])
        return collision or font
    print("usage: labfig.py doctor | inspect <table> | render <script.R|script.py> | qa <figure.pdf>")
    return 2


if __name__ == "__main__":
    sys.exit(main())
