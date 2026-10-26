# GWAS templates: Manhattan and QQ plots.

# Chromosome names in genome order: 1-22, X, Y, then mitochondrial and others.
.chr_order <- function(chr) {
  u <- unique(chr)
  key <- suppressWarnings(as.numeric(u))
  key[toupper(u) == "X"] <- 23
  key[toupper(u) == "Y"] <- 24
  key[toupper(u) %in% c("M", "MT")] <- 25
  key[is.na(key)] <- 26
  u[order(key, u)]
}

.lambda_gc <- function(p) stats::median(stats::qchisq(p, 1, lower.tail = FALSE)) / stats::qchisq(0.5, 1)

#' Manhattan plot from per-variant results (`chr`, base-pair `pos`, `p`).
#' Lines mark genome-wide (5e-8) and suggestive (1e-5) significance; with
#' `label`, the `label_count` strongest genome-wide hits are named.
lab_manhattan <- function(data, chr, pos, p, label = NULL, threshold = 5e-8, suggestive = 1e-5,
                          label_count = 10) {
  d <- data.frame(chr = sub("^chr", "", as.character(.col(data, chr)), ignore.case = TRUE),
                  pos = as.numeric(.col(data, pos)), p = as.numeric(.col(data, p)))
  if (!is.null(label)) d$label <- as.character(.col(data, label))
  d <- d[stats::complete.cases(d[c("chr", "pos", "p")]) & d$p > 0 & d$p <= 1, ]
  chrs <- .chr_order(d$chr)
  d$chr <- factor(d$chr, levels = chrs)
  lengths <- tapply(d$pos, d$chr, max)
  offset <- c(0, cumsum(as.numeric(lengths)))[seq_along(chrs)]
  names(offset) <- chrs
  d$x <- d$pos + offset[as.character(d$chr)]
  d$y <- .logp(d$p)
  d$band <- factor(as.integer(d$chr) %% 2)
  centres <- tapply(d$x, d$chr, function(v) mean(range(v)))

  p <- ggplot(d, aes(x, y, colour = band)) +
    geom_point(size = .geom$point_dense) +
    geom_hline(yintercept = .logp(threshold), linetype = 2, linewidth = .geom$thin, colour = lab_colors("binary")[2]) +
    geom_hline(yintercept = .logp(suggestive), linetype = 3, linewidth = .geom$thin, colour = .neutral("guide")) +
    scale_colour_manual(values = c(`1` = lab_colors("binary")[1], `0` = "grey60"), guide = "none") +
    scale_x_continuous(breaks = centres, labels = chrs, expand = expansion(mult = 0.01)) +
    scale_y_continuous(expand = expansion(mult = c(0, 0.08))) +
    labs(x = "Chromosome", y = "-log10(P)") +
    theme_lab() +
    theme(axis.text.x = element_text(size = rel(0.7)))
  hits <- d[d$p < threshold, ]
  hits <- hits[order(hits$p), ]
  if (!is.null(label) && label_count > 0 && nrow(hits)) {
    p <- p + ggrepel::geom_text_repel(data = utils::head(hits, label_count), aes(label = label),
                                      colour = "black", size = .lab_style$text$small, seed = 42,
                                      max.overlaps = Inf, show.legend = FALSE)
  }
  s <- data.frame(variants = nrow(d), genome_wide = sum(d$p < threshold), suggestive = sum(d$p < suggestive),
                  lambda_gc = .lambda_gc(d$p), threshold = threshold)
  attr(p, "lab_tables") <- list(top_hits = utils::head(d[order(d$p), setdiff(names(d), c("x", "y", "band"))], 50))
  .set_meta(p, c(6.5, 2.7), s)
}

#' QQ plot of observed against expected -log10 P, with a 95% band and the
#' genomic inflation factor (lambda).
lab_qq <- function(data, p) {
  pv <- sort(as.numeric(.col(data, p)))
  pv <- pv[!is.na(pv) & pv > 0 & pv <= 1]
  n <- length(pv)
  i <- seq_len(n)
  z <- data.frame(expected = -log10(stats::ppoints(n)), observed = -log10(pv),
                  lower = -log10(stats::qbeta(0.975, i, n - i + 1)),
                  upper = -log10(stats::qbeta(0.025, i, n - i + 1)))
  lambda <- .lambda_gc(pv)
  p <- ggplot(z, aes(expected, observed)) +
    geom_ribbon(aes(ymin = lower, ymax = upper), fill = .neutral("light")) +
    annotate("segment", x = 0, y = 0, xend = max(z$expected), yend = max(z$expected), linetype = 2,
             linewidth = .geom$thin, colour = .neutral("guide")) +
    geom_point(size = .geom$point_dense, colour = lab_colors("binary")[1]) +
    annotate("text", x = 0, y = max(z$observed), hjust = 0, vjust = 1, size = .lab_style$text$small,
             label = sprintf("lambda = %.3f", lambda)) +
    labs(x = "Expected -log10(P)", y = "Observed -log10(P)") +
    theme_lab()
  .set_meta(p, c(2.7, 2.7), data.frame(n = n, lambda_gc = lambda))
}
