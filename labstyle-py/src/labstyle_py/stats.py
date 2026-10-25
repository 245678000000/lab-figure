"""Statistics computed the way the R templates compute them."""

from __future__ import annotations

import math

import numpy as np
from scipy import stats


def format_p_value(p):
    """2 decimals when p >= 0.05, 3 decimals down to 0.0095, else scientific
    with 2 significant digits (format_p_value in labstyle/R/stats.R)."""
    if isinstance(p, (list, tuple, np.ndarray)):
        return [format_p_value(x) for x in p]
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return None
    if p >= 0.05:
        return str(round(p, 2))
    if p >= 0.0095:
        return str(round(p, 3))
    return f"{p:.1e}"


def p_to_symbol(p):
    if isinstance(p, (list, tuple, np.ndarray)):
        return [p_to_symbol(x) for x in p]
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "ns"
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def auc_delong(y, score) -> tuple[float, float, float]:
    """AUC with DeLong 95% CI, as pROC::ci.auc (cases = 1 score higher)."""
    y = np.asarray(y)
    score = np.asarray(score, dtype=float)
    pos, neg = score[y == 1], score[y == 0]
    psi = (pos[:, None] > neg[None, :]) + 0.5 * (pos[:, None] == neg[None, :])
    auc = psi.mean()
    v10, v01 = psi.mean(axis=1), psi.mean(axis=0)
    se = math.sqrt(v10.var(ddof=1) / len(pos) + v01.var(ddof=1) / len(neg))
    z = stats.norm.ppf(0.975)
    return auc, max(0.0, auc - z * se), min(1.0, auc + z * se)


def wilcox_p(a, b) -> float:
    """Two-sided Wilcoxon rank-sum p as R (>= 4.4) computes it by default:
    exact when both groups have fewer than 50 values, also with ties (the
    exact conditional distribution given the tied ranks), otherwise the
    normal approximation with continuity correction."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if len(a) < 50 and len(b) < 50:
        return _wilcox_exact_p(a, b)
    return float(stats.mannwhitneyu(a, b, alternative="two-sided", method="asymptotic",
                                    use_continuity=True).pvalue)


def _wilcox_exact_p(a: np.ndarray, b: np.ndarray) -> float:
    """Exact two-sided p of W = rank sum of `a` - m(m+1)/2, from the
    distribution of the sum of m of the pooled (mid-)ranks drawn without
    replacement; two-sided p = min(2 P(W <= w), 2 P(W >= w), 1) as in R's
    .wilcox_test_two_pval_exact."""
    m = len(a)
    ranks2 = np.rint(2 * stats.rankdata(np.concatenate([a, b]))).astype(int)  # mid-ranks x 2
    total = int(ranks2.sum())
    # counts[k, s]: number of k-subsets of the ranks seen so far with doubled sum s
    counts = np.zeros((m + 1, total + 1))
    counts[0, 0] = 1.0
    for r in ranks2:
        counts[1:, r:] += counts[:-1, : total + 1 - r]  # numpy buffers the overlapping read
    prob = counts[m] / counts[m].sum()
    w = np.arange(total + 1) / 2 - m * (m + 1) / 2
    observed = ranks2[:m].sum() / 2 - m * (m + 1) / 2
    eps = 1e-7
    lower = prob[w <= observed + eps].sum()
    upper = prob[w >= observed - eps].sum()
    return float(min(2 * lower, 2 * upper, 1.0))


def odds_ratio_wald(events2, n2, events1, n1) -> tuple[float, float]:
    """Wald 95% CI of the odds ratio (group 2 vs group 1); 0.5 is added to
    every cell when one is empty."""
    cells = np.array([events2, n2 - events2, events1, n1 - events1], dtype=float)
    if (cells == 0).any():
        cells = cells + 0.5
    log_or = math.log(cells[0] * cells[3] / (cells[1] * cells[2]))
    half = stats.norm.ppf(0.975) * math.sqrt((1 / cells).sum())
    return math.exp(log_or - half), math.exp(log_or + half)


def fisher_p(table) -> float:
    return float(stats.fisher_exact(np.asarray(table), alternative="two-sided").pvalue)
