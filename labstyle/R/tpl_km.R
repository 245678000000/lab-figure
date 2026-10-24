#' Kaplan-Meier curves with a number-at-risk table. Adapted from save_km_plot /
#' save_km_plot2 in melanoma_irAE/code/utils.R, rebuilt in plain ggplot2 so the
#' result combines with other panels via patchwork.
#'
#' Groups come from `group` (an existing column) or from `score` split at
#' `cutoff` ("median" or a number) into Low / High. Two groups get
#' HR (95% CI) and p from a univariable Cox model with the first group as
#' reference; more groups get a log-rank p.
lab_km <- function(data, time, event, group = NULL, score = NULL, cutoff = "median",
                   levels = NULL, labels = NULL, event_value = NULL,
                   xlab = "Time (months)", ylab = "Survival probability",
                   xmax = NULL, break_by = NULL, risk_table = TRUE, show_stats = TRUE) {
  tt <- as.numeric(.col(data, time))
  ev <- .as_binary(.col(data, event), event_value, event)
  if (!is.null(group)) {
    g <- .as_group(.col(data, group), levels)
    threshold <- NA_real_
  } else if (!is.null(score)) {
    s <- as.numeric(.col(data, score))
    threshold <- if (identical(cutoff, "median")) stats::median(s, na.rm = TRUE) else as.numeric(cutoff)
    g <- factor(ifelse(s > threshold, "High", "Low"), levels = c("Low", "High"))
  } else {
    stop("give either group = (a column) or score = (a numeric column to split)", call. = FALSE)
  }
  df <- stats::na.omit(data.frame(time = tt, event = ev, group = g))
  df$group <- droplevels(df$group)
  if (!is.null(labels)) levels(df$group) <- labels
  lv <- levels(df$group)
  cols <- .palette_for(length(lv))

  fit <- survival::survfit(survival::Surv(time, event) ~ group, data = df)
  strata <- factor(sub("^group=", "", rep(names(fit$strata), fit$strata)), levels = lv)
  cd <- rbind(
    data.frame(time = 0, surv = 1, n.censor = 0, group = factor(lv, levels = lv)),
    data.frame(time = fit$time, surv = fit$surv, n.censor = fit$n.censor, group = strata)
  )

  xmax <- xmax %||% max(df$time)
  break_by <- break_by %||% diff(pretty(c(0, xmax)))[1]
  breaks <- seq(0, xmax, by = break_by)
  xlim <- c(-0.06 * xmax, xmax)

  p <- ggplot(cd, aes(x = time, y = surv, colour = group)) +
    geom_step(linewidth = 1) +
    geom_point(data = cd[cd$n.censor > 0, ], shape = 3, size = 2, show.legend = FALSE) +
    scale_colour_manual(values = cols, name = NULL) +
    scale_x_continuous(breaks = breaks) +
    coord_cartesian(xlim = xlim, ylim = c(0, 1)) +
    labs(x = xlab, y = ylab) +
    theme_lab() +
    theme(
      legend.position = "inside",
      legend.position.inside = c(1, 1),
      legend.justification = c(1, 1),
      legend.key.height = unit(0.4, "cm"),
      legend.text = element_text(size = rel(0.9)),
      plot.margin = margin(0.2, 0.2, 0, 0.2, "cm")
    )

  if (length(lv) == 2) {
    cs <- summary(survival::coxph(survival::Surv(time, event) ~ group, data = df))
    stats <- data.frame(hr = cs$conf.int[1, 1], lower = cs$conf.int[1, 3],
                        upper = cs$conf.int[1, 4], p = cs$coefficients[1, 5],
                        test = "cox", reference = lv[1], cutoff = threshold, n = nrow(df))
    label <- sprintf("HR = %.2f\n(%.2f-%.2f)\np = %s",
                     stats$hr, stats$lower, stats$upper, format_p_value(stats$p))
  } else {
    sd <- survival::survdiff(survival::Surv(time, event) ~ group, data = df)
    stats <- data.frame(p = stats::pchisq(sd$chisq, length(sd$n) - 1, lower.tail = FALSE),
                        test = "logrank", cutoff = threshold, n = nrow(df))
    label <- paste0("Log-rank\np = ", format_p_value(stats$p))
  }
  if (show_stats) {
    pos <- .km_label_pos(cd, xmax)
    p <- p + annotate("text", x = pos$x, y = pos$y, hjust = pos$hjust, vjust = pos$vjust,
                      size = .lab_style$text$km, label = label, colour = "black",
                      lineheight = 0.9)
  }
  if (!risk_table) return(.set_meta(p, "km", stats))

  rs <- summary(fit, times = breaks, extend = TRUE)
  rt <- data.frame(time = rs$time, n = rs$n.risk,
                   group = factor(sub("^group=", "", rs$strata), levels = lv))
  tab <- ggplot(rt, aes(x = time, y = group)) +
    geom_text(aes(label = n, colour = group), size = .lab_style$text$small) +
    scale_colour_manual(values = cols, guide = "none") +
    scale_y_discrete(limits = rev(lv)) +
    scale_x_continuous(breaks = breaks) +
    coord_cartesian(xlim = xlim) +
    labs(title = "Number at risk", x = NULL, y = NULL) +
    theme_void(base_size = .lab_style$base_size) +
    theme(plot.title = element_text(size = rel(0.8), hjust = 0),
          plot.margin = margin(0, 0.2, 0.1, 0.2, "cm"))

  out <- patchwork::wrap_plots(p, tab, ncol = 1, heights = c(3, 1))
  .set_meta(out, "km", stats)
}

# Spot for the 3-line HR / CI / p label that the curves cross least:
# bottom-left, bottom-right, right side under the legend, or bottom-middle.
# Boxes are the label's approximate extent as fractions of the axes.
.km_label_pos <- function(cd, xmax) {
  boxes <- list(
    list(x = 0, y = 0.02, hjust = 0, vjust = 0, xr = c(0, 0.45), yr = c(0, 0.34)),
    list(x = xmax, y = 0.02, hjust = 1, vjust = 0, xr = c(0.55, 1), yr = c(0, 0.34)),
    list(x = xmax, y = 0.64, hjust = 1, vjust = 1, xr = c(0.55, 1), yr = c(0.3, 0.66)),
    list(x = 0.5 * xmax, y = 0.02, hjust = 0.5, vjust = 0, xr = c(0.28, 0.72), yr = c(0, 0.34))
  )
  grid <- seq(0, xmax, length.out = 60)
  surv_at <- lapply(split(cd, cd$group), function(g) {
    g <- g[order(g$time), ]
    stats::approx(g$time, g$surv, xout = grid, method = "constant", f = 0, rule = 2,
                  ties = "ordered")$y
  })
  hits <- vapply(boxes, function(b) {
    in_x <- grid >= b$xr[1] * xmax & grid <= b$xr[2] * xmax
    sum(vapply(surv_at, function(s) sum(in_x & s >= b$yr[1] & s <= b$yr[2]), numeric(1)))
  }, numeric(1))
  boxes[[which.min(hits)]]
}
