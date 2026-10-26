# Distribution and flow templates: ridgeline, density, Sankey and Venn.
# Drawn with ggplot2 only, so no extra packages are needed.

.group_summary <- function(value, group) {
  by <- split(value, group)
  do.call(rbind, lapply(names(by), function(g) {
    x <- by[[g]]
    data.frame(group = g, n = length(x), mean = if (length(x)) mean(x) else NA,
               sd = if (length(x) > 1) stats::sd(x) else NA, median = if (length(x)) stats::median(x) else NA)
  }))
}

#' Ridgeline plot: one density curve per group, stacked vertically (first
#' group at the top).
lab_ridge <- function(data, group, value, levels = NULL, xlab = value, overlap = 1.2) {
  d <- data.frame(group = .as_group(.col(data, group), levels), value = as.numeric(.col(data, value)))
  d <- d[stats::complete.cases(d), ]
  lv <- levels(d$group)
  rng <- range(d$value)
  dens <- do.call(rbind, lapply(seq_along(lv), function(i) {
    x <- d$value[d$group == lv[i]]
    if (length(x) < 2) return(NULL)
    k <- stats::density(x, from = rng[1], to = rng[2], n = 256)
    data.frame(group = lv[i], x = k$x, y = k$y, offset = length(lv) - i + 1)
  }))
  dens$y <- dens$y / max(dens$y) * overlap
  dens$group <- factor(dens$group, levels = lv)
  # draw the top ridge first so lower ridges sit in front of it
  dens$draw <- factor(dens$offset, levels = sort(unique(dens$offset), decreasing = TRUE))
  p <- ggplot(dens, aes(x, ymin = offset, ymax = offset + y, fill = group, group = draw)) +
    geom_ribbon(alpha = 0.85, colour = "black", linewidth = .geom$thin) +
    scale_fill_manual(values = .palette_for(length(lv)), guide = "none") +
    scale_y_continuous(breaks = rev(seq_along(lv)), labels = lv, expand = expansion(add = c(0.1, overlap))) +
    labs(x = xlab, y = NULL) +
    theme_lab()
  .set_meta(p, c(3.2, min(12, 1 + 0.45 * length(lv))), .group_summary(d$value, d$group))
}

#' Overlaid density curves, one per group (or a single curve).
lab_density <- function(data, value, group = NULL, levels = NULL, xlab = value) {
  d <- data.frame(value = as.numeric(.col(data, value)))
  d$group <- if (is.null(group)) factor("all") else .as_group(.col(data, group), levels)
  d <- d[stats::complete.cases(d), ]
  p <- ggplot(d, aes(value))
  p <- p + if (is.null(group)) {
    geom_density(fill = lab_colors("binary")[1], colour = lab_colors("binary")[1], alpha = 0.25,
                 linewidth = .geom$line)
  } else {
    list(geom_density(aes(fill = group, colour = group), alpha = 0.25, linewidth = .geom$line),
         scale_fill_manual(values = .palette_for(nlevels(d$group)), name = group),
         scale_colour_manual(values = .palette_for(nlevels(d$group)), name = group))
  }
  p <- p + labs(x = xlab, y = "Density") + theme_lab()
  .set_meta(p, c(3.2, 2.7), .group_summary(d$value, d$group))
}

#' Sankey (alluvial) diagram across 2-4 stage columns, for example response
#' at baseline -> week 12 -> week 24. Each row is one subject, or a group of
#' subjects when `count` is given. Flows take the colour of the category
#' they leave; the same category name keeps one colour in every stage.
lab_sankey <- function(data, stages, count = NULL, stage_labels = stages) {
  if (length(stages) < 2) stop("a Sankey diagram needs at least two stage columns", call. = FALSE)
  d <- as.data.frame(lapply(stages, function(s) as.character(.col(data, s))), stringsAsFactors = FALSE)
  names(d) <- paste0("s", seq_along(stages))
  d$n <- if (is.null(count)) 1 else as.numeric(.col(data, count))
  d <- d[stats::complete.cases(d), ]
  total <- sum(d$n)
  gap <- 0.03 * total
  width <- 0.12
  categories <- unique(unlist(d[seq_along(stages)]))
  colours <- stats::setNames(.palette_for(length(categories)), categories)

  # nodes stacked from the top of each stage
  nodes <- do.call(rbind, lapply(seq_along(stages), function(k) {
    lv <- unique(d[[k]])
    n <- as.numeric(tapply(d$n, factor(d[[k]], levels = lv), sum))
    top <- total + gap * (length(lv) - 1) - c(0, cumsum(n + gap))[seq_along(lv)]
    data.frame(stage = k, category = lv, n = n, ymax = top, ymin = top - n)
  }))
  node_of <- function(k, cat) nodes[nodes$stage == k & nodes$category == cat, ]

  flows <- list()
  for (k in seq_len(length(stages) - 1)) {
    pairs <- stats::aggregate(d$n, by = list(from = d[[k]], to = d[[k + 1]]), FUN = sum)
    pairs <- pairs[order(match(pairs$from, nodes$category[nodes$stage == k]),
                         match(pairs$to, nodes$category[nodes$stage == k + 1])), ]
    used_out <- stats::setNames(rep(0, nrow(nodes)), paste(nodes$stage, nodes$category))
    used_in <- used_out
    by_target <- pairs[order(match(pairs$to, nodes$category[nodes$stage == k + 1]),
                             match(pairs$from, nodes$category[nodes$stage == k])), ]
    in_pos <- list()
    for (i in seq_len(nrow(by_target))) {
      key <- paste(k + 1, by_target$to[i])
      top <- node_of(k + 1, by_target$to[i])$ymax - used_in[key]
      in_pos[[paste(by_target$from[i], by_target$to[i])]] <- c(top, top - by_target$x[i])
      used_in[key] <- used_in[key] + by_target$x[i]
    }
    for (i in seq_len(nrow(pairs))) {
      key <- paste(k, pairs$from[i])
      top <- node_of(k, pairs$from[i])$ymax - used_out[key]
      out <- c(top, top - pairs$x[i])
      used_out[key] <- used_out[key] + pairs$x[i]
      into <- in_pos[[paste(pairs$from[i], pairs$to[i])]]
      t <- seq(0, 1, length.out = 40)
      s <- (1 - cos(pi * t)) / 2
      x <- (k + width / 2) + t * (1 - width)
      flows[[length(flows) + 1]] <- data.frame(
        id = paste(k, i), category = pairs$from[i],
        x = c(x, rev(x)),
        y = c(out[1] + (into[1] - out[1]) * s, rev(out[2] + (into[2] - out[2]) * s)))
    }
  }
  flows <- do.call(rbind, flows)
  transitions <- do.call(rbind, lapply(seq_len(length(stages) - 1), function(k) {
    a <- stats::aggregate(d$n, by = list(from = d[[k]], to = d[[k + 1]]), FUN = sum)
    data.frame(from_stage = stage_labels[k], from = a$from, to_stage = stage_labels[k + 1], to = a$to, n = a$x)
  }))

  p <- ggplot() +
    geom_polygon(data = flows, aes(x, y, group = id, fill = category), alpha = 0.45) +
    geom_rect(data = nodes, aes(xmin = stage - width / 2, xmax = stage + width / 2, ymin = ymin, ymax = ymax,
                                fill = category), colour = "white", linewidth = .geom$thin) +
    # white boxes keep the middle-stage labels readable over the flows
    geom_label(data = nodes, aes(x = stage + ifelse(stage == length(stages), width / 2 + 0.04, -width / 2 - 0.04),
                                 y = (ymin + ymax) / 2, label = paste0(category, " (", n, ")"),
                                 hjust = ifelse(stage == length(stages), 0, 1)),
               size = .lab_style$text$small, fill = "white", border.colour = NA,
               label.padding = grid::unit(0.08, "lines")) +
    scale_fill_manual(values = colours, guide = "none") +
    scale_x_continuous(breaks = seq_along(stages), labels = stage_labels, expand = expansion(add = 0.7)) +
    labs(x = NULL, y = NULL) +
    theme_lab() +
    theme(axis.line = element_blank(), axis.ticks = element_blank(), axis.text.y = element_blank())
  .set_meta(p, c(min(10, 1.6 + 1.5 * length(stages)), 3.2), transitions)
}

# Venn shapes (centre, semi-axes, rotation in degrees). The four-set layout
# is the classic ellipse arrangement used by VennDiagram::draw.quad.venn.
.venn_shapes <- function(k) {
  switch(as.character(k),
    "2" = data.frame(x = c(-0.55, 0.55), y = 0, a = 1, b = 1, angle = 0),
    "3" = data.frame(x = c(-0.55, 0.55, 0), y = c(0.35, 0.35, -0.6), a = 1, b = 1, angle = 0),
    "4" = data.frame(x = c(0.35, 0.5, 0.5, 0.65), y = c(0.47, 0.57, 0.57, 0.47), a = c(0.35, 0.35, 0.33, 0.35),
                     b = c(0.2, 0.15, 0.15, 0.2), angle = c(135, 135, 45, 45)),
    stop("a Venn diagram needs 2-4 sets; use lab_upset for more", call. = FALSE))
}

.inside_shape <- function(px, py, s) {
  th <- s$angle * pi / 180
  dx <- px - s$x
  dy <- py - s$y
  u <- dx * cos(th) + dy * sin(th)
  v <- -dx * sin(th) + dy * cos(th)
  (u / s$a)^2 + (v / s$b)^2 <= 1
}

#' Venn diagram of 2-4 sets from 0/1 (or TRUE/FALSE) membership columns,
#' one row per element. Each region shows the number of elements in exactly
#' that combination of sets.
lab_venn <- function(data, sets) {
  shapes <- .venn_shapes(length(sets))
  m <- sapply(sets, function(s) {
    x <- .col(data, s)
    if (anyNA(x)) stop(sprintf("set column '%s' has missing values; use 0/1", s), call. = FALSE)
    if (is.logical(x)) x else as.numeric(x) == 1
  })
  m <- matrix(m, ncol = length(sets))
  pattern <- apply(m, 1, function(r) paste(as.integer(r), collapse = ""))

  # region labels: the grid point nearest each region's centre
  span <- range(c(shapes$x - shapes$a, shapes$x + shapes$a, shapes$y - shapes$a, shapes$y + shapes$a))
  grid <- expand.grid(x = seq(span[1], span[2], length.out = 220), y = seq(span[1], span[2], length.out = 220))
  inside <- sapply(seq_len(nrow(shapes)), function(i) .inside_shape(grid$x, grid$y, shapes[i, ]))
  grid$pattern <- apply(inside, 1, function(r) paste(as.integer(r), collapse = ""))
  combos <- unique(grid$pattern[grepl("1", grid$pattern)])
  regions <- do.call(rbind, lapply(combos, function(pt) {
    g <- grid[grid$pattern == pt, ]
    i <- which.min((g$x - mean(g$x))^2 + (g$y - mean(g$y))^2)
    data.frame(pattern = pt, x = g$x[i], y = g$y[i], count = sum(pattern == pt))
  }))

  outline <- do.call(rbind, lapply(seq_len(nrow(shapes)), function(i) {
    s <- shapes[i, ]
    t <- seq(0, 2 * pi, length.out = 200)
    th <- s$angle * pi / 180
    u <- s$a * cos(t)
    v <- s$b * sin(t)
    data.frame(set = sets[i], x = s$x + u * cos(th) - v * sin(th), y = s$y + u * sin(th) + v * cos(th))
  }))
  outline$set <- factor(outline$set, levels = sets)
  colours <- .palette_for(length(sets))
  # set names go in the legend: names placed around the shapes run off the page
  p <- ggplot() +
    geom_polygon(data = outline, aes(x, y, group = set, fill = set, colour = set), alpha = 0.2,
                 linewidth = .geom$line) +
    geom_text(data = regions, aes(x, y, label = count), size = .lab_style$text$box) +
    scale_fill_manual(values = colours, name = NULL) +
    scale_colour_manual(values = colours, name = NULL) +
    coord_equal() +
    theme_void(base_size = .lab_style$base_size) +
    theme(plot.background = element_rect(fill = "white", colour = NA), plot.margin = margin(6, 6, 6, 6),
          legend.position = "bottom", legend.text = element_text(size = rel(0.8)))
  sets_in <- function(pt) paste(sets[strsplit(pt, "")[[1]] == "1"], collapse = " & ")
  s <- data.frame(region = vapply(regions$pattern, sets_in, character(1)), count = regions$count, row.names = NULL)
  s <- rbind(s, data.frame(region = "(none of the sets)", count = sum(!grepl("1", pattern))))
  .set_meta(p, c(3.4, 3.4), s)
}
