# Omics and sample-check templates, moved here from the AISI-figure app
# (agent-app/bio.py) so that figure scripts call one function per chart.
# Plots and statistics are unchanged from that code.

# Point sizes and line widths shared by these templates.
.geom <- list(point = 2, point_dense = 0.5, curve = 1, line = 0.5, thin = 0.3)
.neutral <- function(which) {
  switch(which,
         other = lab_colors("categorical")[5],
         guide = lab_colors("categorical")[9],
         light = "grey90",
         missing = "grey85")
}

.logp <- function(x) -log10(pmax(x, 1e-300))
.percent_labels <- function(x) paste0(round(100 * x), "%")

# Canvas for heatmap-like charts: 0.3 in per cell plus room for the labels.
.matrix_size <- function(rows, columns, row_labels, column_labels, legend_labels = character()) {
  label_space <- 0.075 * max(nchar(c(as.character(row_labels), as.character(column_labels), "")))
  guide_space <- if (length(legend_labels)) 0.075 * max(nchar(legend_labels)) + 0.8 else 0
  pmin(c(16, 18), pmax(c(lab_sizes()$wide[1], lab_sizes()$single[2]),
                       c(label_space + 0.3 * columns + 1.2 + guide_space, label_space + 0.3 * rows + 0.6)))
}

# Canvas for charts with one labelled row per category.
.category_size <- function(rows, labels, legend = FALSE) {
  label_space <- 0.075 * max(nchar(c(as.character(labels), "")))
  pmin(c(16, 18), c(max(lab_sizes()$wide[1], label_space + 2.3 + if (legend) 1.2 else 0),
                    max(lab_sizes()$single[2], 0.3 * rows + 0.8)))
}

.wide_square <- function() c(lab_sizes()$wide[1], lab_sizes()$roc_multi[2])

# ---- differential expression -------------------------------------------

.de_table <- function(data, label, effect, padj, p_threshold, effect_threshold) {
  z <- data.frame(gene = .col(data, label), effect = .col(data, effect), padj = .col(data, padj))
  up <- z$padj < p_threshold & z$effect >= effect_threshold
  down <- z$padj < p_threshold & z$effect <= -effect_threshold
  z$status <- factor(ifelse(up, "Up", ifelse(down, "Down", "Other")), levels = c("Down", "Other", "Up"))
  z$plot_y <- .logp(z$padj)
  z
}

.de_finish <- function(p, z, p_threshold, effect_threshold) {
  p <- p +
    scale_colour_manual(values = c(Down = lab_colors("binary")[1], Other = .neutral("other"),
                                   Up = lab_colors("binary")[2]), drop = FALSE) +
    theme_lab()
  s <- data.frame(status = levels(z$status), genes = as.integer(table(z$status)),
                  effect_threshold = effect_threshold, p_threshold = p_threshold)
  .set_meta(p, .wide_square(), s)
}

#' Volcano plot from a finished differential-expression table. All genes are
#' kept; the `label_count` most significant up/down genes are labelled.
lab_volcano <- function(data, label, effect, padj, p_threshold = 0.05, effect_threshold = 1,
                        label_count = 10) {
  z <- .de_table(data, label, effect, padj, p_threshold, effect_threshold)
  p <- ggplot(z, aes(effect, plot_y, colour = status)) +
    geom_point(size = .geom$point, alpha = 0.7) +
    geom_vline(xintercept = c(-effect_threshold, effect_threshold), linetype = 2,
               linewidth = .geom$thin, colour = .neutral("guide")) +
    geom_hline(yintercept = .logp(p_threshold), linetype = 2, linewidth = .geom$thin,
               colour = .neutral("guide")) +
    labs(x = "log2 fold change", y = "-log10(adjusted P)")
  if (label_count > 0) {
    candidates <- z[z$status != "Other", ]
    top <- utils::head(candidates[order(candidates$padj, -abs(candidates$effect)), ], label_count)
    p <- p + ggrepel::geom_text_repel(data = top, aes(label = gene), size = .lab_style$text$small,
                                      max.overlaps = Inf, seed = 42, box.padding = 0.4,
                                      point.padding = 0.2, show.legend = FALSE, max.time = 1)
  }
  .de_finish(p, z, p_threshold, effect_threshold)
}

#' MA plot: mean expression against log2 fold change.
lab_ma <- function(data, label, mean, effect, padj, p_threshold = 0.05, effect_threshold = 1) {
  z <- .de_table(data, label, effect, padj, p_threshold, effect_threshold)
  z$mean <- .col(data, mean)
  p <- ggplot(z, aes(mean, effect, colour = status)) +
    geom_point(size = .geom$point, alpha = 0.7) +
    geom_hline(yintercept = c(-effect_threshold, 0, effect_threshold), linetype = 2,
               linewidth = .geom$thin, colour = .neutral("guide")) +
    labs(x = "Mean expression (input units)", y = "log2 fold change")
  .de_finish(p, z, p_threshold, effect_threshold)
}

# ---- matrices -----------------------------------------------------------

# Rows = `label`, columns = `features`; optional z-score by row or column.
.feature_matrix <- function(data, label, features, scaling) {
  m <- as.matrix(data[, features, drop = FALSE])
  rownames(m) <- as.character(.col(data, label))
  if (scaling == "row_z") { m <- t(scale(t(m))); m[is.nan(m)] <- 0 }
  if (scaling == "column_z") { m <- scale(m); m[is.nan(m)] <- 0 }
  m
}

.tile_heatmap <- function(m, fill_name, diverging) {
  z <- data.frame(row = rep(rownames(m), times = ncol(m)), column = rep(colnames(m), each = nrow(m)),
                  value = as.vector(m))
  z$row <- factor(z$row, levels = rev(rownames(m)))
  z$column <- factor(z$column, levels = colnames(m))
  p <- ggplot(z, aes(column, row, fill = value)) +
    geom_tile() +
    labs(x = NULL, y = NULL, fill = fill_name) +
    theme_lab(x_angle = 45) +
    theme(panel.grid = element_blank())
  p <- p + if (diverging) {
    scale_fill_gradient2(low = lab_colors("binary")[1], mid = "white", high = lab_colors("binary")[2],
                         midpoint = 0, na.value = .neutral("missing"))
  } else {
    scale_fill_gradient(low = "white", high = lab_colors("binary")[1], na.value = .neutral("missing"))
  }
  .set_meta(p, .matrix_size(nrow(m), ncol(m), rownames(m), colnames(m)), z)
}

#' Expression heatmap: one row per gene (`label`), one column per sample
#' (`features`). `scaling` is "none", "row_z" or "column_z".
lab_expression_heatmap <- function(data, label, features, scaling = "none") {
  m <- .feature_matrix(data, label, features, scaling)
  .tile_heatmap(m, scaling, diverging = scaling != "none")
}

#' Euclidean distance between samples (rows) over the chosen features.
lab_sample_distance <- function(data, label, features, scaling = "none") {
  m <- as.matrix(stats::dist(.feature_matrix(data, label, features, scaling), method = "euclidean"))
  .tile_heatmap(m, "Euclidean distance", diverging = FALSE)
}

#' PCA of the chosen features (rows are samples). Coordinates and loadings
#' are kept in attr(p, "lab_tables") and written by the app's finish().
lab_pca <- function(data, label, features, group = NULL, scaling = "none") {
  m <- as.matrix(data[, features, drop = FALSE])
  if (scaling == "row_z") m <- t(scale(t(m)))
  fit <- stats::prcomp(m, center = TRUE, scale. = scaling == "column_z")
  variance <- fit$sdev^2 / sum(fit$sdev^2)
  z <- data.frame(sample = .col(data, label), PC1 = fit$x[, 1], PC2 = fit$x[, 2])
  axes <- labs(x = sprintf("PC1 (%.1f%%)", 100 * variance[1]), y = sprintf("PC2 (%.1f%%)", 100 * variance[2]))
  if (is.null(group)) {
    p <- ggplot(z, aes(PC1, PC2)) + geom_point(size = .geom$point, colour = lab_colors("binary")[1]) + axes + theme_lab()
  } else {
    z$group <- factor(.col(data, group))
    p <- ggplot(z, aes(PC1, PC2, colour = group)) +
      geom_point(size = .geom$point) +
      scale_colour_manual(values = .palette_for(nlevels(z$group)), name = group) +
      axes + theme_lab()
  }
  s <- data.frame(component = paste0("PC", seq_along(variance)), variance_explained = variance)
  attr(p, "lab_tables") <- list(pca_coordinates = z, pca_loadings = fit$rotation)
  .set_meta(p, lab_sizes()$roc_multi, s)
}

#' Share of missing values in each chosen column.
lab_missingness <- function(data, features) {
  s <- data.frame(column = features,
                  missing = vapply(data[, features, drop = FALSE], function(x) sum(is.na(x)), integer(1)),
                  rows = nrow(data))
  s$fraction <- s$missing / s$rows
  p <- ggplot(s, aes(stats::reorder(column, fraction), fraction)) +
    geom_col(fill = lab_colors("binary")[1], width = 0.7) +
    coord_flip() +
    scale_y_continuous(labels = .percent_labels, limits = c(0, 1)) +
    labs(x = NULL, y = "Missing values") +
    theme_lab()
  .set_meta(p, .category_size(length(features), features), s)
}

# ---- single cell --------------------------------------------------------

#' Existing UMAP / t-SNE coordinates coloured by cluster or cell type.
lab_embedding <- function(data, x, y, group) {
  z <- data.frame(x = .col(data, x), y = .col(data, y), group = factor(.col(data, group)))
  p <- ggplot(z, aes(x, y, colour = group)) +
    geom_point(size = .geom$point_dense, alpha = 0.8) +
    scale_colour_manual(values = .palette_for(nlevels(z$group)), name = group) +
    theme_lab() + coord_equal() +
    labs(x = x, y = y)
  .set_meta(p, lab_sizes()$roc_multi, data.frame(group = levels(z$group), n = as.integer(table(z$group))))
}

#' FeaturePlot: existing coordinates coloured by expression or a score.
lab_feature <- function(data, x, y, value) {
  z <- data.frame(x = .col(data, x), y = .col(data, y), value = .col(data, value))
  p <- ggplot(z, aes(x, y, colour = value)) +
    geom_point(size = .geom$point_dense, alpha = 0.85) +
    scale_colour_gradient(low = .neutral("light"), high = lab_colors("binary")[2], name = value) +
    theme_lab() + coord_equal() +
    labs(x = x, y = y)
  s <- data.frame(n = nrow(z), min = min(z$value), max = max(z$value), mean = mean(z$value))
  .set_meta(p, lab_sizes()$roc_multi, s)
}

.dot_matrix <- function(z, value, size_name) {
  p <- ggplot(z, aes(group, label, size = size, colour = value)) +
    geom_point() +
    scale_size_continuous(range = c(.geom$point_dense, .geom$point * 3), name = size_name) +
    scale_colour_gradient(low = .neutral("missing"), high = lab_colors("binary")[2], name = value) +
    labs(x = NULL, y = NULL) +
    theme_lab(x_angle = 45)
  size <- .matrix_size(length(unique(z$label)), length(unique(z$group)), unique(z$label),
                       unique(z$group), legend_labels = c(value, size_name))
  .set_meta(p, size, z)
}

#' Marker DotPlot: one row per gene x cell group; `pct` is percent (0-100).
lab_marker_dot <- function(data, label, group, value, pct) {
  z <- data.frame(label = .col(data, label), group = .col(data, group), value = .col(data, value))
  z$size <- .col(data, pct)
  .dot_matrix(z, value, "Percent expressing")
}

#' Ligand-receptor bubble matrix from an existing communication analysis.
lab_lr_dot <- function(data, label, group, value, padj) {
  z <- data.frame(label = .col(data, label), group = .col(data, group), value = .col(data, value))
  z$size <- .logp(.col(data, padj))
  z$padj <- .col(data, padj)
  .dot_matrix(z, value, "-log10(adjusted P)")
}

#' Stacked cell composition per sample. Without `count`, each row is one cell.
lab_composition <- function(data, sample, group, count = NULL) {
  z <- data.frame(sample = .col(data, sample), group = .col(data, group),
                  count = if (is.null(count)) 1 else .col(data, count))
  z <- stats::aggregate(count ~ sample + group, z, sum)
  z$fraction <- z$count / stats::ave(z$count, z$sample, FUN = sum)
  z$group <- factor(z$group)
  p <- ggplot(z, aes(sample, fraction, fill = group)) +
    geom_col(width = 0.75) +
    scale_fill_manual(values = .palette_for(nlevels(z$group)), name = group) +
    scale_y_continuous(labels = .percent_labels) +
    labs(x = sample, y = "Cell composition") +
    theme_lab(x_angle = 45)
  .set_meta(p, lab_sizes()$wide, z)
}

# ---- enrichment ---------------------------------------------------------

.gene_ratio <- function(v) {
  vapply(strsplit(as.character(v), "/", fixed = TRUE), function(a) {
    if (length(a) == 2) as.numeric(a[1]) / as.numeric(a[2]) else as.numeric(a[1])
  }, numeric(1))
}

#' Enrichment bubble chart from an existing GO/KEGG table.
#' `ratio` may be a number or "a/b" (clusterProfiler GeneRatio).
lab_enrichment_dot <- function(data, label, ratio, count, padj) {
  z <- data.frame(term = .col(data, label), padj = .col(data, padj))
  z$significance <- .logp(z$padj)
  z$ratio <- .gene_ratio(.col(data, ratio))
  z$count <- .col(data, count)
  p <- ggplot(z, aes(ratio, stats::reorder(term, significance), size = count, colour = significance)) +
    geom_point() +
    scale_colour_gradient(low = .neutral("other"), high = lab_colors("binary")[2], name = "-log10(adjusted P)") +
    scale_size_continuous(range = c(.geom$point, .geom$point * 3), name = "Gene count") +
    labs(x = "Gene ratio", y = NULL) +
    theme_lab()
  .set_meta(p, .category_size(nrow(z), z$term, legend = TRUE), z)
}

#' Enrichment bar chart: -log10(adjusted P) per term.
lab_enrichment_bar <- function(data, label, padj) {
  z <- data.frame(term = .col(data, label), padj = .col(data, padj))
  z$significance <- .logp(z$padj)
  p <- ggplot(z, aes(significance, stats::reorder(term, significance))) +
    geom_col(fill = lab_colors("binary")[1], width = 0.7) +
    labs(x = "-log10(adjusted P)", y = NULL) +
    theme_lab()
  .set_meta(p, .category_size(nrow(z), z$term), z)
}

#' Running enrichment score of one gene set, as supplied (no NES or P computed).
lab_gsea <- function(data, rank, value) {
  z <- data.frame(rank = .col(data, rank), running_ES = .col(data, value))
  z <- z[order(z$rank), ]
  p <- ggplot(z, aes(rank, running_ES)) +
    geom_hline(yintercept = 0, colour = .neutral("guide"), linewidth = .geom$thin) +
    geom_line(colour = lab_colors("binary")[1], linewidth = .geom$curve) +
    labs(x = "Rank in ordered gene list", y = "Running enrichment score (input)") +
    theme_lab()
  s <- data.frame(input_points = nrow(z), max_running_ES = max(z$running_ES), min_running_ES = min(z$running_ES))
  .set_meta(p, lab_sizes()$wide, s)
}

# ---- paired and correlation ---------------------------------------------

.paired_table <- function(data, pair, group, value, reference) {
  z <- data.frame(pair = as.character(.col(data, pair)), condition = as.character(.col(data, group)),
                  value = .col(data, value))
  other <- setdiff(sort(unique(z$condition)), reference)
  z$condition <- factor(z$condition, levels = c(reference, other))
  a <- z[z$condition == reference, ]
  b <- z[z$condition == other, ]
  b <- b[match(a$pair, b$pair), ]
  delta <- b$value - a$value
  wt <- suppressWarnings(stats::wilcox.test(b$value, a$value, paired = TRUE, exact = FALSE))
  s <- data.frame(reference = reference, comparison = other, n_pairs = length(delta),
                  mean_delta = mean(delta), median_delta = stats::median(delta),
                  test = "paired Wilcoxon", p = wt$p.value)
  list(z = z, a = a, other = other, delta = delta, p = wt$p.value, stats = s)
}

.paired_caption <- function(t) {
  labs(caption = sprintf("Paired Wilcoxon p = %s\nn = %d pairs", format_p_value(t$p), length(t$delta)))
}

#' Paired lines between two conditions; Wilcoxon signed-rank test on the pairs.
lab_paired <- function(data, pair, group, value, reference) {
  t <- .paired_table(data, pair, group, value, reference)
  p <- ggplot(t$z, aes(condition, value, group = pair)) +
    geom_line(colour = .neutral("other"), linewidth = .geom$line) +
    geom_point(aes(colour = condition), size = .geom$point) +
    scale_colour_manual(values = .palette_for(2), guide = "none") +
    labs(x = NULL, y = value) +
    theme_lab() +
    .paired_caption(t)
  .set_meta(p, lab_sizes()$single, t$stats)
}

#' Per-pair difference (other condition minus `reference`).
lab_paired_delta <- function(data, pair, group, value, reference) {
  t <- .paired_table(data, pair, group, value, reference)
  dd <- data.frame(pair = factor(t$a$pair, levels = t$a$pair), delta = t$delta)
  p <- ggplot(dd, aes(pair, delta)) +
    geom_hline(yintercept = 0, linetype = 2, colour = .neutral("guide")) +
    geom_segment(aes(xend = pair, y = 0, yend = delta), colour = .neutral("guide")) +
    geom_point(colour = lab_colors("binary")[1], size = .geom$point) +
    labs(x = "Pair ID", y = paste0(t$other, " - ", reference)) +
    theme_lab(x_angle = 45) +
    .paired_caption(t)
  .set_meta(p, lab_sizes()$wide, t$stats)
}

#' Scatter with a linear trend; Spearman and Pearson are both computed.
lab_scatter <- function(data, x, y, group = NULL) {
  z <- data.frame(x = .col(data, x), y = .col(data, y))
  if (!is.null(group)) z$group <- factor(.col(data, group))
  p <- ggplot(z, aes(x, y)) +
    geom_point(size = .geom$point, alpha = 0.75) +
    geom_smooth(method = "lm", formula = y ~ x, se = TRUE, colour = lab_colors("binary")[1],
                linewidth = .geom$curve) +
    theme_lab()
  if (!is.null(group)) {
    p <- p + aes(colour = group) + scale_colour_manual(values = .palette_for(nlevels(z$group)), name = group)
  }
  s <- do.call(rbind, lapply(c("spearman", "pearson"), function(m) {
    ct <- suppressWarnings(stats::cor.test(z$x, z$y, method = m, exact = FALSE))
    data.frame(method = m, r = unname(ct$estimate), p = ct$p.value, n = nrow(z))
  }))
  p <- p + labs(caption = paste(sprintf("%s r = %.3f; p = %.3g", s$method, s$r, s$p), collapse = "\n"),
                x = x, y = y)
  .set_meta(p, lab_sizes()$wide, s)
}

#' Histogram of one numeric column with basic descriptive statistics.
lab_histogram <- function(data, value, bins = 30) {
  z <- data.frame(value = .col(data, value))
  p <- ggplot(z, aes(value)) +
    geom_histogram(bins = bins, fill = lab_colors("binary")[1], colour = "white", linewidth = .geom$thin) +
    labs(x = value, y = "Frequency") +
    theme_lab()
  s <- data.frame(n = nrow(z), mean = mean(z$value), sd = stats::sd(z$value), median = stats::median(z$value),
                  min = min(z$value), max = max(z$value))
  .set_meta(p, lab_sizes()$single, s)
}

# ---- sets and networks --------------------------------------------------

#' UpSet chart from 0/1 membership columns (one per set); all non-empty
#' exact intersections are shown.
lab_upset <- function(data, sets) {
  m <- as.matrix(data[, sets, drop = FALSE])
  combinations <- apply(m, 1, paste0, collapse = "")
  tab <- sort(table(combinations), decreasing = TRUE)
  tab <- tab[names(tab) != paste0(rep(0, ncol(m)), collapse = "")]
  if (length(tab) == 0) stop("No non-empty intersections", call. = FALSE)
  z <- data.frame(intersection = names(tab), count = as.numeric(tab))
  z$intersection <- factor(z$intersection, levels = names(tab))
  no_x <- theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())
  top <- ggplot(z, aes(intersection, count)) +
    geom_col(fill = lab_colors("binary")[1], width = 0.7) +
    labs(x = NULL, y = "Intersection size") + theme_lab() + no_x
  grid <- expand.grid(intersection = names(tab), set = seq_along(sets))
  grid$member <- mapply(function(x, i) as.integer(substr(x, i, i)), grid$intersection, grid$set)
  grid$intersection <- factor(grid$intersection, levels = names(tab))
  members <- grid[grid$member == 1, ]
  bottom <- ggplot(grid, aes(intersection, set)) +
    geom_point(colour = .neutral("light"), size = .geom$point) +
    geom_line(data = members, aes(group = intersection), colour = lab_colors("binary")[1], linewidth = .geom$line) +
    geom_point(data = members, colour = lab_colors("binary")[1], size = .geom$point) +
    scale_y_continuous(breaks = seq_along(sets), labels = sets) +
    labs(x = "Exact intersection membership", y = NULL) + theme_lab() + no_x
  p <- patchwork::wrap_plots(top, bottom, ncol = 1, heights = c(2, 1))
  .set_meta(p, .matrix_size(length(sets) + 5, length(tab), sets, names(tab)), z)
}

#' Directed network from an edge table, on a fixed circular layout.
#' Node size is the number of edges; edge width is the input weight.
lab_network <- function(data, source, target, weight) {
  edges <- data.frame(source = as.character(.col(data, source)), target = as.character(.col(data, target)),
                      weight = .col(data, weight))
  names <- sort(unique(c(edges$source, edges$target)))
  angle <- seq(0, 2 * pi, length.out = length(names) + 1)[-1]
  nodes <- data.frame(node = names, x = cos(angle), y = sin(angle))
  nodes$degree <- as.integer(table(factor(c(edges$source, edges$target), levels = names)))
  at <- function(v, coord) nodes[[coord]][match(v, nodes$node)]
  edges$x <- at(edges$source, "x"); edges$y <- at(edges$source, "y")
  edges$xend <- at(edges$target, "x"); edges$yend <- at(edges$target, "y")
  p <- ggplot() +
    geom_segment(data = edges, aes(x, y, xend = xend, yend = yend, linewidth = weight), alpha = 0.35,
                 colour = lab_colors("binary")[1], arrow = grid::arrow(length = grid::unit(0.08, "inches"))) +
    scale_linewidth_continuous(range = c(0.2, 2), name = "Input weight") +
    geom_point(data = nodes, aes(x, y, size = degree), colour = lab_colors("binary")[1]) +
    ggrepel::geom_text_repel(data = nodes, aes(x, y, label = node), size = .lab_style$text$small, seed = 42,
                             max.overlaps = Inf, show.legend = FALSE) +
    coord_equal(clip = "off") +
    theme_lab() +
    theme(axis.title = element_blank(), axis.text = element_blank(), axis.ticks = element_blank(),
          axis.line = element_blank())
  .set_meta(p, lab_sizes()$roc_multi, nodes)
}

#' A single declared layer: "point", "line", "bar", "box" or "violin".
lab_custom <- function(data, x, y, group = NULL, geometry = "point") {
  z <- data.frame(x = .col(data, x), y = .col(data, y))
  if (!is.null(group)) z$group <- factor(.col(data, group))
  if (geometry %in% c("box", "violin")) z$x <- factor(z$x)
  p <- ggplot(z, aes(x, y))
  if (!is.null(group)) p <- p + aes(colour = group)
  p <- p + switch(geometry,
    point = list(geom_point(size = .geom$point, alpha = 0.75)),
    line = list(geom_line(linewidth = .geom$curve), geom_point(size = .geom$point)),
    bar = list(geom_col(fill = lab_colors("binary")[1], width = 0.7)),
    box = list(geom_boxplot(), geom_jitter(width = 0.12, size = .geom$point)),
    violin = list(geom_violin(), geom_point(position = position_jitter(width = 0.1, seed = 42), size = .geom$point)),
    stop("geometry must be point, line, bar, box or violin", call. = FALSE))
  if (!is.null(group)) p <- p + scale_colour_manual(values = .palette_for(nlevels(z$group)), name = group)
  p <- p + labs(x = x, y = y) + theme_lab()
  .set_meta(p, lab_sizes()$single, data.frame(input_rows = nrow(z), geometry = geometry))
}
