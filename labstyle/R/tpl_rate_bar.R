#' Event rate (%) per group as bars; two groups get an odds-ratio bracket.
#' Adapted from save_irAE_barplot / calc_group_rate_or in
#' melanoma_irAE/code/utils.R. Fisher's exact p is in lab_stats().
lab_rate_bar <- function(data, group, outcome, positive = NULL, levels = NULL,
                         ylab = NULL, show_p = FALSE) {
  d <- stats::na.omit(data.frame(group = .as_group(.col(data, group), levels),
                                 y = .as_binary(.col(data, outcome), positive, outcome)))
  d$group <- droplevels(d$group)
  lv <- levels(d$group)
  rates <- do.call(rbind, lapply(lv, function(g) {
    yy <- d$y[d$group == g]
    data.frame(group = g, n = length(yy), events = sum(yy), rate = mean(yy) * 100)
  }))
  rates$group <- factor(rates$group, levels = lv)

  p <- ggplot(rates, aes(x = group, y = rate, fill = group)) +
    geom_col(colour = "black", width = 0.6) +
    scale_fill_manual(values = .palette_for(length(lv))) +
    labs(x = NULL, y = ylab %||% paste0(outcome, " (%)")) +
    ylim(0, 100) +
    theme_lab(legend = "none")

  stats <- rates
  if (length(lv) == 2) {
    odds <- rates$rate / (100 - rates$rate)
    or <- round(odds[2] / odds[1], 1)
    fp <- stats::fisher.test(table(d$group, d$y))$p.value
    stats$or <- or
    stats$fisher_p <- fp
    label <- paste0("OR = ", or, if (show_p) paste0("\np = ", format_p_value(fp)) else "")
    p <- p +
      annotate("segment", x = 1, xend = 2, y = 90, yend = 90, linewidth = 0.4) +
      annotate("segment", x = 1, xend = 1, y = 90, yend = 86, linewidth = 0.4) +
      annotate("segment", x = 2, xend = 2, y = 90, yend = 86, linewidth = 0.4) +
      annotate("text", x = 1.5, y = 97, label = label, size = .lab_style$text$bar)
  }
  size <- if (length(lv) <= 2) "bar2" else c(0.6 + 0.45 * length(lv), 2.565)
  .set_meta(p, size, stats)
}
