#' Export a figure as PDF + PNG at a house size preset.
#'
#' `size` is a preset name (see `lab_sizes()`) or c(width, height) in inches;
#' when NULL the template's own preset is used. `data` optionally writes the
#' plotted source data next to the figure as `<name>_source_data.csv`.
save_fig <- function(p, name, size = NULL, dir = "figures",
                     formats = c("pdf", "png"), dpi = .lab_style$dpi, data = NULL) {
  wh <- .resolve_size(size %||% attr(p, "lab_size") %||% "single")
  if (isTRUE(.preview$active)) {
    # live preview (serve()): hand the plot over instead of writing files
    .preview$figures[[length(.preview$figures) + 1]] <- list(plot = p, name = name, size = wh)
    return(invisible(character()))
  }
  dir.create(dir, recursive = TRUE, showWarnings = FALSE)
  base <- file.path(dir, sub("\\.(pdf|png|svg)$", "", name))
  paths <- character()

  if ("pdf" %in% formats) {
    f <- paste0(base, ".pdf")
    .draw_to(function() grDevices::pdf(f, width = wh[1], height = wh[2],
                                       useDingbats = FALSE, onefile = FALSE), p)
    paths <- c(paths, f)
  }
  if ("png" %in% formats) {
    f <- paste0(base, ".png")
    .draw_to(function() ragg::agg_png(f, width = wh[1], height = wh[2], units = "in",
                                      res = dpi, background = "white"), p)
    paths <- c(paths, f)
  }
  if ("svg" %in% formats) {
    f <- paste0(base, ".svg")
    .draw_to(function() svglite::svglite(f, width = wh[1], height = wh[2]), p)
    paths <- c(paths, f)
  }
  if (!is.null(data)) {
    f <- paste0(base, "_source_data.csv")
    utils::write.csv(data, f, row.names = FALSE)
    paths <- c(paths, f)
  }
  message("saved ", sprintf("%.2f x %.2f in: ", wh[1], wh[2]), paste(paths, collapse = ", "))
  invisible(paths)
}

.resolve_size <- function(size) {
  if (is.numeric(size) && length(size) == 2) return(size)
  wh <- .lab_style$sizes[[size]]
  if (is.null(wh)) {
    stop(sprintf("unknown size preset '%s'; use one of: %s, or c(width, height)",
                 size, paste(names(.lab_style$sizes), collapse = ", ")), call. = FALSE)
  }
  wh
}

.draw_to <- function(open_device, p) {
  open_device()
  dev <- grDevices::dev.cur()
  on.exit(grDevices::dev.off(dev), add = TRUE)
  if (inherits(p, "grob") || inherits(p, "gtable")) grid::grid.draw(p) else print(p)
}
