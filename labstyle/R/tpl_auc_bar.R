#' AUC (DeLong 95% CI) of each predictor for a binary outcome, optionally
#' per dataset (`by`). Feeds lab_auc_bar().
lab_auc_table <- function(data, outcome, predictors, positive = NULL, direction = "<",
                          by = NULL, labels = NULL) {
  one <- function(dd) {
    y <- .as_binary(.col(dd, outcome), positive, outcome)
    do.call(rbind, lapply(seq_along(predictors), function(i) {
      x <- as.numeric(.col(dd, predictors[i]))
      ok <- !is.na(x) & !is.na(y)
      roc <- pROC::roc(response = y[ok], predictor = x[ok], levels = c(0, 1),
                       direction = direction, quiet = TRUE)
      ci <- as.numeric(pROC::ci.auc(roc))
      data.frame(predictor = (labels %||% predictors)[i], auc = ci[2],
                 lower = ci[1], upper = ci[3], n = sum(ok))
    }))
  }
  if (is.null(by)) return(one(data))
  groups <- split(data, .col(data, by))
  do.call(rbind, lapply(names(groups), function(g) cbind(dataset = g, one(groups[[g]]))))
}

#' AUC bars. Without `dataset`: one bar per predictor with CI error bars
#' (save_auc_barplot). With `dataset`: mean bar per predictor, + 1 SE whisker,
#' and one point per dataset (save_auc_comparison). Both from
#' melanoma_irAE/code/utils.R. Bars are ordered by AUC unless `order = FALSE`.
lab_auc_bar <- function(data, label = "predictor", auc = "auc", lower = "lower",
                        upper = "upper", dataset = NULL, order = TRUE, ylab = "AUC") {
  d <- data.frame(label = as.character(.col(data, label)), auc = as.numeric(.col(data, auc)))

  if (is.null(dataset)) {
    d$lower <- as.numeric(.col(data, lower))
    d$upper <- as.numeric(.col(data, upper))
    lv <- if (order) d$label[order(d$auc)] else unique(d$label)
    d$label <- factor(d$label, levels = lv)
    p <- ggplot(d, aes(x = label, y = auc, fill = label)) +
      geom_col(width = 0.7) +
      geom_errorbar(aes(ymin = lower, ymax = upper), width = 0.2, colour = "black",
                    linewidth = 0.5) +
      geom_hline(yintercept = 0.5, linetype = "dashed", colour = "grey", linewidth = 0.5) +
      scale_fill_manual(values = .palette_for(length(lv))) +
      coord_cartesian(ylim = c(0, 1)) +
      labs(x = NULL, y = ylab) +
      theme_lab(x_angle = 45, legend = "none")
    size <- c(max(2, 0.6 + 0.35 * length(lv)), 3.5)
    return(.set_meta(p, size, d))
  }

  d$dataset <- as.character(.col(data, dataset))
  means <- tapply(d$auc, d$label, mean, na.rm = TRUE)
  lv <- if (order) names(sort(means)) else unique(d$label)
  d$label <- factor(d$label, levels = lv)
  upper_se <- function(y) {
    y <- y[is.finite(y)]
    m <- mean(y)
    se <- if (length(y) > 1) stats::sd(y) / sqrt(length(y)) else 0
    data.frame(y = m, ymin = m, ymax = m + se)
  }
  p <- ggplot(d, aes(x = label, y = auc)) +
    stat_summary(fun = mean, geom = "col", width = 0.65, fill = "grey85",
                 colour = "black", linewidth = 0.35) +
    stat_summary(fun.data = upper_se, geom = "errorbar", width = 0.18,
                 linewidth = 0.35, colour = "black") +
    geom_point(aes(colour = dataset, group = dataset),
               position = position_dodge(width = 0.55), size = 2, alpha = 0.95) +
    geom_hline(yintercept = 0.5, linetype = "dashed", colour = "grey60", linewidth = 0.4) +
    scale_colour_manual(values = lab_colors("dataset", length(unique(d$dataset))), name = NULL) +
    coord_cartesian(ylim = c(0, 1)) +
    scale_y_continuous(breaks = seq(0, 1, 0.1), expand = expansion(mult = c(0, 0.02))) +
    labs(x = NULL, y = ylab) +
    theme_lab(x_angle = 45)
  size <- c(1.8 + 0.4 * length(lv), 3.5)
  .set_meta(p, size, as.data.frame(as.table(means), responseName = "mean_auc"))
}
