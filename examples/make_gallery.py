"""Re-render every template example and write thumbnails into the skill.

    .venv/bin/python -I examples/make_gallery.py      (run from the repo root)
"""

import subprocess
import sys
from pathlib import Path

from PIL import Image

TEMPLATES = ["roc", "km", "forest", "box", "violin", "rate_bar", "auc_bar", "cor_heatmap", "pie"]
LONG_SIDE = 520


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    labfig = repo / "skill" / "lab-figure" / "scripts" / "labfig"
    gallery = repo / "skill" / "lab-figure" / "gallery"
    gallery.mkdir(parents=True, exist_ok=True)

    for name in TEMPLATES:
        run = subprocess.run([str(labfig), "render", f"examples/{name}.R"], cwd=repo,
                             capture_output=True, text=True)
        if run.returncode != 0:
            print(f"{name}: render failed\n{run.stdout}{run.stderr}", file=sys.stderr)
            return 1
        img = Image.open(repo / "examples" / "out" / f"{name}.png").convert("RGB")
        img.thumbnail((LONG_SIDE, LONG_SIDE), Image.LANCZOS)
        dest = gallery / f"{name}.png"
        img.save(dest, optimize=True)
        print(f"{dest.relative_to(repo)}  {img.width}x{img.height}  {dest.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
