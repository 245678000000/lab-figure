# Style sheet: every template on the HNSCC example data, page 1 with open
# axes (default), page 2 with boxed panels. Run from the repo root:
#   Rscript examples/style_sheet.R   ->  docs/style-sheet.pdf + .png pages
library(labstyle)
library(patchwork)

build <- function() {
  env <- new.env()
  plots <- list()
  for (f in c("roc", "km", "forest", "box", "violin", "rate_bar", "auc_bar", "cor_heatmap", "pie")) {
    exprs <- parse(file.path("examples", paste0(f, ".R")))
    # run everything except the save_fig()/print lines; keep the last `p`
    keep <- !grepl("^(save_fig|lab_stats|tab$)", vapply(exprs, function(e) deparse(e)[1], ""))
    for (e in exprs[keep]) eval(e, env)
    plots[[f]] <- env$p
  }
  plots
}

page <- function(plots, title) {
  wrap_plots(
    plots$roc, wrap_elements(full = plots$km), plots$box,
    plots$rate_bar, plots$violin, plots$auc_bar,
    wrap_elements(full = plots$forest), plots$cor_heatmap, plots$pie,
    ncol = 3, widths = c(1, 1, 1)
  ) + plot_annotation(title = title, tag_levels = "a")
}

dir.create("docs", showWarnings = FALSE)
open_axes <- build()
options(labstyle.boxed = TRUE)
boxed <- build()
options(labstyle.boxed = FALSE)

w <- 15; h <- 13
grDevices::pdf("docs/style-sheet.pdf", width = w, height = h, useDingbats = FALSE)
print(page(open_axes, "A. Open axes (default: theme_lab())"))
print(page(boxed, "B. Boxed panels (theme_lab(boxed = TRUE), the theme_bw look)"))
grDevices::dev.off()
for (i in 1:2) {
  ragg::agg_png(sprintf("docs/style-sheet-%d.png", i), width = w, height = h, units = "in",
                res = 110, background = "white")
  print(page(if (i == 1) open_axes else boxed,
             if (i == 1) "A. Open axes (default)" else "B. Boxed panels"))
  grDevices::dev.off()
}
cat("wrote docs/style-sheet.pdf, docs/style-sheet-1.png, docs/style-sheet-2.png\n")
