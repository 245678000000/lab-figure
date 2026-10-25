---
name: lab-figure
description: >-
  Make this lab's data figures from a table (csv/xlsx) in the lab's house style:
  ROC/AUC, Kaplan-Meier survival with risk table, Cox forest plot, box or violin
  with Wilcoxon p, response-rate bars with OR, AUC comparison bars, correlation
  heatmap, composition pie. Use for 实验室作图、按导师风格画图、ROC/KM/森林图/箱线图
  from data. Not for schematics, mechanism diagrams or graphical abstracts
  (use nature-figure for those).
---

# Lab figure

Figures are built from the `labstyle` R package: a fixed house style plus plot
templates. Your job is to pick a template, map the data columns, and write a
short script. Do not restyle templates or hand-write ggplot themes.

`LABFIG=<this skill dir>/scripts/labfig` is the entry point for every step below.

## Workflow

1. **Inspect the data.** `"$LABFIG" inspect <data file>`. Read the role hints
   (binary / survival time / survival event / id) and the NOTE lines: a
   two-row Excel header must be read with the `skip =` shown.
2. **Pick a template** from [references/template-catalog.md](references/template-catalog.md).
   If the request is ambiguous (which column is the outcome, which class is
   positive, what cutoff), ask one short question rather than guess.
3. **Write `figures/<name>.R`** in the project, 20–40 lines, in two sections:

   ```r
   # ---- data ----
   library(labstyle)
   d <- readxl::read_excel("data/cohort.xlsx", sheet = "Cohort10", skip = 1)
   # recode / filter here

   # ---- plot ----
   p <- lab_roc(d, outcome = "Response", predictor = "B_cells", positive = "R")
   save_fig(p, "roc_bcells")
   lab_stats(p)
   ```

   Keep data loading above `# ---- plot ----` and plotting below it (the
   live preview caches the data section).
4. **Render**: `"$LABFIG" render figures/<name>.R`. On error it prints the
   script line; fix and re-render. Open the PNG it lists and look at it. At
   most two self-correction rounds, then show the user what you have.
5. **Report** the figure path and the numbers from `lab_stats(p)` (AUC, HR,
   p). Never state a statistic the template did not compute.
6. **Only for the final export** (the user says it is final / for
   submission): `"$LABFIG" qa figures/<name>.pdf`. FIX BEFORE DELIVERY means
   repair and re-run; REVIEW REQUIRED means look at each warning. The
   collision audit measures rotated text by its upright bounding box, so
   45° tick labels next to each other can be flagged as text-text overlaps
   when the glyphs do not touch: look at the PNG before changing anything
   for those findings.

## Rules

- Style comes only from labstyle: `theme_lab()`, `scale_*_lab()`,
  `lab_colors()`, size presets in `save_fig()`. No hex colours, font sizes or
  `theme_bw()` in figure scripts. Style values and their sources:
  [references/style-spec.md](references/style-spec.md).
- Small changes go through template arguments or ggplot additions:
  `p + labs(y = "...")`, `p + coord_cartesian(ylim = c(0, 50))`. For KM and
  forest plots (patchwork objects) use `&` instead of `+` for theme changes.
- `save_fig()` picks the template's size preset; pass `size = "wide"` or
  `size = c(w, h)` only when the user asks for a different size.
- Multi-panel figures: build panels with templates, combine with
  `patchwork::wrap_plots(...) + patchwork::plot_annotation(tag_levels = "a")`,
  save with an explicit `size`. KM and forest plots are themselves
  composites: put them in as `patchwork::wrap_elements(full = p)`, otherwise
  the risk table / forest columns get their own panel letters. A forest plot
  needs the width of its own preset (about 6.4 in with the CI column): give it
  a full row, or use `ci_text = FALSE` for a narrower one.
- No template fits: write plain ggplot2 with `theme_lab()` and house scales,
  then `save_fig(p, name, size = "single")`. Say that it is not a template.
- Column names with spaces or symbols are passed as plain strings; keep them
  when reading (`readxl` does; for csv use `check.names = FALSE`).
- Python: `labstyle_py` has `lab_roc`, `lab_box` and `lab_rate_bar` with the
  same arguments, house style and statistics as the R templates (see the
  catalog's Python section). Use it when the user works in Python; for any
  other template, say it exists only in R and offer R. Same two-section
  layout in `figures/<name>.py`, render with `"$LABFIG" render figures/<name>.py`.

## Setup check

If `render` fails because R or labstyle is missing, run `"$LABFIG" doctor` and
report what it says instead of installing anything yourself.
