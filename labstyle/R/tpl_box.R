#' Points + box plot per group with Wilcoxon (or t) test brackets. Adapted from
#' save_feature_boxplot in melanoma_irAE/code/utils.R.
#'
#' `comparisons`: NULL (the single pair when there are 2 groups), "all",
#' "none", or a list of c("A", "B") pairs. `percent = TRUE` multiplies y by 100.
#' `show_n` puts each group's size in its axis label. `x_angle` defaults to
#' upright for short group names and 45 degrees for long ones.
lab_box <- function(data, x, y, levels = NULL, comparisons = NULL, test = c("wilcox", "t"),
                    xlab = NULL, ylab = NULL, x_angle = NULL, percent = FALSE, ylim = NULL,
                    show_n = TRUE) {
  test <- match.arg(test)
  d <- stats::na.omit(data.frame(x = .as_group(.col(data, x), levels),
                                 y = as.numeric(.col(data, y))))
  d$x <- droplevels(d$x)
  if (percent) d$y <- d$y * 100
  lv <- levels(d$x)
  x_angle <- x_angle %||% if (max(nchar(lv)) <= 6) 0 else 45
  cols <- .palette_for(length(lv))
  tests <- .pair_tests(d, .resolve_comparisons(comparisons, lv), test)

  span <- if (is.null(ylim)) diff(range(d$y)) else diff(ylim)
  step <- span * 0.12
  # brackets above the data, or inside a fixed ylim (as in the original)
  y0 <- if (is.null(ylim)) max(d$y) + step * 0.6 else ylim[2] - step * (nrow(tests) - 1) - step * 0.9

  p <- ggplot(d, aes(x = x, y = y)) +
    geom_point(aes(colour = x), size = 2,
               position = position_jitter(width = 0.2, height = 0, seed = 1)) +
    geom_boxplot(aes(fill = x), outlier.shape = NA, alpha = 0.5, colour = "black") +
    scale_colour_manual(values = cols) +
    scale_fill_manual(values = cols) +
    labs(x = xlab, y = ylab %||% y) +
    theme_lab(x_angle = x_angle, legend = "none") +
    .bracket_layers(tests, lv, y0, step, .lab_style$text$small)
  if (show_n) p <- p + .x_scale_n(d$x, x_angle)
  if (!is.null(ylim)) p <- p + coord_cartesian(ylim = ylim, clip = "off")
  # "(n = 28)" labels need more room per group than the original 1.5 in panel
  size <- if (show_n) c(0.75 + 0.6 * length(lv), 3.3)
          else if (length(lv) <= 2) "narrow" else c(0.6 + 0.55 * length(lv), 3.3)
  .set_meta(p, size, tests)
}
