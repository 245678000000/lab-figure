#' ROC curve with AUC (DeLong 95% CI). Adapted from save_roc_plot /
#' save_roc_plot_with_youden in melanoma_irAE/code/utils.R.
#'
#' One predictor: black step curve with the AUC label. Several predictors:
#' one coloured curve each, AUCs in the legend. `direction = "<"` means higher
#' predictor values indicate the positive class. `show_n` adds the class sizes
#' under the AUC (single curve).
lab_roc <- function(data, outcome, predictor, positive = NULL, direction = "<",
                    labels = NULL, youden = FALSE, show_n = TRUE) {
  y_raw <- .col(data, outcome)
  y <- .as_binary(y_raw, positive, outcome)
  classes <- .binary_labels(y_raw, positive)
  labels <- labels %||% predictor
  curves <- lapply(predictor, function(pr) {
    x <- as.numeric(.col(data, pr))
    ok <- !is.na(x) & !is.na(y)
    roc <- pROC::roc(response = y[ok], predictor = x[ok], levels = c(0, 1),
                     direction = direction, quiet = TRUE)
    ci <- as.numeric(pROC::ci.auc(roc))
    df <- data.frame(fpr = 1 - roc$specificities, sensitivity = roc$sensitivities)
    df <- unique(df[order(df$fpr, df$sensitivity), ])
    list(roc = roc, df = df, auc = ci[2], lower = ci[1], upper = ci[3], n = sum(ok),
         n_pos = sum(y[ok] == 1), n_neg = sum(y[ok] == 0))
  })
  stats <- data.frame(
    predictor = labels,
    auc = vapply(curves, `[[`, numeric(1), "auc"),
    lower = vapply(curves, `[[`, numeric(1), "lower"),
    upper = vapply(curves, `[[`, numeric(1), "upper"),
    n = vapply(curves, `[[`, numeric(1), "n"),
    n_pos = vapply(curves, `[[`, numeric(1), "n_pos"),
    n_neg = vapply(curves, `[[`, numeric(1), "n_neg")
  )

  p <- ggplot() +
    geom_abline(slope = 1, intercept = 0, linetype = "dashed", colour = "gray70") +
    coord_cartesian(xlim = c(0, 1), ylim = c(0, 1)) +
    labs(x = "1 - Specificity", y = "Sensitivity") +
    theme_lab()

  if (length(curves) == 1) {
    cv <- curves[[1]]
    # short lines keep the label in the empty corner below the diagonal
    label <- paste(c(sprintf("AUC = %.2f", cv$auc),
                     sprintf("95%% CI %.2f-%.2f", cv$lower, cv$upper),
                     if (show_n) sprintf("n: %s %d, %s %d", classes[2], cv$n_pos,
                                         classes[1], cv$n_neg)),
                   collapse = "\n")
    p <- p +
      geom_step(data = cv$df, aes(x = fpr, y = sensitivity), direction = "vh",
                colour = "black", linewidth = 1) +
      annotate("text", x = 1, y = 0.03, hjust = 1, vjust = 0, size = .lab_style$text$roc,
               lineheight = 0.9, label = label)
    if (youden) {
      yc <- pROC::coords(cv$roc, x = "best", best.method = "youden",
                         ret = c("threshold", "sensitivity", "specificity"))[1, ]
      pt <- data.frame(fpr = 1 - yc$specificity, sensitivity = yc$sensitivity)
      p <- p +
        geom_point(data = pt, aes(x = fpr, y = sensitivity),
                   colour = lab_colors("accent"), size = 3) +
        annotate("text", x = pt$fpr, y = pt$sensitivity, hjust = -0.05, vjust = -0.5,
                 size = .lab_style$text$small,
                 label = paste0("Cutoff = ", signif(yc$threshold, 3)))
      stats$youden_cutoff <- yc$threshold
      stats$youden_sensitivity <- yc$sensitivity
      stats$youden_specificity <- yc$specificity
    }
    return(.set_meta(p, "roc", stats))
  }

  legend_labels <- sprintf("%s (AUC = %.2f)", labels, stats$auc)
  all <- do.call(rbind, lapply(seq_along(curves), function(i) {
    cbind(curves[[i]]$df, curve = legend_labels[i])
  }))
  all$curve <- factor(all$curve, levels = legend_labels)
  p <- p +
    geom_step(data = all, aes(x = fpr, y = sensitivity, colour = curve),
              direction = "vh", linewidth = 0.8) +
    scale_colour_manual(values = .palette_for(length(curves)), name = NULL) +
    theme(
      legend.position = "inside",
      legend.position.inside = c(0.98, 0.02),
      legend.justification = c(1, 0),
      legend.text = element_text(size = rel(0.75)),
      legend.key.height = unit(0.35, "cm")
    )
  .set_meta(p, "roc_multi", stats)
}
