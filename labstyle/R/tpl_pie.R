#' Composition pie chart. Adapted from plot_pie in melanoma_irAE/code/utils.R.
#' Without `count`, categories are counted from the `category` column.
#' Slices keep first-appearance order unless `levels` is given.
lab_pie <- function(data, category, count = NULL, levels = NULL) {
  cat_col <- as.character(.col(data, category))
  if (is.null(count)) {
    lv <- levels %||% unique(stats::na.omit(cat_col))
    d <- data.frame(category = lv, count = as.vector(table(factor(cat_col, levels = lv))))
  } else {
    d <- data.frame(category = cat_col, count = as.numeric(.col(data, count)))
    lv <- levels %||% unique(d$category)
  }
  d$category <- factor(d$category, levels = lv)

  p <- ggplot(d, aes(x = "", y = count, fill = category)) +
    geom_col(width = 1) +
    coord_polar(theta = "y") +
    scale_fill_manual(values = .palette_for(length(lv))) +
    theme_void(base_size = .lab_style$base_size) +
    theme(legend.position = "right",
          plot.background = element_rect(fill = "white", colour = NA)) +
    guides(fill = guide_legend(ncol = 1, byrow = FALSE)) +
    labs(title = NULL, fill = NULL)
  .set_meta(p, "pie", d)
}
