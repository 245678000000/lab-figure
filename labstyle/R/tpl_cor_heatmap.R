#' Correlation heatmap with significance stars. Correlations and p values as
#' in get_cor_and_p (melanoma_irAE/code/utils.R); drawn with ggplot2 so it
#' combines with other panels.
#'
#' `vars` alone gives a square matrix (clustered when `cluster = TRUE`);
#' `vars_y` gives vars (rows) x vars_y (columns).
lab_cor_heatmap <- function(data, vars, vars_y = NULL, method = c("spearman", "pearson"),
                            cluster = TRUE, show_values = FALSE) {
  method <- match.arg(method)
  vy <- vars_y %||% vars
  r <- matrix(NA_real_, length(vars), length(vy), dimnames = list(vars, vy))
  pm <- r
  for (i in vars) for (j in vy) {
    ct <- suppressWarnings(stats::cor.test(as.numeric(.col(data, i)), as.numeric(.col(data, j)),
                                           method = method, exact = FALSE))
    r[i, j] <- unname(ct$estimate)
    pm[i, j] <- ct$p.value
  }
  row_order <- vars
  col_order <- vy
  if (cluster && is.null(vars_y) && length(vars) > 2) {
    hc <- stats::hclust(stats::as.dist(1 - r))
    row_order <- col_order <- vars[hc$order]
  }

  long <- data.frame(row = rep(rownames(r), times = ncol(r)),
                     col = rep(colnames(r), each = nrow(r)),
                     r = as.vector(r), p = as.vector(pm))
  long$row <- factor(long$row, levels = rev(row_order))
  long$col <- factor(long$col, levels = col_order)
  long$sig <- ifelse(long$p < 0.05, p_to_symbol(long$p), "")
  long$text <- if (show_values) sprintf("%.2f", long$r) else long$sig
  if (is.null(vars_y)) long$text[long$row == long$col] <- ""

  p <- ggplot(long, aes(x = col, y = row, fill = r)) +
    geom_tile(colour = "white", linewidth = 0.3) +
    geom_text(aes(label = text), size = .lab_style$text$heatmap, vjust = 0.75) +
    scale_fill_lab_diverging(name = paste(.title_case(method), "r")) +
    coord_fixed() +
    labs(x = NULL, y = NULL) +
    theme_lab(x_angle = 45) +
    theme(axis.line = element_blank(), axis.ticks = element_blank())
  label_w <- 0.075 * max(nchar(c(vars, vy)))
  size <- c(label_w + 0.3 * length(vy) + 1.2, label_w + 0.3 * length(vars) + 0.3)
  .set_meta(p, size, long[, c("row", "col", "r", "p")])
}

.title_case <- function(x) paste0(toupper(substring(x, 1, 1)), substring(x, 2))
