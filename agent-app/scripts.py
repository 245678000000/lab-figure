"""Writes the figure script shown in the editor.

Every script has the same short shape, so it reads like the lab-figure
examples:

    source("figure-style.R")      # house style, read_source(), finish()
    d <- read_source()            # this run's input table
    p <- lab_volcano(d, ...)      # one template call
    finish(p)                     # figure.pdf/png/svg + statistics

The bookkeeping (colours, export size, Unicode PDF, statistics files) lives
in figure-style.R / figure_style.py, which are copied next to each script.
"""
import json

WIDTH = 88  # wrap template calls longer than this


def rstr(value):
    # JSON strings are valid R strings; encoding also prevents code interpolation.
    return json.dumps(str(value), ensure_ascii=False)


def rvec(values):
    return "c(" + ", ".join(rstr(x) for x in values) + ")"


def r_call(target, fn, /, *args, **named):
    """`target <- fn(args, name = value, ...)`, skipping named values that are None."""
    parts = [*args, *(f"{k} = {v}" for k, v in named.items() if v is not None)]
    start = f"{target} <- {fn}("
    line, lines = start, []
    for i, part in enumerate(parts):
        piece = part + (", " if i < len(parts) - 1 else ")")
        if len(line) + len(piece) > WIDTH and line != start:
            lines.append(line.rstrip())
            line = " " * len(start) + piece
        else:
            line += piece
    if not parts:
        line += ")"
    return "\n".join(lines + [line])


def _features(spec):
    # Very long selections stay in analysis-settings.json instead of the script.
    predictors = spec.columns.get("predictors", [])
    return "read_features()" if spec.all_numeric_features or len(predictors) > 30 else rvec(predictors)


def _opt(spec, role):
    value = spec.columns.get(role)
    return rstr(value) if value else None


def r_lines(spec):
    """The template call(s) that build `p` for one chart."""
    c, chart = spec.columns, spec.chart
    q = lambda role: rstr(c[role])
    positive = rstr(spec.positive) if spec.positive else None
    show_n = None if spec.show_n else "FALSE"
    if chart == "roc":
        return [r_call("p", "lab_roc", "d", outcome=q("outcome"), predictor=q("predictor"), positive=positive,
                       direction=None if spec.direction == "<" else rstr(spec.direction), show_n=show_n)]
    if chart in ("box", "violin"):
        comparisons = None if spec.comparisons == "default" else rstr(spec.comparisons)
        return [r_call("p", f"lab_{chart}", "d", x=q("group"), y=q("value"), comparisons=comparisons, show_n=show_n)]
    if chart == "rate_bar":
        return [r_call("p", "lab_rate_bar", "d", group=q("group"), outcome=q("outcome"), positive=positive,
                       show_counts=show_n)]
    if chart == "km":
        return [r_call("p", "lab_km", "d", time=q("time"), event=q("event"), group=q("group"), event_value=positive,
                       show_n=show_n, xlab=rstr(spec.x_label) if spec.x_label else None,
                       ylab=rstr(spec.y_label) if spec.y_label else None)]
    if chart == "forest":
        return [r_call("tab", "lab_cox_table", "d", time=q("time"), event=q("event"), terms=rvec(c["predictors"]),
                       event_value=positive),
                r_call("p", "lab_forest", "tab", xlab=rstr(spec.x_label) if spec.x_label else None)]
    if chart == "auc_bar":
        return [r_call("tab", "lab_auc_table", "d", outcome=q("outcome"), predictors=rvec(c["predictors"]),
                       positive=positive, direction=None if spec.direction == "<" else rstr(spec.direction)),
                r_call("p", "lab_auc_bar", "tab")]
    if chart == "cor_heatmap":
        return [r_call("p", "lab_cor_heatmap", "d", vars=rvec(c["predictors"]), method=rstr(spec.method),
                       cluster="FALSE", show_values="TRUE")]
    if chart == "pie":
        return [r_call("p", "lab_pie", "d", category=q("group"))]
    if chart in ("volcano", "ma"):
        named = dict(label=q("label"), mean=q("mean") if chart == "ma" else None, effect=q("effect"), padj=q("padj"),
                     p_threshold=_num(spec.p_threshold, .05), effect_threshold=_num(spec.effect_threshold, 1))
        if chart == "volcano":
            named["label_count"] = _num(spec.label_count, 10)
        return [r_call("p", f"lab_{chart}", "d", **named)]
    if chart in ("expression_heatmap", "sample_distance"):
        return [r_call("p", f"lab_{chart}", "d", label=q("label"), features=_features(spec),
                       scaling=None if spec.scaling == "none" else rstr(spec.scaling))]
    if chart == "pca":
        return [r_call("p", "lab_pca", "d", label=q("label"), features=_features(spec), group=_opt(spec, "group"),
                       scaling=None if spec.scaling == "none" else rstr(spec.scaling))]
    if chart == "missingness":
        return [r_call("p", "lab_missingness", "d", features=_features(spec))]
    if chart == "upset":
        return [r_call("p", "lab_upset", "d", sets=_features(spec))]
    if chart == "embedding":
        return [r_call("p", "lab_embedding", "d", x=q("x"), y=q("y"), group=q("group"))]
    if chart == "feature":
        return [r_call("p", "lab_feature", "d", x=q("x"), y=q("y"), value=q("value"))]
    if chart == "scatter":
        return [r_call("p", "lab_scatter", "d", x=q("x"), y=q("y"), group=_opt(spec, "group"))]
    if chart == "marker_dot":
        return [r_call("p", "lab_marker_dot", "d", label=q("label"), group=q("group"), value=q("value"), pct=q("pct"))]
    if chart == "lr_dot":
        return [r_call("p", "lab_lr_dot", "d", label=q("label"), group=q("group"), value=q("value"), padj=q("padj"))]
    if chart == "composition":
        return [r_call("p", "lab_composition", "d", sample=q("sample"), group=q("group"), count=_opt(spec, "count"))]
    if chart == "enrichment_dot":
        return [r_call("p", "lab_enrichment_dot", "d", label=q("label"), ratio=q("ratio"), count=q("count"),
                       padj=q("padj"))]
    if chart == "enrichment_bar":
        return [r_call("p", "lab_enrichment_bar", "d", label=q("label"), padj=q("padj"))]
    if chart == "gsea":
        return [r_call("p", "lab_gsea", "d", rank=q("rank"), value=q("value"))]
    if chart in ("paired", "paired_delta"):
        return [r_call("p", f"lab_{chart}", "d", pair=q("pair"), group=q("group"), value=q("value"),
                       reference=rstr(spec.reference))]
    if chart == "network":
        return [r_call("p", "lab_network", "d", source=q("source"), target=q("target"), weight=q("weight"))]
    if chart == "histogram":
        return [r_call("p", "lab_histogram", "d", value=q("value"), bins=_num(spec.bins, 30))]
    if chart == "custom":
        return [r_call("p", "lab_custom", "d", x=q("x"), y=q("y"), group=_opt(spec, "group"),
                       geometry=rstr(spec.geometry))]
    # templates added with lab-figure 0.3
    if chart == "waterfall":
        return [r_call("p", "lab_waterfall", "d", id=q("label"), value=q("value"), group=_opt(spec, "group"))]
    if chart == "swimmer":
        return [r_call("p", "lab_swimmer", "d", id=q("label"), time=q("time"), group=_opt(spec, "group"),
                       ongoing=_opt(spec, "ongoing"))]
    if chart == "oncoprint":
        return [r_call("p", "lab_oncoprint", "d", sample=q("sample"), gene=q("label"), alteration=q("alteration"))]
    if chart == "nomogram":
        return [r_call("p", "lab_nomogram", "d", predictors=rvec(c["predictors"]), outcome=q("outcome"),
                       positive=positive)]
    if chart == "calibration":
        return [r_call("p", "lab_calibration", "d", outcome=q("outcome"), predicted=q("predictor"), positive=positive)]
    if chart == "dca":
        return [r_call("p", "lab_dca", "d", outcome=q("outcome"), predictors=rvec(c["predictors"]), positive=positive)]
    if chart == "time_roc":
        return [r_call("p", "lab_time_roc", "d", time=q("time"), event=q("event"), predictor=q("predictor"),
                       times=_times(spec), event_value=positive,
                       direction=None if spec.direction == "<" else rstr(spec.direction))]
    if chart == "ridge":
        return [r_call("p", "lab_ridge", "d", group=q("group"), value=q("value"))]
    if chart == "density":
        return [r_call("p", "lab_density", "d", value=q("value"), group=_opt(spec, "group"))]
    if chart == "sankey":
        return [r_call("p", "lab_sankey", "d", stages=rvec(c["predictors"]), count=_opt(spec, "count"))]
    if chart == "venn":
        return [r_call("p", "lab_venn", "d", sets=rvec(c["predictors"]))]
    if chart == "manhattan":
        return [r_call("p", "lab_manhattan", "d", chr=q("chr"), pos=q("pos"), p=q("pvalue"), label=_opt(spec, "label"))]
    if chart == "qq":
        return [r_call("p", "lab_qq", "d", p=q("pvalue"))]
    raise ValueError(f"没有 {chart} 的脚本模板")


def _num(value, default):
    return None if value == default else format(value, "g")


def _times(spec):
    values = [v for v in spec.time_points.replace("，", ",").split(",") if v.strip()]
    return "c(" + ", ".join(format(float(v), "g") for v in values) + ")"


def r_labels(spec):
    """Title and axis names typed in the app, added after the template."""
    if spec.chart in ("km", "forest", "upset"):
        # composite figures: the title goes above the whole figure; KM/forest axis names are template arguments
        return [f"p <- p + patchwork::plot_annotation(title = {rstr(spec.title)})"] if spec.title else []
    labels = [f"{key} = {rstr(value)}" for key, value in
              [("title", spec.title), ("x", spec.x_label), ("y", spec.y_label)] if value]
    return [f"p <- p + labs({', '.join(labels)})"] if labels else []


def r_size(spec, default_size):
    if default_size:
        return f", size = c({default_size[0]}, {default_size[1]})"
    return "" if spec.size == "template" else f", size = {rstr(spec.size)}"


def r_script(spec, default_size=None):
    body = "\n".join([*r_lines(spec), *r_labels(spec), f"finish(p{r_size(spec, default_size)})"])
    return f'''# AISI-figure. Run in this folder: Rscript figure.R
# ---- data ----
source("figure-style.R")   # house style, read_source() and finish()
d <- read_source()         # the table this figure was made from

# ---- plot ----
{body}
'''


def py_script(spec, default_size=None):
    c = spec.columns
    pyrepr = lambda v: json.dumps(v, ensure_ascii=False)
    show_n = "" if spec.show_n else ", show_n=False"
    if spec.chart == "roc":
        direction = "" if spec.direction == "<" else f", direction={pyrepr(spec.direction)}"
        call = f"lab_roc(d, outcome={pyrepr(c['outcome'])}, predictor={pyrepr(c['predictor'])}, positive={pyrepr(spec.positive)}{direction}{show_n})"
    elif spec.chart == "box":
        comparisons = "" if spec.comparisons == "default" else f", comparisons={pyrepr(spec.comparisons)}"
        call = f"lab_box(d, x={pyrepr(c['group'])}, y={pyrepr(c['value'])}{comparisons}{show_n})"
    else:
        counts = "" if spec.show_n else ", show_counts=False"
        call = f"lab_rate_bar(d, group={pyrepr(c['group'])}, outcome={pyrepr(c['outcome'])}, positive={pyrepr(spec.positive)}{counts})"
    labels = [f"fig.axes[0].set_{key}({pyrepr(value)})" for key, value in
              [("title", spec.title), ("xlabel", spec.x_label), ("ylabel", spec.y_label)] if value]
    size = f"size={tuple(default_size)!r}" if default_size else "" if spec.size == "template" else f"size={pyrepr(spec.size)}"
    body = "\n".join([f"fig = {call}", *labels, f"finish(fig{', ' + size if size else ''})"])
    return f'''# AISI-figure. Run in this folder: python figure.py
# ---- data ----
from figure_style import read_source, finish   # house style and export
from labstyle_py import {"lab_" + spec.chart}
d = read_source()                               # the table this figure was made from

# ---- plot ----
{body}
'''
