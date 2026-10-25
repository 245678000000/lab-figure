"""The Python port must match the labstyle R package: same style values, and
the same statistics on the same data. R is asked directly for its values."""

import json
import math
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

import labstyle_py as lp
from labstyle_py import stats, style

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "evals" / "data" / "hnscc_inhouse_cohorts.xlsx"
RSCRIPT = shutil.which("Rscript") or "/usr/local/bin/Rscript"
needs_r = pytest.mark.skipif(not Path(RSCRIPT).exists(), reason="R not installed")


def r_json(code: str):
    out = subprocess.run([RSCRIPT, "-e", f"suppressMessages(library(labstyle)); {code}"],
                         capture_output=True, text=True, cwd=REPO, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def cohort10() -> pd.DataFrame:
    d = pd.read_excel(DATA, sheet_name="Cohort10", header=1)
    d["Response"] = d["Best response"].isin(["CR", "PR", "SD"]).map({True: "DC", False: "PD"})
    d["B_group"] = (d["B_cells"] > d["B_cells"].median()).map({True: "High", False: "Low"})
    return d


R_COHORT10 = (
    'd <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort10", skip = 1); '
    'd$Response <- ifelse(d$`Best response` %in% c("CR", "PR", "SD"), "DC", "PD"); '
    'd$B_group <- ifelse(d$B_cells > median(d$B_cells), "High", "Low"); '
)


@needs_r
def test_style_values_match_r():
    r = r_json(
        "cat(jsonlite::toJSON(list("
        "colors = sapply(c('binary','categorical','dataset','clusters','diverging','accent'), lab_colors), "
        "sizes = lab_sizes(), text = labstyle:::.lab_style$text, base = labstyle:::.lab_style$base_size, "
        "dpi = labstyle:::.lab_style$dpi), digits = NA))"
    )
    assert r["colors"] == style.COLORS
    assert {k: tuple(v) for k, v in r["sizes"].items()} == style.SIZES
    assert {k: v[0] for k, v in r["text"].items()} == style.TEXT_MM
    assert r["base"][0] == style.BASE_SIZE and r["dpi"][0] == style.DPI


@needs_r
def test_p_value_formatting_matches_r():
    ps = [0.73, 0.2, 0.05, 0.0499, 0.0312, 0.0096, 0.0094, 0.00012, 3.4e-9]
    r = r_json(f"cat(jsonlite::toJSON(format_p_value(c({', '.join(map(repr, ps))}))))")
    assert stats.format_p_value(ps) == r
    assert stats.p_to_symbol([0.0005, 0.005, 0.03, 0.2, float("nan")]) == ["***", "**", "*", "ns", "ns"]


@needs_r
def test_roc_stats_match_r():
    r = r_json(R_COHORT10 + 'cat(jsonlite::toJSON(lab_stats(lab_roc(d, "Response", "B_cells", '
               'positive = "DC", youden = TRUE)), digits = NA))')[0]
    py = lp.lab_roc(cohort10(), "Response", "B_cells", positive="DC", youden=True).lab_stats.iloc[0]
    for key in ("auc", "lower", "upper", "youden_cutoff", "youden_sensitivity", "youden_specificity"):
        assert py[key] == pytest.approx(r[key], abs=1e-9), key
    assert (py["n_pos"], py["n_neg"]) == (r["n_pos"], r["n_neg"])


@needs_r
def test_roc_multi_and_direction_match_r():
    r = r_json(R_COHORT10 + 'cat(jsonlite::toJSON(lab_stats(lab_roc(d, "Response", '
               'c("B_cells", "Tregs", "NK_cells"), positive = "DC", direction = ">")), digits = NA))')
    py = lp.lab_roc(cohort10(), "Response", ["B_cells", "Tregs", "NK_cells"], positive="DC",
                    direction=">").lab_stats
    assert list(py["auc"]) == pytest.approx([x["auc"] for x in r], abs=1e-9)
    assert list(py["upper"]) == pytest.approx([x["upper"] for x in r], abs=1e-9)


@needs_r
def test_box_wilcoxon_matches_r_exact_and_tied():
    r = r_json(R_COHORT10 + 'cat(jsonlite::toJSON(c('
               'lab_stats(lab_box(d, "Response", "B_cells"))$p, '
               'lab_stats(lab_box(d, "Response", "Monocytes"))$p), digits = NA))')
    d = cohort10()
    assert lp.lab_box(d, "Response", "B_cells").lab_stats["p"][0] == pytest.approx(r[0], rel=1e-9)
    # Monocytes has tied values: R >= 4.4 still computes the exact (conditional) p
    assert lp.lab_box(d, "Response", "Monocytes").lab_stats["p"][0] == pytest.approx(r[1], rel=1e-9)


@needs_r
def test_wilcoxon_large_groups_use_normal_approximation_like_r():
    import numpy as np

    rng = np.random.default_rng(3)
    a, b = np.round(rng.normal(0, 1, 60), 1), np.round(rng.normal(0.3, 1, 55), 1)  # ties, n >= 50
    r = r_json(f"cat(jsonlite::toJSON(suppressWarnings(wilcox.test(c({', '.join(map(str, a))}), "
               f"c({', '.join(map(str, b))})))$p.value, digits = NA))")
    assert stats.wilcox_p(a, b) == pytest.approx(r[0], rel=1e-9)


@needs_r
def test_rate_bar_or_ci_and_fisher_match_r():
    r = r_json(R_COHORT10 + 'cat(jsonlite::toJSON(lab_stats(lab_rate_bar(d, "B_group", "Response", '
               'positive = "DC", levels = c("Low", "High"))), digits = NA))')[0]
    py = lp.lab_rate_bar(cohort10(), "B_group", "Response", positive="DC",
                         levels=["Low", "High"]).lab_stats.iloc[0]
    for key in ("or", "or_lower", "or_upper", "fisher_p"):
        assert py[key] == pytest.approx(r[key], rel=1e-9), key


def test_save_fig_sizes_and_preview_capture(tmp_path):
    import pymupdf

    fig = lp.lab_roc(cohort10(), "Response", "B_cells", positive="DC")
    paths = lp.save_fig(fig, "roc", dir=tmp_path, data=cohort10())
    assert [Path(p).name for p in paths] == ["roc.pdf", "roc.png", "roc_source_data.csv"]
    page = pymupdf.open(paths[0])[0]
    assert (round(page.rect.width / 72, 2), round(page.rect.height / 72, 2)) == (2.7, 2.2)
    fonts = {f[3].split("+")[-1] for f in page.get_fonts()}  # drop the subset prefix
    assert "ArialMT" in fonts  # TrueType embedded, so the text stays editable

    from labstyle_py.save import preview

    preview.active, preview.figures = True, []
    try:
        assert lp.save_fig(fig, "roc", size="wide", dir=tmp_path / "nope") == []
        assert preview.figures[0]["size"] == (4.6, 2.7)
        assert not (tmp_path / "nope").exists()
    finally:
        preview.active, preview.figures = False, []


def test_input_checks():
    d = cohort10()
    with pytest.raises(KeyError, match="column 'Nope' not found"):
        lp.lab_roc(d, "Nope", "B_cells")
    with pytest.raises(ValueError, match="set positive="):
        lp.lab_roc(d, "Response", "B_cells")
    assert math.isclose(lp.lab_rate_bar(d, "B_group", "Response", positive="DC").lab_stats["rate"].sum(),
                        8 / 17 * 100 + 4 / 17 * 100)
