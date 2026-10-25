#' Correlation heatmap with significance stars. Correlations and p values as
#' in get_cor_and_p (melanoma_irAE/code/utils.R); stars use Benjamini-Hochberg
#' adjusted p by default, as in the HNSCC_Bcells heatmaps. Drawn with ggplot2
#' so it combines with other panels.
#'
#' `vars` alone gives a square matrix, clustered when `cluster = TRUE` and
#' drawn as its lower triangle (`triangle = "full"` draws both halves).
#' `vars_y` gives vars (rows) x vars_y (columns). `p_adjust` takes any
#' p.adjust() method or "none"; each pair is counted once. `show_values`
#' prints r with the stars under it. `note` adds a caption explaining the stars.
lab_cor_heatmap <- function(data, vars, vars_y = NULL, method = c("spearman", "pearson"),
                            cluster = TRUE, p_adjust = "BH", triangle = c("lower", "full"),
                            show_values = FALSE, note = TRUE) {
  method <- match.arg(method)
  triangle <- match.arg(triangle)
  square <- is.null(vars_y)
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
  if (cluster && square && length(vars) > 2) {
    hc <- stats::hclust(stats::as.dist(1 - r))
    row_order <- col_order <- vars[hc$order]
  }

  long <- data.frame(row = rep(rownames(r), times = ncol(r)),
                     col = rep(colnames(r), each = nrow(r)),
                     r = as.vector(r), p = as.vector(pm))
  ri <- match(long$row, row_order)
  ci <- match(long$col, col_order)
  if (square) {
    # one test per unordered pair: adjust over the lower triangle, mirror to the upper
    lower <- ri > ci
    adj <- stats::p.adjust(long$p[lower], method = p_adjust)
    key <- function(a, b) paste(pmin(a, b), pmax(a, b))
    long$p_adj <- adj[match(key(long$row, long$col), key(long$row[lower], long$col[lower]))]
  } else {
    long$p_adj <- stats::p.adjust(long$p, method = p_adjust)
  }
  long$sig <- ifelse(!is.na(long$p_adj) & long$p_adj < 0.05, p_to_symbol(long$p_adj), "")
  long$text <- if (show_values) {
    paste0(sprintf("%.2f", long$r), ifelse(long$sig == "", "", paste0("\n", long$sig)))
  } else {
    long$sig
  }
  if (square) long$text[ri == ci] <- ""
  stats <- long[if (square) ri > ci else TRUE, c("row", "col", "r", "p", "p_adj")]
  rownames(stats) <- NULL

  rows_shown <- row_order
  cols_shown <- col_order
  if (square && triangle == "lower") {
    long <- long[ri > ci, ]
    rows_shown <- row_order[-1]
    cols_shown <- col_order[-length(col_order)]
  }
  long$row <- factor(long$row, levels = rev(rows_shown))
  long$col <- factor(long$col, levels = cols_shown)

  p <- ggplot(long, aes(x = col, y = row, fill = r)) +
    geom_tile(colour = "white", linewidth = 0.3) +
    geom_text(aes(label = text), size = .lab_style$text$heatmap,
              vjust = if (show_values) 0.5 else 0.75, lineheight = 0.85) +
    scale_fill_lab_diverging(name = paste(.title_case(method), "r")) +
    coord_fixed() +
    labs(x = NULL, y = NULL) +
    theme_lab(x_angle = 90) +
    theme(axis.line = element_blank(), axis.ticks = element_blank())
  if (note) {
    p_name <- if (p_adjust == "none") "P" else paste0(p_adjust, "-adjusted P")
    p <- p +
      labs(caption = paste0(p_name, ": * < 0.05, ** < 0.01, *** < 0.001")) +
      theme(plot.caption.position = "plot", plot.caption = element_text(hjust = 0))
  }

  label_w <- 0.075 * max(nchar(c(vars, vy)))
  width <- label_w + 0.3 * length(cols_shown) + 1.2
  height <- label_w + 0.3 * length(rows_shown) + 0.3 + if (note) 0.3 else 0
  .set_meta(p, c(if (note) max(width, 3.6) else width, height), stats)
}

.title_case <- function(x) paste0(toupper(substring(x, 1, 1)), substring(x, 2))
