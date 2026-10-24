#' Cox model as a forest-plot table: one row per model term with HR, 95% CI
#' and p. `terms` are column names (factors get one row per non-reference
#' level). Adapted from fit_multivariable_cox in melanoma_irAE/code/utils.R.
lab_cox_table <- function(data, time, event, terms, event_value = NULL, labels = NULL) {
  df <- data.frame(time = as.numeric(.col(data, time)),
                   event = .as_binary(.col(data, event), event_value, event))
  for (t in terms) df[[t]] <- .col(data, t)
  df <- stats::na.omit(df)
  f <- stats::as.formula(paste("survival::Surv(time, event) ~",
                               paste(sprintf("`%s`", terms), collapse = " + ")))
  cs <- summary(survival::coxph(f, data = df))
  out <- data.frame(
    term = gsub("`", "", rownames(cs$conf.int)),
    estimate = cs$conf.int[, 1],
    lower = cs$conf.int[, 3],
    upper = cs$conf.int[, 4],
    p = cs$coefficients[, 5],
    n = nrow(df),
    row.names = NULL
  )
  if (!is.null(labels)) out$term <- labels
  out
}

#' Forest plot laid out as  estimate | label | interval | p,  as in
#' save_forest_plot (forestplot package) in melanoma_irAE/code/utils.R,
#' rebuilt in ggplot2 + patchwork.
lab_forest <- function(data, label = "term", estimate = "estimate", lower = "lower",
                       upper = "upper", p = "p", est_name = "HR", label_name = "Variable",
                       xlab = "Hazard ratio", ref = 1, xlim = NULL, xbreaks = NULL,
                       log = FALSE) {
  d <- data.frame(label = as.character(.col(data, label)),
                  est = as.numeric(.col(data, estimate)),
                  lower = as.numeric(.col(data, lower)),
                  upper = as.numeric(.col(data, upper)))
  d$p <- if (!is.null(p) && p %in% names(data)) as.numeric(data[[p]]) else NA_real_
  n <- nrow(d)
  d$y <- rev(seq_len(n))
  ylim <- c(0.5, n + 1.5)
  fs <- .lab_style$text$forest

  text_col <- function(values, header, hjust) {
    x <- if (hjust == 0) 0 else 1
    ggplot() +
      annotate("text", x = x, y = c(d$y, n + 1), label = c(values, header), hjust = hjust,
               fontface = c(rep("plain", n), "bold"), size = fs) +
      scale_x_continuous(limits = c(0, 1)) +
      scale_y_continuous(limits = ylim, expand = c(0, 0)) +
      coord_cartesian(clip = "off") +
      theme_void()
  }

  xlim <- xlim %||% range(c(ref, d$lower, d$upper), na.rm = TRUE)
  forest <- ggplot(d, aes(y = y)) +
    geom_vline(xintercept = ref, linewidth = 0.4, colour = "grey70") +
    geom_errorbar(aes(xmin = lower, xmax = upper), width = 0.25, orientation = "y",
                  linewidth = 0.5) +
    geom_point(aes(x = est), shape = 15, size = 3) +
    scale_y_continuous(limits = ylim, expand = c(0, 0)) +
    coord_cartesian(xlim = xlim) +
    labs(x = xlab, y = NULL) +
    theme_lab() +
    theme(axis.line.y = element_blank(), axis.text.y = element_blank(),
          axis.ticks.y = element_blank())
  if (log) {
    forest <- forest + scale_x_log10(breaks = xbreaks %||% waiver())
  } else if (!is.null(xbreaks)) {
    forest <- forest + scale_x_continuous(breaks = xbreaks)
  }

  out <- patchwork::wrap_plots(
    text_col(sprintf("%.3f", d$est), est_name, 0),
    text_col(d$label, label_name, 0),
    forest,
    text_col(format_p_value(d$p), "P-value", 1),
    nrow = 1, widths = c(0.7, 2, 1.6, 0.8)
  )
  stats <- data.frame(label = d$label, estimate = d$est, lower = d$lower,
                      upper = d$upper, p = d$p)
  # rows 0.85 cm apart as in the original (lineheight = unit(0.85, "cm"))
  .set_meta(out, c(5.5, 0.335 * (n + 1) + 0.9), stats)
}
