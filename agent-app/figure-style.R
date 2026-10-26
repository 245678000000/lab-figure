# AISI-figure extensions inherit the original nine labstyle templates.
# Style source: labstyle/R/style.R, theme.R and tpl_{box,violin,roc,cor_heatmap}.R.
# Statistical data and methods are independent of these presentation settings.
# A figure script needs only: source("figure-style.R"); d <- read_source();
# p <- <a lab_* template or ggplot>; finish(p). Helpers are at the end of this file.
suppressPackageStartupMessages({ library(labstyle); library(ggplot2) })
set.seed(42)
ais_house <- getFromNamespace(".lab_style", "labstyle")
ais_house$point <- list(standard=2, dense=.5)
ais_house$line <- list(curve=1, standard=.5, thin=.3)
ais_house$neutral <- list(other=lab_colors("categorical")[5], guide=lab_colors("categorical")[9], light="grey90", missing="grey85", white="white")
ais_theme <- function(...) theme_lab(...)
ais_size <- function(chart) {
  preset <- if(chart %in% c("volcano","ma","embedding","feature","pca","network")) "roc_multi" else if(chart %in% c("scatter","gsea","composition","paired_delta","upset")) "wide" else "single"
  wh <- lab_sizes()[[preset]]
  if(chart %in% c("volcano","ma")) wh <- c(lab_sizes()[["wide"]][1],lab_sizes()[["roc_multi"]][2])
  wh
}
ais_matrix_size <- function(rows,columns,row_labels,column_labels,legend_labels=character()) {
  # The original correlation heatmap reserves .3 in per cell plus label space.
  label_space <- .075 * max(nchar(c(as.character(row_labels),as.character(column_labels),"")))
  guide_space <- if(length(legend_labels)) .075*max(nchar(legend_labels))+.8 else 0
  pmin(c(16,18),pmax(c(lab_sizes()[["wide"]][1],lab_sizes()[["single"]][2]),c(label_space+.3*columns+1.2+guide_space,label_space+.3*rows+.6)))
}
ais_category_size <- function(rows,labels,legend=FALSE) {
  label_space <- .075*max(nchar(c(as.character(labels),"")))
  pmin(c(16,18),c(max(lab_sizes()[["wide"]][1],label_space+2.3+if(legend) 1.2 else 0),max(lab_sizes()[["single"]][2],.3*rows+.8)))
}
ais_write_style <- function(wh) {
  t <- theme_lab()
  info <- list(name="AISI-figure",reference="Original nine labstyle templates",version="1",labstyle_version=as.character(packageVersion("labstyle")),base_size_pt=ais_house$base_size,axis_text_pt=ggplot2::calc_element("axis.text.x",t)$size,axis_title_pt=ggplot2::calc_element("axis.title.x",t)$size,legend_text_pt=ggplot2::calc_element("legend.text",t)$size,annotation_mm=ais_house$text$small,colors=lab_colors("binary"),width_in=unname(wh[1]),height_in=unname(wh[2]),dpi=ais_house$dpi)
  jsonlite::write_json(info,"figure-style.json",auto_unbox=TRUE,pretty=TRUE)
}

# Per-run settings are frozen with the input and code, independent of future edits.
ais_settings <- if(file.exists("plot-settings.json")) jsonlite::fromJSON("plot-settings.json",simplifyVector=FALSE) else list()
ais_export_size <- function(wh) {
  if(!is.null(ais_settings$width_mm)) {
    width <- ais_settings$width_mm/25.4
    height <- if(is.null(ais_settings$height_mm)) width*wh[2]/wh[1] else ais_settings$height_mm/25.4
    return(c(width,height))
  }
  wh
}
ais_apply_colors <- function(p) {
  colors <- unlist(ais_settings$group_colors,use.names=TRUE)
  if(!length(colors)) return(p)
  size <- attr(p,"lab_size")
  if(inherits(p,"patchwork")) {
    for(i in seq_len(length(p))) p[[i]] <- ais_apply_colors(p[[i]])
    if(!is.null(size)) attr(p,"lab_size") <- size
    return(p)
  }
  for(aesthetic in c("colour","fill")) {
    scale <- p$scales$get_scales(aesthetic)
    if(!is.null(scale) && scale$is_discrete()) {
      scale <- scale$clone()
      scale$palette <- function(n) colors
      scale$palette.cache <- NULL
      p$scales$add(scale)
    }
  }
  jsonlite::write_json(as.list(colors),"render-colors.json",auto_unbox=TRUE,pretty=TRUE)
  p
}

# ---- helpers used by figure scripts ----

# This run's input table, exactly as the app saved it.
read_source <- function() {
  if (file.exists("source-schema.json")) {
    source("wide-table.R", local = TRUE)
    return(ais_read_wide())
  }
  utils::read.csv("source_data.csv", check.names = FALSE, encoding = "UTF-8", stringsAsFactors = FALSE)
}

# The feature list chosen in the app, for selections too long to show in the script.
read_features <- function() unlist(jsonlite::fromJSON("analysis-settings.json")$columns$predictors)

# Save figure.pdf/png/svg plus the statistics, export size and session details
# the app reads after a run. `size` is a preset name or c(width, height) in
# inches; by default the template's own size.
finish <- function(p, size = NULL) {
  stats <- lab_stats(p)
  tables <- attr(p, "lab_tables")
  if (is.null(size)) size <- attr(p, "lab_size")
  if (is.null(size)) size <- "single"
  if (!inherits(p, "grob")) p <- ais_apply_colors(p)   # an edited figure may already be a grid table
  wh <- if (is.character(size)) lab_sizes()[[size]] else size
  wh <- ais_export_size(wh)
  ais_write_style(wh)
  ais_save_figure(p, "figure", size = wh)
  if (is.null(stats)) stats <- data.frame()
  jsonlite::write_json(stats, "stats.json", dataframe = "rows", auto_unbox = TRUE, na = "null", pretty = TRUE, digits = NA)
  if (nrow(stats)) utils::write.csv(stats, "statistics.csv", row.names = FALSE)
  for (name in names(tables)) utils::write.csv(tables[[name]], paste0(name, ".csv"), row.names = is.matrix(tables[[name]]))
  writeLines(utils::capture.output(utils::sessionInfo()), "session-info.txt")
  invisible(p)
}

# PNG and SVG first, then the PDF. The standard PDF device covers Arial text in
# Latin-1; other characters (e.g. Chinese, en dash) or fonts need Cairo. Without
# Cairo (macOS without XQuartz) only text the standard device would lose stops the run.
ais_save_figure <- function(p, name, dir = ".", size, formats = c("pdf", "png", "svg"), ...) {
  labstyle::save_fig(p, name, dir = dir, size = size, formats = union(setdiff(formats, "pdf"), "svg"), ...)
  if (!"pdf" %in% formats) return(invisible())
  svg <- readLines(file.path(dir, paste0(name, ".svg")), warn = FALSE, encoding = "UTF-8")
  file <- file.path(dir, paste0(name, ".pdf"))
  other_font <- any(grepl('font-family: "(?!Arial")', svg, perl = TRUE))
  # code-point checks only once the text has non-ASCII lines (PCRE needs UTF-8 input for them)
  unicode <- any(grepl("[^\\x01-\\x7f]", svg, perl = TRUE, useBytes = TRUE))
  beyond_latin1 <- unicode && any(grepl("[^\\x{01}-\\x{ff}]", svg, perl = TRUE))
  if ((other_font || beyond_latin1) && ais_cairo_pdf(p, size, file)) return(invisible())
  cjk <- unicode && any(grepl("[\\x{2e80}-\\x{9fff}\\x{ac00}-\\x{d7af}\\x{ff00}-\\x{ffef}]", svg, perl = TRUE))
  if (other_font || cjk) {
    stop("This figure has Chinese text or a non-Arial font, which needs R's Cairo PDF device. ",
         "On macOS install XQuartz (brew install --cask xquartz) and try again.", call. = FALSE)
  }
  labstyle::save_fig(p, name, dir = dir, size = size, formats = "pdf", ...)
}

ais_cairo_pdf <- function(p, size, file) {
  opened <- tryCatch({ grDevices::cairo_pdf(file, width = size[1], height = size[2], family = "Arial"); TRUE },
                     warning = function(w) FALSE, error = function(e) FALSE)
  if (!opened) return(FALSE)
  on.exit(grDevices::dev.off(), add = TRUE)
  if (inherits(p, "grob")) grid::grid.draw(p) else print(p)
  TRUE
}
