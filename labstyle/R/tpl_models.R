# Prediction-model templates: nomogram, calibration curve, decision curve
# analysis and time-dependent ROC.

#' Nomogram for a logistic model (binary `outcome`) or, with `time` and
#' `event`, a Cox model with survival-probability axes at `times`.
#' Each predictor's effect is scaled to points (the largest effect spans
#' 0-100); total points map to the predicted probability.
lab_nomogram <- function(data, predictors, outcome = NULL, positive = NULL,
                         time = NULL, event = NULL, event_value = NULL, times = NULL,
                         time_unit = "months") {
  cox <- !is.null(time)
  if (cox && (is.null(event) || is.null(times))) stop("a Cox nomogram needs `event` and `times`", call. = FALSE)
  if (!cox && is.null(outcome)) stop("set `outcome` (logistic) or `time`/`event`/`times` (Cox)", call. = FALSE)
  safe <- paste0("v", seq_along(predictors))
  d <- as.data.frame(stats::setNames(lapply(predictors, function(v) .col(data, v)), safe))
  for (v in safe) if (is.character(d[[v]]) || is.logical(d[[v]])) d[[v]] <- factor(d[[v]])
  if (cox) {
    d$.time <- as.numeric(.col(data, time))
    d$.event <- .as_binary(.col(data, event), event_value, "event")
  } else {
    d$.y <- .as_binary(.col(data, outcome), positive)
  }
  d <- d[stats::complete.cases(d), ]
  f <- stats::reformulate(safe, response = if (cox) "survival::Surv(.time, .event)" else ".y")
  fit <- if (cox) survival::coxph(f, data = d) else stats::glm(f, data = d, family = stats::binomial())
  beta <- stats::coef(fit)

  # effect of each predictor at its tick values
  scales <- lapply(seq_along(safe), function(j) {
    x <- d[[safe[j]]]
    if (is.factor(x)) {
      values <- levels(x)
      effect <- c(0, unname(beta[paste0(safe[j], values[-1])]))
    } else {
      values <- pretty(range(x), n = 5)
      values <- values[values >= min(x) & values <= max(x)]
      if (length(values) < 2) values <- range(x)
      effect <- unname(beta[safe[j]]) * values
    }
    data.frame(row = predictors[j], value = as.character(values), effect = effect)
  })
  low <- vapply(scales, function(s) min(s$effect), numeric(1))
  spread <- vapply(scales, function(s) diff(range(s$effect)), numeric(1))
  unit <- max(spread) / 100                       # effect per point
  intercept <- if (cox) 0 else unname(beta[1])
  base <- intercept + sum(low)
  total_max <- sum(spread) / unit

  rows <- list(data.frame(row = "Points", value = as.character(seq(0, 100, 10)), x = seq(0, 100, 10)))
  for (j in seq_along(scales)) {
    s <- scales[[j]]
    rows[[length(rows) + 1]] <- data.frame(row = s$row, value = s$value, x = (s$effect - low[j]) / unit)
  }
  total_ticks <- pretty(c(0, total_max), n = 8)
  total_ticks <- total_ticks[total_ticks <= total_max]
  rows[[length(rows) + 1]] <- data.frame(row = "Total points", value = as.character(total_ticks),
                                         x = total_ticks / total_max * 100)
  # probability axes: total points at which the model reaches each probability
  add_axis <- function(name, probs, points_at) {
    tp <- points_at(probs)
    ok <- is.finite(tp) & tp >= 0 & tp <= total_max
    if (any(ok)) rows[[length(rows) + 1]] <<- data.frame(row = name, value = format(probs[ok]), x = tp[ok] / total_max * 100)
  }
  if (cox) {
    hazard <- survival::basehaz(fit, centered = FALSE)
    for (t in times) {
      h0 <- utils::tail(hazard$hazard[hazard$time <= t], 1)
      if (!length(h0) || h0 <= 0) next
      add_axis(sprintf("%s-%s survival", format(t), sub("s$", "", time_unit)), c(0.95, seq(0.9, 0.1, -0.1), 0.05),
               function(p) (log(-log(p) / h0) - base) / unit)
    }
  } else {
    add_axis("Predicted probability", c(0.05, seq(0.1, 0.9, 0.1), 0.95), function(p) (stats::qlogis(p) - base) / unit)
  }

  axes <- do.call(rbind, rows)
  names_in_order <- unique(axes$row)
  axes$y <- match(axes$row, rev(names_in_order))
  lines <- stats::aggregate(x ~ row + y, axes, function(v) c(min = min(v), max = max(v)))
  lines <- data.frame(row = lines$row, y = lines$y, x = lines$x[, "min"], xend = lines$x[, "max"])
  p <- ggplot(axes) +
    geom_segment(data = lines, aes(x = x, xend = xend, y = y, yend = y), linewidth = .geom$line) +
    geom_segment(aes(x = x, xend = x, y = y, yend = y + 0.12), linewidth = .geom$line) +
    geom_text(aes(x = x, y = y + 0.22, label = value), size = .lab_style$text$small, vjust = 0) +
    scale_y_continuous(breaks = seq_along(names_in_order), labels = rev(names_in_order),
                       expand = expansion(add = c(0.4, 0.6))) +
    scale_x_continuous(expand = expansion(mult = 0.04)) +
    labs(x = NULL, y = NULL) +
    theme_lab() +
    theme(axis.line = element_blank(), axis.ticks = element_blank(), axis.text.x = element_blank())

  co <- summary(fit)$coefficients
  co <- co[rownames(co) != "(Intercept)", , drop = FALSE]
  term <- rownames(co)
  for (j in seq_along(safe)) term <- sub(paste0("^", safe[j]), paste0(predictors[j], " "), term)
  ci <- suppressMessages(stats::confint.default(fit))[rownames(co), , drop = FALSE]
  s <- data.frame(term = trimws(term), estimate = co[, 1], ratio = exp(co[, 1]),
                  lower = exp(ci[, 1]), upper = exp(ci[, 2]), p = co[, ncol(co)],
                  model = if (cox) "Cox" else "logistic", n = nrow(d), row.names = NULL)
  names(s)[3] <- if (cox) "hr" else "or"
  .set_meta(p, c(5.5, min(12, 0.6 + 0.45 * length(names_in_order))), s)
}

#' Calibration curve for predicted probabilities: observed event rate per
#' quantile bin (with 95% exact CI) against the mean predicted probability.
#' Stats: Brier score, calibration intercept and slope, Hosmer-Lemeshow test.
lab_calibration <- function(data, outcome, predicted, positive = NULL, bins = 10) {
  y <- .as_binary(.col(data, outcome), positive)
  prob <- as.numeric(.col(data, predicted))
  keep <- !is.na(y) & !is.na(prob)
  y <- y[keep]
  prob <- prob[keep]
  if (any(prob < 0 | prob > 1)) stop("`predicted` must be probabilities between 0 and 1", call. = FALSE)
  g <- cut(prob, unique(stats::quantile(prob, seq(0, 1, length.out = bins + 1))), include.lowest = TRUE)
  b <- do.call(rbind, lapply(split(seq_along(y), g), function(i) {
    ci <- stats::binom.test(sum(y[i]), length(i))$conf.int
    data.frame(predicted = mean(prob[i]), observed = mean(y[i]), lower = ci[1], upper = ci[2],
               events = sum(y[i]), n = length(i))
  }))
  lp <- stats::qlogis(pmin(pmax(prob, 1e-6), 1 - 1e-6))
  slope <- unname(stats::coef(stats::glm(y ~ lp, family = stats::binomial()))[2])
  intercept <- unname(stats::coef(stats::glm(y ~ 1, offset = lp, family = stats::binomial()))[1])
  expected <- b$predicted * b$n
  hl <- sum((b$events - expected)^2 / (expected * (1 - b$predicted)))
  hl_df <- nrow(b) - 2
  s <- data.frame(n = length(y), brier = mean((prob - y)^2), intercept = intercept, slope = slope,
                  hl_chi2 = hl, hl_df = hl_df, hl_p = stats::pchisq(hl, hl_df, lower.tail = FALSE))
  label <- sprintf("Brier = %.3f\nSlope = %.2f\nIntercept = %.2f", s$brier, s$slope, s$intercept)
  p <- ggplot(b, aes(predicted, observed)) +
    # finite segment, not geom_abline: abline paths run off the page and trip the collision audit
    annotate("segment", x = 0, y = 0, xend = 1, yend = 1, linetype = 2, linewidth = .geom$thin, colour = .neutral("guide")) +
    geom_errorbar(aes(ymin = lower, ymax = upper), width = 0.02, linewidth = .geom$thin,
                  colour = lab_colors("binary")[1]) +
    geom_line(colour = lab_colors("binary")[1], linewidth = .geom$line) +
    geom_point(colour = lab_colors("binary")[1], size = .geom$point) +
    annotate("text", x = 1, y = 0.02, label = label, hjust = 1, vjust = 0, size = .lab_style$text$small) +
    coord_equal(xlim = c(0, 1), ylim = c(0, 1)) +
    labs(x = "Predicted probability", y = "Observed proportion") +
    theme_lab()
  attr(p, "lab_tables") <- list(calibration_bins = b)
  .set_meta(p, c(3, 3), s)
}

#' Decision curve analysis: net benefit of each predicted-probability column
#' across threshold probabilities, against treating everyone or no one.
lab_dca <- function(data, outcome, predictors, positive = NULL, labels = NULL,
                    thresholds = seq(0.01, 0.99, by = 0.01)) {
  y <- .as_binary(.col(data, outcome), positive)
  probs <- as.data.frame(lapply(predictors, function(v) as.numeric(.col(data, v))))
  keep <- !is.na(y) & stats::complete.cases(probs)
  y <- y[keep]
  probs <- probs[keep, , drop = FALSE]
  if (any(probs < 0 | probs > 1)) stop("predictors must be probabilities between 0 and 1", call. = FALSE)
  names(probs) <- labels %||% predictors
  n <- length(y)
  prevalence <- mean(y)
  odds <- thresholds / (1 - thresholds)
  net <- function(prob) {
    vapply(seq_along(thresholds), function(k) {
      treat <- prob >= thresholds[k]
      sum(treat & y == 1) / n - sum(treat & y == 0) / n * odds[k]
    }, numeric(1))
  }
  curves <- c(lapply(names(probs), function(m) data.frame(model = m, threshold = thresholds, net_benefit = net(probs[[m]]))),
              list(data.frame(model = "Treat all", threshold = thresholds, net_benefit = prevalence - (1 - prevalence) * odds),
                   data.frame(model = "Treat none", threshold = thresholds, net_benefit = 0)))
  s <- do.call(rbind, curves)
  s$model <- factor(s$model, levels = c(names(probs), "Treat all", "Treat none"))
  colours <- c(.palette_for(ncol(probs)), "grey60", "black")
  bottom <- -0.05
  shown <- s
  shown$net_benefit[shown$net_benefit < bottom] <- NA   # curves stop at the bottom of the plot
  p <- ggplot(shown, aes(threshold, net_benefit, colour = model, linetype = model)) +
    geom_line(linewidth = .geom$line, na.rm = TRUE) +
    scale_colour_manual(values = colours, name = NULL) +
    scale_linetype_manual(values = c(rep("solid", ncol(probs)), "dashed", "solid"), name = NULL) +
    scale_x_continuous(breaks = seq(0, 1, 0.25), labels = c("0", "0.25", "0.5", "0.75", "1")) +
    coord_cartesian(ylim = c(bottom, max(prevalence, s$net_benefit) * 1.05)) +
    labs(x = "Threshold probability", y = "Net benefit") +
    theme_lab()
  .set_meta(p, c(4.2, 3), s)
}

#' Time-dependent ROC at each of `times`: cases had the event before t,
#' controls are still event-free after t, and cases are weighted by the
#' inverse Kaplan-Meier probability of remaining uncensored. This is the
#' "marginal" estimator of timeROC::timeROC (AUCs agree to about 1e-5).
#' `direction = ">"` if lower marker values mean higher risk.
lab_time_roc <- function(data, time, event, predictor, times, event_value = NULL, direction = "<",
                         time_unit = "months") {
  tt <- as.numeric(.col(data, time))
  ev <- .as_binary(.col(data, event), event_value, "event")
  marker <- as.numeric(.col(data, predictor))
  keep <- stats::complete.cases(tt, ev, marker)
  tt <- tt[keep]; ev <- ev[keep]; marker <- marker[keep]
  if (direction == ">") marker <- -marker
  cens <- survival::survfit(survival::Surv(tt, 1 - ev) ~ 1)
  censor_surv <- stats::stepfun(cens$time, c(1, cens$surv))   # G(t), right-continuous

  curves <- list()
  s <- list()
  for (t in times) {
    case <- tt < t & ev == 1
    control <- tt > t
    if (!any(case) || !any(control)) next
    w <- 1 / censor_surv(tt[case] - 1e-9)                     # 1 / G(T_i-)
    cuts <- sort(unique(marker), decreasing = TRUE)
    w_at <- tapply(w, factor(marker[case], levels = cuts), sum)
    c_at <- tapply(control[control], factor(marker[control], levels = cuts), sum)
    w_at[is.na(w_at)] <- 0
    c_at[is.na(c_at)] <- 0
    tpr <- c(0, cumsum(w_at) / sum(w))
    fpr <- c(0, cumsum(c_at) / sum(control))
    auc <- sum(diff(fpr) * (utils::head(tpr, -1) + utils::tail(tpr, -1)) / 2)
    label <- sprintf("%s %s: AUC = %.2f", format(t), time_unit, auc)
    curves[[length(curves) + 1]] <- data.frame(time = label, fpr = fpr, tpr = tpr)
    s[[length(s) + 1]] <- data.frame(time = t, auc = auc, cases = sum(case), controls = sum(control))
  }
  if (!length(curves)) stop("no time point has both cases and controls", call. = FALSE)
  z <- do.call(rbind, curves)
  z$time <- factor(z$time, levels = unique(z$time))
  p <- ggplot(z, aes(fpr, tpr, colour = time)) +
    annotate("segment", x = 0, y = 0, xend = 1, yend = 1, linetype = 2, linewidth = .geom$thin, colour = .neutral("guide")) +
    geom_path(linewidth = .geom$line) +
    scale_colour_manual(values = .palette_for(nlevels(z$time)), name = NULL) +
    coord_equal(xlim = c(0, 1), ylim = c(0, 1)) +
    labs(x = "1 - Specificity", y = "Sensitivity") +
    theme_lab() +
    theme(legend.position = "inside", legend.position.inside = c(0.98, 0.02),
          legend.justification = c(1, 0), legend.text = element_text(size = rel(0.75)),
          legend.key.height = unit(0.35, "cm"))
  .set_meta(p, lab_sizes()$roc_multi, do.call(rbind, s))
}
