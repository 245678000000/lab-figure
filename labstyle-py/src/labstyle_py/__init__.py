"""Python port of the labstyle R package: house style, save_fig() and the
ROC / box / rate-bar templates, with statistics computed as in R."""

from .save import lab_stats, save_fig
from .stats import format_p_value, p_to_symbol
from .style import lab_colors, lab_sizes
from .templates import lab_box, lab_rate_bar, lab_roc
from .theme import lab_rc, options

__version__ = "0.1.0"

__all__ = [
    "format_p_value", "lab_box", "lab_colors", "lab_rate_bar", "lab_rc", "lab_roc",
    "lab_sizes", "lab_stats", "options", "p_to_symbol", "save_fig",
]
