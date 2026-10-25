"""lab_roc, lab_box, lab_rate_bar: ports of the R templates of the same name.
Each returns a matplotlib Figure carrying `lab_stats` (a DataFrame) and
`lab_size` (its size preset); pass `ax=` to draw into an existing panel."""

from __future__ import annotations

import math
from itertools import combinations

import numpy as np
import pandas as pd
from matplotlib.colors import to_rgb
from matplotlib.ticker import FixedLocator, FormatStrFormatter, MaxNLocator
from scipy import stats as st
from sklearn.metrics import roc_curve

from .stats import auc_delong, fisher_p, format_p_value, odds_ratio_wald, wilcox_p
from .style import LINE_PT, MM_TO_PT, lab_colors, palette_for, text_pt, to_mpl_color
from .theme import new_axes, style_axes, with_lab_rc

GRAY70 = "#b3b3b3"
GEOM_LINE_PT = LINE_PT * 0.5  # ggplot2's default linewidth 0.5 for boxes, bars, whiskers


def _pretty_y(ax) -> None:
    """About as many y ticks as ggplot2's default breaks (roughly 3-5)."""
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4, steps=[1, 2, 2.5, 5, 10]))


def _point_area(size: float) -> float:
    """ggplot2 point size (mm) as a matplotlib scatter area (pt^2)."""
    return (size * MM_TO_PT) ** 2


class ColumnNotFoundError(KeyError):
    """A KeyError that prints its message without the quotes KeyError adds."""

    def __str__(self) -> str:
        return str(self.args[0])


def _col(data: pd.DataFrame, name: str) -> pd.Series:
    if name not in data.columns:
        raise ColumnNotFoundError(f"column '{name}' not found; available: {', '.join(map(str, data.columns))}")
    return data[name]


def _as_binary(x: pd.Series, positive=None, arg: str = "outcome") -> np.ndarray:
    """Two-class outcome -> 1.0 / 0.0 / nan. 0/1 and booleans pass through;
    1/2 status means 2 = event; otherwise `positive` names the event class."""
    s = pd.Series(x)
    if s.dtype == bool:
        return s.astype(float).to_numpy()
    vals = sorted(s.dropna().unique(), key=str)
    if pd.api.types.is_numeric_dtype(s) and positive is None:
        if set(vals) <= {0, 1}:
            return s.astype(float).to_numpy()
        if set(vals) <= {1, 2}:
            print(f"'{arg}' coded 1/2: treating 2 as the event")
            return (s == 2).astype(float).where(s.notna()).to_numpy()
    if len(vals) != 2:
        raise ValueError(f"'{arg}' must have exactly 2 classes, found {len(vals)}: "
                         + ", ".join(map(str, vals[:6])))
    if positive is None:
        if isinstance(s.dtype, pd.CategoricalDtype):
            positive = s.cat.remove_unused_categories().cat.categories[1]
        else:
            raise ValueError(f"'{arg}' has classes {vals[0]} / {vals[1]}; set positive= the event class")
    if str(positive) not in map(str, vals):
        raise ValueError(f"positive = '{positive}' is not a class of '{arg}' ({' / '.join(map(str, vals))})")
    return (s.astype(str) == str(positive)).astype(float).where(s.notna()).to_numpy()


def _binary_labels(x: pd.Series, positive=None) -> tuple[str, str]:
    """(negative, positive) class names, matching _as_binary()."""
    s = pd.Series(x)
    vals = sorted(s.dropna().unique(), key=str)
    if positive is None:
        if isinstance(s.dtype, pd.CategoricalDtype):
            cats = list(s.cat.remove_unused_categories().cat.categories)
            return str(cats[0]), str(cats[1])
        return str(vals[0]), str(vals[-1])
    other = [v for v in vals if str(v) != str(positive)]
    return str(other[0]), str(positive)


def _levels(s: pd.Series, levels=None) -> list:
    if levels is not None:
        return list(levels)
    if isinstance(s.dtype, pd.CategoricalDtype):
        return [c for c in s.cat.categories if (s == c).any()]
    vals = s.dropna().unique()
    numeric = all(isinstance(v, (int, float, np.number)) for v in vals)
    return sorted(vals) if numeric else sorted(vals, key=str)


def _set_meta(fig, ax, size, stats: pd.DataFrame):
    fig.lab_size = size
    fig.lab_stats = stats
    ax.lab_stats = stats
    return fig


@with_lab_rc
def lab_roc(data: pd.DataFrame, outcome: str, predictor, positive=None, direction: str = "<",
            labels=None, youden: bool = False, show_n: bool = True, ax=None):
    """ROC curve with AUC (DeLong 95% CI). One predictor: black step curve and
    an AUC / CI / n label. Several: one coloured curve each, AUCs in the legend.
    direction "<" means higher predictor values indicate the positive class."""
    y_raw = _col(data, outcome)
    y = _as_binary(y_raw, positive, outcome)
    classes = _binary_labels(y_raw, positive)
    preds = [predictor] if isinstance(predictor, str) else list(predictor)
    labels = list(labels) if labels is not None else preds

    curves = []
    for pr in preds:
        x = pd.to_numeric(_col(data, pr), errors="coerce").to_numpy(dtype=float)
        ok = ~np.isnan(x) & ~np.isnan(y)
        yy, score = y[ok].astype(int), x[ok] if direction == "<" else -x[ok]
        fpr, tpr, thr = roc_curve(yy, score, drop_intermediate=False)
        auc, lo, hi = auc_delong(yy, score)
        curves.append(dict(fpr=fpr, tpr=tpr, thr=thr, score=score, auc=auc, lower=lo, upper=hi,
                           n=int(ok.sum()), n_pos=int((yy == 1).sum()), n_neg=int((yy == 0).sum())))
    stats = pd.DataFrame({
        "predictor": labels,
        **{k: [c[k] for c in curves] for k in ("auc", "lower", "upper", "n", "n_pos", "n_neg")},
    })

    multi = len(curves) > 1
    fig, ax = new_axes(ax, "roc_multi" if multi else "roc")
    ax.plot([0, 1], [0, 1], linestyle=(0, (4, 4)), color=GRAY70, linewidth=LINE_PT / 2)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(FixedLocator([0, 0.25, 0.5, 0.75, 1]))
        axis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax.set_xlabel("1 - Specificity")
    ax.set_ylabel("Sensitivity")

    if not multi:
        cv = curves[0]
        ax.step(cv["fpr"], cv["tpr"], where="pre", color="black", linewidth=LINE_PT)
        lines = [f"AUC = {cv['auc']:.2f}", f"95% CI {cv['lower']:.2f}-{cv['upper']:.2f}"]
        if show_n:
            lines.append(f"n: {classes[1]} {cv['n_pos']}, {classes[0]} {cv['n_neg']}")
        ax.text(1, 0.03, "\n".join(lines), ha="right", va="bottom", fontsize=text_pt("roc"),
                linespacing=0.9 * 1.2)
        if youden:
            j = cv["tpr"] - cv["fpr"]
            idx = int(np.flatnonzero(j == j.max())[-1])  # pROC keeps the lowest threshold on ties
            uniq = np.unique(cv["score"])
            k = int(np.searchsorted(uniq, cv["thr"][idx]))
            cut = (uniq[k] + uniq[k - 1]) / 2 if k > 0 else -math.inf  # pROC thresholds are midpoints
            cut = cut if direction == "<" else -cut
            px, py = cv["fpr"][idx], cv["tpr"][idx]
            ax.plot([px], [py], "o", color=lab_colors("accent")[0], markersize=3 * MM_TO_PT)
            ax.annotate(f"Cutoff = {cut:.3g}", (px, py), xytext=(3, 3), textcoords="offset points",
                        fontsize=text_pt("small"))
            stats["youden_cutoff"] = cut
            stats["youden_sensitivity"] = py
            stats["youden_specificity"] = 1 - px
        return _set_meta(fig, ax, "roc", stats)

    for color, label, cv in zip(palette_for(len(curves)), labels, curves):
        ax.step(cv["fpr"], cv["tpr"], where="pre", color=to_mpl_color(color), linewidth=LINE_PT * 0.8,
                label=f"{label} (AUC = {cv['auc']:.2f})")
    ax.legend(loc="lower right", fontsize=12 * 0.8 * 0.75, handlelength=1.5)
    return _set_meta(fig, ax, "roc_multi", stats)


def _resolve_comparisons(comparisons, lv):
    if comparisons is None:
        return [tuple(lv)] if len(lv) == 2 else []
    if comparisons == "all":
        return list(combinations(lv, 2))
    if comparisons == "none":
        return []
    return [tuple(c) for c in comparisons]


def _pair_tests(groups: pd.Series, values: np.ndarray, pairs, test: str) -> pd.DataFrame:
    rows = []
    for g1, g2 in pairs:
        a, b = values[(groups == g1).to_numpy()], values[(groups == g2).to_numpy()]
        p = st.ttest_ind(a, b, equal_var=False).pvalue if test == "t" else wilcox_p(a, b)
        rows.append({"group1": g1, "group2": g2, "n1": len(a), "n2": len(b), "test": test, "p": float(p)})
    return pd.DataFrame(rows, columns=["group1", "group2", "n1", "n2", "test", "p"])


def _brackets(ax, tests: pd.DataFrame, lv, y0: float, step: float, size: float) -> float:
    """Square brackets with "p = ..." above, stacked upwards; returns the top."""
    tip = step * 0.25
    for i, row in enumerate(tests.itertuples()):
        x1, x2 = lv.index(row.group1), lv.index(row.group2)
        y = y0 + i * step
        ax.plot([x1, x1, x2, x2], [y - tip, y, y, y - tip], color="black", linewidth=0.4 * LINE_PT)
        ax.text((x1 + x2) / 2, y + step * 0.3, f"p = {format_p_value(row.p)}", ha="center",
                va="bottom", fontsize=size)
    return y0 + len(tests) * step


@with_lab_rc
def lab_box(data: pd.DataFrame, x: str, y: str, levels=None, comparisons=None, test: str = "wilcox",
            xlab=None, ylab=None, x_angle=None, percent: bool = False, ylim=None, show_n: bool = True,
            ax=None):
    """Points + box per group with Wilcoxon (or Welch t) brackets.
    comparisons: None (the single pair of 2 groups), "all", "none" or a list of pairs."""
    d = pd.DataFrame({"x": _col(data, x), "y": pd.to_numeric(_col(data, y), errors="coerce")}).dropna()
    lv = [g for g in _levels(d["x"], levels) if (d["x"] == g).any()]
    d = d[d["x"].isin(lv)]
    values = d["y"].to_numpy(dtype=float) * (100 if percent else 1)
    names = [str(g) for g in lv]
    x_angle = x_angle if x_angle is not None else (0 if max(map(len, names)) <= 6 else 45)
    colors = [to_mpl_color(c) for c in palette_for(len(lv))]
    tests = _pair_tests(d["x"], values, _resolve_comparisons(comparisons, lv), test)

    size = (0.75 + 0.6 * len(lv), 3.3) if show_n else ("narrow" if len(lv) <= 2 else (0.6 + 0.55 * len(lv), 3.3))
    fig, ax = new_axes(ax, size)
    rng = np.random.default_rng(1)
    groups = []
    for i, g in enumerate(lv):
        v = values[(d["x"] == g).to_numpy()]
        groups.append(v)
        ax.scatter(i + rng.uniform(-0.2, 0.2, len(v)), v, s=_point_area(2), color=colors[i],
                   linewidths=0, zorder=2)
    box = ax.boxplot(groups, positions=range(len(lv)), widths=0.75, patch_artist=True,
                     showfliers=False, whis=1.5, zorder=3,
                     medianprops=dict(color="black", linewidth=GEOM_LINE_PT * 2),  # ggplot fatten = 2
                     whiskerprops=dict(color="black", linewidth=GEOM_LINE_PT),
                     capprops=dict(linewidth=0),
                     boxprops=dict(edgecolor="black", linewidth=GEOM_LINE_PT))
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor((*to_rgb(color), 0.5))  # fill at alpha 0.5, outline stays opaque

    span = (ylim[1] - ylim[0]) if ylim else float(values.max() - values.min())
    step = span * 0.12
    y0 = values.max() + step * 0.6 if ylim is None else ylim[1] - step * (len(tests) - 1) - step * 0.9
    top = _brackets(ax, tests, lv, y0, step, text_pt("small"))
    if ylim is not None:
        ax.set_ylim(*ylim)
    else:
        lo, hi = float(values.min()), max(float(values.max()), top if len(tests) else float(values.max()))
        ax.set_ylim(lo - 0.05 * (hi - lo), hi + 0.05 * (hi - lo))

    _pretty_y(ax)
    ax.set_xlim(-0.6, len(lv) - 0.4)
    ax.set_xticks(range(len(lv)))
    counts = [len(v) for v in groups]
    sep = "\n" if x_angle == 0 else " "
    ax.set_xticklabels([f"{n}{sep}(n = {c})" if show_n else n for n, c in zip(names, counts)])
    style_axes(ax, x_angle)
    ax.set_xlabel(xlab or "")
    ax.set_ylabel(ylab or y)
    return _set_meta(fig, ax, size, tests)


@with_lab_rc
def lab_rate_bar(data: pd.DataFrame, group: str, outcome: str, positive=None, levels=None, ylab=None,
                 show_counts: bool = True, show_ci: bool = True, show_p: bool = True, ax=None):
    """Event rate (%) per group with events/n on each bar; two groups get an
    OR bracket with its Wald 95% CI and Fisher's exact p."""
    d = pd.DataFrame({"group": _col(data, group), "y": _as_binary(_col(data, outcome), positive, outcome)}).dropna()
    lv = [g for g in _levels(d["group"], levels) if (d["group"] == g).any()]
    rows = []
    for g in lv:
        yy = d.loc[d["group"] == g, "y"]
        rows.append({"group": g, "n": len(yy), "events": int(yy.sum()), "rate": yy.mean() * 100})
    rates = pd.DataFrame(rows)
    colors = [to_mpl_color(c) for c in palette_for(len(lv))]
    small = text_pt("bar")

    size = "bar2" if len(lv) <= 2 else (0.6 + 0.45 * len(lv), 2.565)
    fig, ax = new_axes(ax, size)
    ax.bar(range(len(lv)), rates["rate"], width=0.6, color=colors, edgecolor="black",
           linewidth=GEOM_LINE_PT, zorder=2)
    top = float(rates["rate"].max())
    if show_counts:
        for i, r in rates.iterrows():
            ax.text(i, r["rate"] + 2, f"{r['events']}/{r['n']}", ha="center", va="bottom", fontsize=small)
        top += 9

    stats = rates.copy()
    ymax = 100.0
    if len(lv) == 2:
        odds = rates["rate"] / (100 - rates["rate"])
        odds_ratio = float(odds.iloc[1] / odds.iloc[0]) if odds.iloc[0] else math.inf
        lo, hi = odds_ratio_wald(rates["events"][1], rates["n"][1], rates["events"][0], rates["n"][0])
        fp = fisher_p(pd.crosstab(d["group"], d["y"]).to_numpy())
        stats["or"], stats["or_lower"], stats["or_upper"], stats["fisher_p"] = odds_ratio, lo, hi, fp
        lines = [f"OR = {round(odds_ratio, 1)}"]
        if show_ci:
            lines.append(f"({lo:.1f}-{hi:.1f})")
        if show_p:
            lines.append(f"p = {format_p_value(fp)}")
        br = top + 6
        ax.plot([0, 0, 1, 1], [br - 4, br, br, br - 4], color="black", linewidth=0.4 * LINE_PT)
        ax.text(0.5, br + 3, "\n".join(lines), ha="center", va="bottom", fontsize=small,
                linespacing=0.9 * 1.2)
        ymax = max(100.0, br + 3 + 7.5 * len(lines))
    elif show_counts:
        ymax = max(100.0, top + 2)

    ax.set_ylim(0, ymax * 1.02)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlim(-0.6, len(lv) - 0.4)
    ax.set_xticks(range(len(lv)))
    ax.set_xticklabels([str(g) for g in lv])
    ax.set_ylabel(ylab or f"{outcome} (%)")
    return _set_meta(fig, ax, size, stats)
