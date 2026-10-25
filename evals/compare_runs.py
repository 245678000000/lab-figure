"""Old vs new figure for each eval task, side by side at the same physical scale.

    .venv/bin/python -I evals/compare_runs.py      (run from the repo root)

Writes evals/runs/compare_<task>.png.
"""

import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

RUNS = Path(__file__).resolve().parent / "runs"
DPI = 150


def render(pdf: Path) -> Image.Image:
    pix = pymupdf.open(pdf)[0].get_pixmap(dpi=DPI, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def main() -> int:
    font = ImageFont.load_default(size=22)
    for task_dir in sorted(p for p in RUNS.iterdir() if p.is_dir()):
        pdfs = [task_dir / arm / "figure.pdf" for arm in ("old", "new")]
        if not all(p.exists() for p in pdfs):
            continue
        a, b = (render(p) for p in pdfs)
        gap, head = 50, 40
        canvas = Image.new("RGB", (a.width + b.width + gap, max(a.height, b.height) + head), "white")
        canvas.paste(a, (0, head))
        canvas.paste(b, (a.width + gap, head))
        draw = ImageDraw.Draw(canvas)
        draw.text((6, 8), "OLD", fill="black", font=font)
        draw.text((a.width + gap + 6, 8), "NEW", fill="black", font=font)
        dest = RUNS / f"compare_{task_dir.name}.png"
        canvas.save(dest)
        print(dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
