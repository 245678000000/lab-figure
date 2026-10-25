#' Violin + inner box + points per group, with test brackets. Adapted from
#' plot_violin in Neutrophil_EGR1/code/Figure2.Rmd. Arguments as in lab_box().
lab_violin <- function(data, x, y, levels = NULL, comparisons = NULL, test = c("wilcox", "t"),
                       xlab = NULL, ylab = NULL, x_angle = 0, percent = FALSE,
                       points = TRUE, trim = TRUE, show_n = TRUE) {
  test <- match.arg(test)
  d <- stats::na.omit(data.frame(x = .as_group(.col(data, x), levels),
                                 y = as.numeric(.col(data, y))))
  d$x <- droplevels(d$x)
  if (percent) d$y <- d$y * 100
  lv <- levels(d$x)
  tests <- .pair_tests(d, .resolve_comparisons(comparisons, lv), test)
  step <- diff(range(d$y)) * 0.1

  p <- ggplot(d, aes(x = x, y = y))
  if (points) {
    p <- p + geom_point(shape = 16, size = 0.5, alpha = 0.6,
                        position = position_jitter(width = 0.2, height = 0, seed = 1))
  }
  p <- p +
    geom_violin(aes(fill = x), scale = "width", trim = trim, alpha = 0.8) +
    geom_boxplot(width = 0.15, fill = "white", colour = "black", outlier.shape = NA) +
    scale_fill_manual(values = .palette_for(length(lv))) +
    labs(x = xlab, y = ylab %||% y) +
    theme_lab(x_angle = x_angle, legend = "none") +
    .bracket_layers(tests, lv, max(d$y) + step * 0.6, step, .lab_style$text$small)
  if (show_n) p <- p + .x_scale_n(d$x, x_angle)
  .set_meta(p, "violin", tests)
}
