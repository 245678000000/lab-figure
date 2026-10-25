"""House style values, kept identical to labstyle/R/style.R (tests check it)."""

from __future__ import annotations

MM_TO_PT = 72.27 / 25.4  # ggplot2's .pt: text and line sizes are given in mm

BASE_SIZE = 12

# in-panel statistics text, in mm as in the R templates
TEXT_MM = {"roc": 4, "km": 4, "box": 4, "bar": 3, "forest": 4.6, "heatmap": 3, "small": 3}

COLORS = {
    "binary": ["#00305d", "#9c1915"],
    "categorical": [
        "#1c4f27", "#81144e", "#79831e", "#00305d", "#C0C0C0",
        "#9c1915", "black", "#404040", "#808080", "#D3D3D3",
    ],
    "dataset": [
        "#1c4f27", "#81144e", "#79831e", "#00305d", "#9c1915",
        "black", "grey", "#f58231", "#e6194b", "#3cb44b", "#42d4f4",
    ],
    "clusters": [
        "#DC050C", "#FB8072", "#1965B0", "#7BAFDE", "#882E72", "#B17BA6",
        "#FF7F00", "#FDB462", "#E7298A", "#E78AC3", "#33A02C", "#B2DF8A",
        "#55A1B1", "#8DD3C7", "#A6761D", "#E6AB02", "#7570B3", "#BEAED4",
        "#666666", "#999999", "#aa8282", "#d4b7b7", "#8600bf", "#ba5ce3",
        "#808000", "#aeae5c", "#1e90ff", "#00bfff", "#56ff0d", "#ffff00",
        "#8B3800", "#4E8500", "#D70131", "#E64B35B2", "#4DBBD5B2", "#00A087B2",
        "#3C5488B2", "#F39B7FB2", "#4E8500", "#4C00FFFF", "#000DFFFF", "#0068FFFF",
        "#00C1FFFF", "#00FF24FF", "#42FF00FF", "#A8FF00FF", "#FFF90CFF",
        "#FFE247FF", "#FFDB83FF", "#4a5b67", "#91D1C2B2", "#DC0000B2", "#7E6148B2",
        "#B09C85B2", "#15b2d3", "#236e96", "#ffd700", "#f3872f", "#ff598f",
        "#4B0082", "#00FA9A", "#FFD700", "#9400D3", "#FF4500", "#DA70D6",
        "#8B0000", "#5F9EA0", "#7FFF00", "#6495ED", "#DB7093", "#FF6347",
        "#4682B4", "#FF1493", "#FFDAB9", "#ADFF2F", "#006400", "#00CED1",
        "#800080", "#FF69B4", "#1E90FF", "#B22222", "#8B4513", "#A52A2A",
        "#0000FF", "#00FF7F", "#FFB6C1", "#32CD32", "#808080", "#D2691E",
        "#4169E1", "#DAA520", "#FF4500", "#98FB98", "#CD5C5C", "#2F4F4F",
        "#00008B", "#8A2BE2", "#CD853F", "#20B2AA", "#DC143C",
    ],
    "diverging": ["#00305d", "white", "#9c1915"],
    "accent": ["red"],
}

# width, height in inches
SIZES = {
    "single": (2.3, 2.7),
    "narrow": (1.5, 3.3),
    "bar2": (1.425, 2.565),
    "roc": (2.7, 2.2),
    "roc_multi": (3.2, 3.0),
    "km": (3.3, 3.0),
    "forest": (5.5, 3.4),
    "violin": (3.0, 4.0),
    "auc_bar": (2.0, 3.5),
    "pie": (3.6, 2.4),
    "wide": (4.6, 2.7),
}

DPI = 300

# ggplot2 linewidth 1 (mm-based) in points, and its default axis line width
LINE_PT = MM_TO_PT * 0.75
AXIS_LINE_PT = BASE_SIZE / 22 * MM_TO_PT * 0.75


def text_pt(kind: str) -> float:
    """Point size of in-panel statistics text for a template ("roc", "small", ...)."""
    return TEXT_MM[kind] * MM_TO_PT


def lab_colors(set: str = "binary", n: int | None = None) -> list[str]:
    """House palettes: binary, categorical, dataset, clusters, diverging, accent."""
    if set not in COLORS:
        raise ValueError(f"unknown palette '{set}'; use one of: {', '.join(COLORS)}")
    pal = COLORS[set]
    if n is None:
        return list(pal)
    if n > len(pal):
        raise ValueError(f"palette '{set}' has {len(pal)} colours, {n} requested")
    return list(pal[:n])


def lab_sizes() -> dict[str, tuple[float, float]]:
    return dict(SIZES)


def palette_for(n: int) -> list[str]:
    """Smallest house palette that has n colours."""
    if n <= 2:
        return lab_colors("binary", n)
    if n <= 10:
        return lab_colors("categorical", n)
    return lab_colors("clusters", n)


def to_mpl_color(color: str) -> str:
    """R's #RRGGBBAA and 'grey' names to matplotlib form."""
    if color == "grey":
        return "#bebebe"  # R's grey, not matplotlib's #808080
    return color.lower() if color.startswith("#") else color


def resolve_size(size) -> tuple[float, float]:
    if isinstance(size, (tuple, list)) and len(size) == 2:
        return float(size[0]), float(size[1])
    if size not in SIZES:
        raise ValueError(f"unknown size preset '{size}'; use one of: {', '.join(SIZES)}, or (width, height)")
    return SIZES[size]
