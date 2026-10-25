"""save_fig() and the hand-over to the live preview worker."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl

from .style import DPI, resolve_size
from .theme import lab_rc


class _Preview:
    active = False
    figures: list = []


preview = _Preview()


def lab_stats(fig):
    """Statistics a template computed (AUC, p values, ...), as a DataFrame."""
    return getattr(fig, "lab_stats", None)


def save_fig(fig, name: str, size=None, dir: str = "figures", formats=("pdf", "png"),
             dpi: int = DPI, data=None) -> list[str]:
    """Export a figure as PDF + PNG at a house size preset.

    `size` is a preset name (see lab_sizes()) or (width, height) in inches;
    None uses the template's own preset. `data` (a DataFrame) is written next
    to the figure as <name>_source_data.csv.
    """
    wh = resolve_size(size or getattr(fig, "lab_size", None) or "single")
    if preview.active:
        # live preview (serve): hand the figure over instead of writing files
        preview.figures.append({"figure": fig, "name": name, "size": wh})
        return []
    out = Path(dir)
    out.mkdir(parents=True, exist_ok=True)
    suffix = Path(name).suffix
    base = out / (name[: -len(suffix)] if suffix in {".pdf", ".png", ".svg"} else name)
    fig.set_size_inches(*wh)
    paths = []
    with mpl.rc_context(lab_rc()):
        for fmt in formats:
            path = f"{base}.{fmt}"
            fig.savefig(path, dpi=dpi if fmt == "png" else "figure")
            paths.append(path)
    if data is not None:
        path = f"{base}_source_data.csv"
        data.to_csv(path, index=False)
        paths.append(path)
    print(f"saved {wh[0]:.2f} x {wh[1]:.2f} in: {', '.join(paths)}")
    return paths
