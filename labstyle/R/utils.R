`%||%` <- function(a, b) if (is.null(a)) b else a

.col <- function(data, name) {
  if (!name %in% names(data)) {
    stop(sprintf("column '%s' not found; available: %s",
                 name, paste(names(data), collapse = ", ")), call. = FALSE)
  }
  data[[name]]
}

# Two-class outcome -> 0/1 integer (NA kept). 0/1 and logical pass through;
# survival-style 1/2 status means 2 = event; otherwise `positive` names the
# event class (defaults to the second factor level).
.as_binary <- function(x, positive = NULL, arg = "outcome") {
  if (is.logical(x)) return(as.integer(x))
  vals <- sort(unique(stats::na.omit(x)))
  if (is.numeric(x) && is.null(positive)) {
    if (all(vals %in% c(0, 1))) return(as.integer(x))
    if (all(vals %in% c(1, 2))) {
      message(sprintf("'%s' coded 1/2: treating 2 as the event", arg))
      return(as.integer(x == 2))
    }
  }
  if (length(vals) != 2) {
    stop(sprintf("'%s' must have exactly 2 classes, found %d: %s",
                 arg, length(vals), paste(utils::head(vals, 6), collapse = ", ")), call. = FALSE)
  }
  if (is.null(positive)) {
    if (!is.factor(x)) {
      stop(sprintf("'%s' has classes %s; set positive = the event class",
                   arg, paste(vals, collapse = " / ")), call. = FALSE)
    }
    positive <- levels(droplevels(x))[2]
  }
  if (!as.character(positive) %in% as.character(vals)) {
    stop(sprintf("positive = '%s' is not a class of '%s' (%s)",
                 positive, arg, paste(vals, collapse = " / ")), call. = FALSE)
  }
  as.integer(as.character(x) == as.character(positive))
}

# Display names of the two classes as c(negative, positive), matching .as_binary().
.binary_labels <- function(x, positive = NULL) {
  if (is.logical(x)) return(c("FALSE", "TRUE"))
  vals <- sort(unique(stats::na.omit(x)))
  if (is.numeric(x) && is.null(positive)) return(as.character(vals))
  if (is.null(positive)) return(levels(droplevels(x)))
  c(setdiff(as.character(vals), as.character(positive))[1], as.character(positive))
}

# "A (n = 12)" labels for group axes and legends.
.n_labels <- function(groups, counts, sep = " ") {
  paste0(groups, sep, "(n = ", counts, ")")
}

# x axis labelled with group sizes: two lines when upright, one line when rotated.
.x_scale_n <- function(x, x_angle) {
  scale_x_discrete(labels = .n_labels(levels(x), as.vector(table(x)),
                                      sep = if (x_angle == 0) "\n" else " "))
}

.as_group <- function(x, levels = NULL) {
  if (!is.null(levels)) return(factor(x, levels = levels))
  if (is.factor(x)) return(droplevels(x))
  factor(x)
}

.set_meta <- function(p, size, stats) {
  attr(p, "lab_size") <- size
  attr(p, "lab_stats") <- stats
  p
}

# Pairwise two-sample tests for the listed group pairs.
.pair_tests <- function(d, comparisons, test) {
  do.call(rbind, lapply(comparisons, function(pair) {
    a <- d$y[d$x == pair[1]]
    b <- d$y[d$x == pair[2]]
    # R's default: exact Wilcoxon p for small samples without ties, as in the originals
    p <- if (test == "t") stats::t.test(a, b)$p.value else suppressWarnings(stats::wilcox.test(a, b)$p.value)
    data.frame(group1 = pair[1], group2 = pair[2], n1 = length(a), n2 = length(b),
               test = test, p = p)
  }))
}

.resolve_comparisons <- function(comparisons, lv) {
  if (is.null(comparisons)) {
    if (length(lv) == 2) return(list(lv))
    return(list())
  }
  if (identical(comparisons, "all")) return(utils::combn(lv, 2, simplify = FALSE))
  if (identical(comparisons, "none")) return(list())
  comparisons
}

# Square brackets with a label above, stacked upwards from y0.
.bracket_layers <- function(tests, lv, y0, step, size) {
  if (is.null(tests) || nrow(tests) == 0) return(list())
  tip <- step * 0.25
  layers <- list()
  for (i in seq_len(nrow(tests))) {
    x1 <- match(tests$group1[i], lv)
    x2 <- match(tests$group2[i], lv)
    y <- y0 + (i - 1) * step
    layers <- c(layers, list(
      annotate("segment", x = x1, xend = x2, y = y, yend = y, linewidth = 0.4),
      annotate("segment", x = x1, xend = x1, y = y, yend = y - tip, linewidth = 0.4),
      annotate("segment", x = x2, xend = x2, y = y, yend = y - tip, linewidth = 0.4),
      annotate("text", x = (x1 + x2) / 2, y = y + step * 0.3, vjust = 0, size = size,
               label = paste0("p = ", format_p_value(tests$p[i])))
    ))
  }
  c(layers, list(expand_limits(y = y0 + nrow(tests) * step)))
}
