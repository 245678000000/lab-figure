#' House theme: open axes, no grid, black axis lines and text.
#'
#' `boxed = TRUE` keeps a black panel border instead of axis lines (the
#' theme_bw look); `options(labstyle.boxed = TRUE)` makes that the default for
#' every template. `x_angle` rotates x tick labels (45 for long group names).
theme_lab <- function(base_size = .lab_style$base_size, x_angle = 0,
                      boxed = getOption("labstyle.boxed", FALSE), legend = "right") {
  t <- theme_classic(base_size = base_size) +
    theme(
      panel.grid = element_blank(),
      panel.background = element_rect(fill = "white", colour = NA),
      plot.background = element_rect(fill = "white", colour = NA),
      axis.line = element_line(colour = "black"),
      axis.ticks = element_line(colour = "black"),
      axis.text = element_text(colour = "black"),
      legend.background = element_rect(fill = NA, colour = NA),
      legend.key = element_rect(fill = NA, colour = NA),
      legend.position = legend
    )
  if (x_angle != 0) {
    t <- t + theme(axis.text.x = element_text(angle = x_angle, hjust = 1, vjust = 1))
  }
  if (boxed) {
    t <- t + theme(
      axis.line = element_blank(),
      panel.border = element_rect(fill = NA, colour = "black")
    )
  }
  t
}

scale_colour_lab <- function(set = "binary", ...) {
  scale_colour_manual(values = lab_colors(set), ...)
}

scale_color_lab <- scale_colour_lab

scale_fill_lab <- function(set = "binary", ...) {
  scale_fill_manual(values = lab_colors(set), ...)
}

#' Navy - white - dark red gradient for correlations and fold changes.
scale_fill_lab_diverging <- function(limits = c(-1, 1), midpoint = 0, ...) {
  div <- lab_colors("diverging")
  scale_fill_gradient2(low = div[1], mid = div[2], high = div[3],
                       midpoint = midpoint, limits = limits, ...)
}
