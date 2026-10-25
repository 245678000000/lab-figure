#' Event rate (%) per group as bars, with events/n above each bar. Two groups
#' get an odds-ratio bracket: OR (as in calc_group_rate_or), its Wald 95% CI
#' and Fisher's exact p. Adapted from save_irAE_barplot in
#' melanoma_irAE/code/utils.R.
lab_rate_bar <- function(data, group, outcome, positive = NULL, levels = NULL,
                         ylab = NULL, show_counts = TRUE, show_ci = TRUE, show_p = TRUE) {
  d <- stats::na.omit(data.frame(group = .as_group(.col(data, group), levels),
                                 y = .as_binary(.col(data, outcome), positive, outcome)))
  d$group <- droplevels(d$group)
  lv <- levels(d$group)
  rates <- do.call(rbind, lapply(lv, function(g) {
    yy <- d$y[d$group == g]
    data.frame(group = g, n = length(yy), events = sum(yy), rate = mean(yy) * 100)
  }))
  rates$group <- factor(rates$group, levels = lv)
  txt <- .lab_style$text$bar

  p <- ggplot(rates, aes(x = group, y = rate, fill = group)) +
    geom_col(colour = "black", width = 0.6) +
    scale_fill_manual(values = .palette_for(length(lv))) +
    labs(x = NULL, y = ylab %||% paste0(outcome, " (%)")) +
    theme_lab(legend = "none")
  top <- max(rates$rate)
  if (show_counts) {
    p <- p + geom_text(aes(y = rate + 2, label = paste0(events, "/", n)), vjust = 0, size = txt)
    top <- top + 9
  }

  stats <- rates
  ymax <- 100
  if (length(lv) == 2) {
    odds <- rates$rate / (100 - rates$rate)
    or <- odds[2] / odds[1]
    # 2x2 cells (events / non-events of group 2, then group 1); 0.5 added if any is empty
    cells <- c(rates$events[2], rates$n[2] - rates$events[2],
               rates$events[1], rates$n[1] - rates$events[1])
    if (any(cells == 0)) cells <- cells + 0.5
    log_or <- log(cells[1] * cells[4] / (cells[2] * cells[3]))
    ci <- exp(log_or + c(-1, 1) * stats::qnorm(0.975) * sqrt(sum(1 / cells)))
    fp <- stats::fisher.test(table(d$group, d$y))$p.value
    stats$or <- or
    stats$or_lower <- ci[1]
    stats$or_upper <- ci[2]
    stats$fisher_p <- fp

    lines <- c(paste0("OR = ", round(or, 1)),
               if (show_ci) sprintf("(%.1f-%.1f)", ci[1], ci[2]),
               if (show_p) paste0("p = ", format_p_value(fp)))
    br <- top + 6
    p <- p +
      annotate("segment", x = 1, xend = 2, y = br, yend = br, linewidth = 0.4) +
      annotate("segment", x = 1, xend = 1, y = br, yend = br - 4, linewidth = 0.4) +
      annotate("segment", x = 2, xend = 2, y = br, yend = br - 4, linewidth = 0.4) +
      annotate("text", x = 1.5, y = br + 3, vjust = 0, lineheight = 0.9, size = txt,
               label = paste(lines, collapse = "\n"))
    ymax <- max(100, br + 3 + 7.5 * length(lines))
  } else if (show_counts) {
    ymax <- max(100, top + 2)
  }
  p <- p + scale_y_continuous(limits = c(0, ymax), breaks = seq(0, 100, 25),
                              expand = expansion(mult = c(0, 0.02)))
  size <- if (length(lv) <= 2) "bar2" else c(0.6 + 0.45 * length(lv), 2.565)
  .set_meta(p, size, stats)
}
