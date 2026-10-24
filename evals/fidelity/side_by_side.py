"""Render original vs template PDFs to one PNG per plot, side by side.

    .venv/bin/python -I evals/fidelity/side_by_side.py [out_dir]
"""

import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

DPI = 200


def render(pdf: Path) -> Image.Image:
    page = pymupdf.open(pdf)[0]
    pix = page.get_pixmap(dpi=DPI, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "evals/fidelity/out")
    font = ImageFont.load_default(size=28)
    made = []
    for orig_pdf in sorted((out / "original").glob("*.pdf")):
        tpl_pdf = out / "template" / orig_pdf.name
        if not tpl_pdf.exists():
            print(f"skip {orig_pdf.name}: no template output")
            continue
        a, b = render(orig_pdf), render(tpl_pdf)
        gap, head = 40, 50
        canvas = Image.new("RGB", (a.width + b.width + gap, max(a.height, b.height) + head), "white")
        canvas.paste(a, (0, head))
        canvas.paste(b, (a.width + gap, head))
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 10), "original (utils.R)", fill="black", font=font)
        draw.text((a.width + gap + 10, 10), "labstyle template", fill="black", font=font)
        dest = out / f"compare_{orig_pdf.stem}.png"
        canvas.save(dest)
        made.append(dest)
    for m in made:
        print(m)
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
