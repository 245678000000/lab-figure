"""Score every eval run's figure.pdf against the house style and the QA audits.

    .venv/bin/python -I evals/score_runs.py      (run from the repo root)

Reads evals/runs/<task>/<arm>/ and writes evals/runs/scores.json. Statistics
correctness is checked by hand against evals/reference.json (the numbers sit
in figure text that differs between runs).
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pymupdf

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "evals" / "runs"
QA = REPO / "skill" / "lab-figure" / "scripts" / "qa"
PY = sys.executable

NAVY, RED = (0x00, 0x30, 0x5D), (0x9C, 0x19, 0x15)
# house size presets per task (inches); forest/heatmap follow the template's own formula
EXPECTED_SIZE = {
    "1_roc": (2.7, 2.2), "2_km": (3.3, 3.0), "3_forest": (5.5, 2.24),
    "4_box": (1.5, 3.3), "5_rate_bar": (1.425, 2.565), "6_heatmap": (5.25, 4.35),
}
TWO_GROUP = {"2_km", "4_box", "5_rate_bar"}


def to_rgb(c):
    return tuple(round(v * 255) for v in c[:3]) if c else None


def near(a, b, tol=28):
    return a is not None and all(abs(x - y) <= tol for x, y in zip(a, b))


def code_lines(out: Path) -> int:
    n = 0
    for f in list(out.glob("*.R")) + list(out.glob("*.py")):
        for line in f.read_text(errors="ignore").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                n += 1
    return n


def verdict(cmd: list[str]) -> str:
    run = subprocess.run(cmd, capture_output=True, text=True)
    m = re.search(r"verdict:\s*([A-Z ]+)", run.stdout + run.stderr)
    return m.group(1).strip() if m else f"exit {run.returncode}"


def score(task: str, arm: str, out: Path) -> dict:
    pdf = out / "figure.pdf"
    row = {"task": task, "arm": arm, "code_lines": code_lines(out)}
    if not pdf.exists():
        row["error"] = "no figure.pdf"
        return row
    doc = pymupdf.open(pdf)
    page = doc[0]
    w, h = page.rect.width / 72, page.rect.height / 72
    row["pages"] = len(doc)
    row["size_in"] = [round(w, 2), round(h, 2)]
    ew, eh = EXPECTED_SIZE[task]
    row["size_ok"] = abs(w - ew) / ew <= 0.15 and abs(h - eh) / eh <= 0.15

    sizes, fonts = [], set()
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"].strip():
                    sizes.append(span["size"])
                    fonts.add(re.sub(r"^[A-Z]{6}\+", "", span["font"]))
    row["font_pt_min_max"] = [round(min(sizes), 1), round(max(sizes), 1)] if sizes else None
    row["fonts"] = sorted(fonts)
    row["font_ok"] = bool(sizes) and min(sizes) >= 7.5 and all(
        re.search(r"helvetica|arial|nimbus ?sans", f, re.I) for f in fonts)

    colors = set()
    for d in page.get_drawings():
        for key in ("fill", "color"):
            rgb = to_rgb(d.get(key))
            if rgb:
                colors.add(rgb)
    if task in TWO_GROUP:
        row["palette_ok"] = any(near(c, NAVY) for c in colors) and any(near(c, RED) for c in colors)
    elif task == "6_heatmap":
        reds = [c for c in colors if c[0] > c[2] + 60]
        deepest = max(reds, key=lambda c: c[0] - c[1] - c[2], default=None)
        row["palette_ok"] = near(deepest, RED, tol=45)
    else:
        row["palette_ok"] = None  # black curve / boxes: no group colours to check

    row["qa_font"] = verdict([PY, "-I", str(QA / "audit_pdf_text.py"), "--min-pt", "5", str(pdf)])
    row["qa_collision"] = verdict([PY, "-I", str(QA / "audit_figure_collisions.py"), str(pdf)])
    return row


def main() -> int:
    rows = []
    for task_dir in sorted(p for p in RUNS.iterdir() if p.is_dir()):
        for arm in ("old", "new"):
            out = task_dir / arm
            if out.exists():
                rows.append(score(task_dir.name, arm, out))
    (RUNS / "scores.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
