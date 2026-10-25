"""House theme as matplotlib rcParams: open axes, no grid, black axis lines and
text, 12 pt base size with 0.8x tick labels (ggplot2 theme_classic sizes)."""

from __future__ import annotations

import functools

import matplotlib as mpl
from matplotlib.figure import Figure

from .style import AXIS_LINE_PT, BASE_SIZE, resolve_size

options = {"boxed": False}  # options["boxed"] = True: panel border, like R's labstyle.boxed


def lab_rc(base_size: float = BASE_SIZE, boxed: bool | None = None) -> dict:
    boxed = options["boxed"] if boxed is None else boxed
    return {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": base_size,
        "axes.labelsize": base_size,
        "axes.titlesize": base_size,
        "xtick.labelsize": base_size * 0.8,
        "ytick.labelsize": base_size * 0.8,
        "legend.fontsize": base_size * 0.8,
        "legend.frameon": False,
        "axes.grid": False,
        "axes.spines.top": boxed,
        "axes.spines.right": boxed,
        "axes.edgecolor": "black",
        "axes.labelcolor": "black",
        "axes.linewidth": AXIS_LINE_PT,
        "axes.facecolor": "white",
        "text.color": "black",
        "xtick.color": "black",
        "ytick.color": "black",
        "xtick.major.width": AXIS_LINE_PT,
        "ytick.major.width": AXIS_LINE_PT,
        # ggplot2 tick length 2.75 pt (1/72.27 in) in matplotlib points (1/72 in)
        "xtick.major.size": 2.75 * 72 / 72.27,
        "ytick.major.size": 2.75 * 72 / 72.27,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "pdf.fonttype": 42,  # embed TrueType: text stays editable
        "ps.fonttype": 42,
        "svg.fonttype": "none",
    }


def with_lab_rc(func):
    """Run a template inside the house rcParams (fonts, spines and ticks are
    fixed when the figure is built)."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with mpl.rc_context(lab_rc()):
            return func(*args, **kwargs)

    return wrapper


def new_axes(ax, size):
    """The given Axes, or a new figure at `size` with one Axes."""
    if ax is not None:
        return ax.figure, ax
    fig = Figure(figsize=resolve_size(size), layout="constrained")
    return fig, fig.add_subplot()


def style_axes(ax, x_angle: float = 0) -> None:
    """Tick labels rotated by x_angle (45 for long group names)."""
    if x_angle:
        for label in ax.get_xticklabels():
            label.set_rotation(x_angle)
            label.set_horizontalalignment("right" if x_angle != 90 else "center")
            label.set_rotation_mode("anchor")
