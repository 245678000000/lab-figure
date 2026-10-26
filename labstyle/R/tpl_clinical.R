# Clinical oncology templates: waterfall, swimmer and OncoPrint.

#' Waterfall plot of the best change from baseline per patient (%), sorted
#' from largest increase to largest decrease. Dashed lines mark the RECIST
#' cut-offs (+20% progression, -30% partial response); bars are coloured by
#' `group` (for example best response) when given.
lab_waterfall <- function(data, id, value, group = NULL, levels = NULL,
                          ylab = "Best change from baseline (%)", thresholds = c(20, -30)) {
  d <- data.frame(id = as.character(.col(data, id)), value = as.numeric(.col(data, value)))
  if (!is.null(group)) d$group <- .as_group(.col(data, group), levels)
  d <- d[stats::complete.cases(d), ]
  d <- d[order(-d$value), ]
  d$id <- factor(d$id, levels = unique(d$id))

  p <- ggplot(d, aes(id, value))
  p <- p + if (is.null(group)) {
    geom_col(fill = lab_colors("binary")[1], width = 0.8)
  } else {
    list(geom_col(aes(fill = group), width = 0.8),
         scale_fill_manual(values = .palette_for(nlevels(d$group)), name = group, drop = FALSE))
  }
  p <- p +
    geom_hline(yintercept = 0, linewidth = .geom$line) +
    geom_hline(yintercept = thresholds, linetype = 2, linewidth = .geom$thin, colour = .neutral("guide")) +
    labs(x = NULL, y = ylab) +
    theme_lab() +
    theme(axis.line.x = element_blank())
  # Patient IDs are readable up to about 40 bars; beyond that they are dropped.
  p <- p + if (nrow(d) <= 40) {
    theme(axis.text.x = element_text(angle = 90, hjust = 1, vjust = 0.5, size = rel(0.75)))
  } else {
    theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())
  }

  by <- if (is.null(group)) list(all = d) else split(d, d$group)
  s <- do.call(rbind, lapply(names(by), function(g) {
    x <- by[[g]]$value
    data.frame(group = g, n = length(x), median_change = if (length(x)) stats::median(x) else NA,
               n_increase_20 = sum(x >= max(thresholds)), n_decrease_30 = sum(x <= min(thresholds)))
  }))
  .set_meta(p, c(min(8, max(3, 1.2 + if (nrow(d) <= 40) 0.12 * nrow(d) else 0.08 * nrow(d))), 2.7), s)
}

#' Swimmer plot: one bar per patient for time on treatment, longest at the
#' top. `ongoing` (0/1 or TRUE/FALSE) adds an arrow for patients still on
#' treatment; bars are coloured by `group` when given.
lab_swimmer <- function(data, id, time, group = NULL, ongoing = NULL, levels = NULL,
                        xlab = "Time on treatment (months)") {
  d <- data.frame(id = as.character(.col(data, id)), time = as.numeric(.col(data, time)))
  if (!is.null(group)) d$group <- .as_group(.col(data, group), levels)
  d$ongoing <- if (is.null(ongoing)) FALSE else .as_binary(.col(data, ongoing), arg = "ongoing") %in% 1
  d <- d[stats::complete.cases(d), ]
  d <- d[order(d$time), ]
  d$id <- factor(d$id, levels = unique(d$id))

  p <- ggplot(d, aes(time, id))
  p <- p + if (is.null(group)) {
    geom_col(fill = lab_colors("binary")[1], width = 0.6, orientation = "y")
  } else {
    list(geom_col(aes(fill = group), width = 0.6, orientation = "y"),
         scale_fill_manual(values = .palette_for(nlevels(d$group)), name = group, drop = FALSE))
  }
  if (any(d$ongoing)) {
    step <- max(d$time) * 0.06
    p <- p + geom_segment(data = d[d$ongoing, ], aes(x = time, xend = time + step, y = id, yend = id),
                          arrow = grid::arrow(length = grid::unit(0.05, "inches"), type = "closed"),
                          linewidth = .geom$line)
  }
  p <- p +
    scale_x_continuous(expand = expansion(mult = c(0, 0.08))) +
    labs(x = xlab, y = NULL, caption = if (any(d$ongoing)) "Arrow: still on treatment" else NULL) +
    theme_lab()

  by <- if (is.null(group)) list(all = d) else split(d, d$group)
  s <- do.call(rbind, lapply(names(by), function(g) {
    x <- by[[g]]
    data.frame(group = g, n = nrow(x), median_time = if (nrow(x)) stats::median(x$time) else NA,
               ongoing = sum(x$ongoing))
  }))
  .set_meta(p, c(3.6, min(14, max(2.4, 0.8 + 0.17 * nrow(d)))), s)
}

#' OncoPrint from a long mutation table (one row per sample x gene
#' alteration). Genes are ordered by how many samples carry an alteration
#' and samples by their pattern; a sample with two alteration types in one
#' gene is shown as "Multi_hit". Only the `top` most altered genes are drawn.
lab_oncoprint <- function(data, sample, gene, alteration, top = 20) {
  d <- data.frame(sample = as.character(.col(data, sample)), gene = as.character(.col(data, gene)),
                  alteration = as.character(.col(data, alteration)))
  d <- d[stats::complete.cases(d) & nzchar(d$alteration), ]
  samples <- unique(as.character(.col(data, sample)))
  # one alteration per sample x gene cell
  cells <- stats::aggregate(alteration ~ sample + gene, d, function(a) {
    a <- unique(a)
    if (length(a) > 1) "Multi_hit" else a
  })

  freq <- sort(table(cells$gene), decreasing = TRUE)
  genes <- utils::head(names(freq), top)
  cells <- cells[cells$gene %in% genes, ]
  # memo sort: samples altered in the most frequent genes first
  hit <- vapply(genes, function(g) samples %in% cells$sample[cells$gene == g], logical(length(samples)))
  hit <- matrix(hit, nrow = length(samples))
  order_key <- do.call(order, c(lapply(seq_along(genes), function(j) -hit[, j]), list(samples)))
  samples <- samples[order_key]

  types <- sort(unique(cells$alteration))
  colours <- stats::setNames(.palette_for(length(types)), types)
  cells$sample <- factor(cells$sample, levels = samples)
  cells$gene <- factor(cells$gene, levels = rev(genes))
  grid_cells <- expand.grid(sample = factor(samples, levels = samples), gene = factor(rev(genes), levels = rev(genes)))

  stats_table <- data.frame(gene = genes, n_altered = as.integer(freq[genes]),
                            percent = round(100 * as.integer(freq[genes]) / length(samples), 1))
  gene_labels <- paste0(genes, " ", stats_table$percent, "%")

  main <- ggplot(cells, aes(sample, gene)) +
    geom_tile(data = grid_cells, fill = .neutral("light"), colour = "white", linewidth = 0.4) +
    geom_tile(aes(fill = alteration), colour = "white", linewidth = 0.4) +
    scale_fill_manual(values = colours, name = "Alteration") +
    scale_y_discrete(labels = rev(gene_labels)) +
    labs(x = NULL, y = NULL) +
    theme_lab() +
    theme(axis.text.x = element_blank(), axis.ticks.x = element_blank(), axis.line = element_blank(),
          panel.grid = element_blank())
  per_sample <- as.data.frame(table(sample = factor(cells$sample, levels = samples), alteration = cells$alteration))
  bar <- ggplot(per_sample, aes(sample, Freq, fill = alteration)) +
    geom_col(width = 0.9) +
    scale_fill_manual(values = colours, guide = "none") +
    labs(x = NULL, y = "Altered\ngenes") +
    theme_lab() +
    theme(axis.text.x = element_blank(), axis.ticks.x = element_blank(), axis.line.x = element_blank())
  p <- patchwork::wrap_plots(bar, main, ncol = 1, heights = c(1, max(2, length(genes) / 3)))
  size <- c(min(12, max(4.6, 2.6 + 0.12 * length(samples))), min(14, 1.6 + 0.25 * length(genes)))
  .set_meta(p, size, stats_table)
}
