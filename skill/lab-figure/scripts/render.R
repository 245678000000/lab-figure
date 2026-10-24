# Run a figure script with labstyle loaded; report outputs, timing, and the
# script line of any error. Usage: Rscript render.R figures/roc.R
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) stop("usage: Rscript render.R <figure.R>")
file <- normalizePath(args[1], mustWork = TRUE)

suppressPackageStartupMessages(library(labstyle))
started <- Sys.time()
err_line <- NA_integer_

result <- withCallingHandlers(
  tryCatch({
    source(file, local = new.env(), keep.source = TRUE, print.eval = TRUE)
    NULL
  }, error = function(e) e),
  error = function(e) {
    for (cl in rev(sys.calls())) {
      sr <- attr(cl, "srcref")
      sf <- if (!is.null(sr)) attr(sr, "srcfile") else NULL
      if (!is.null(sf) && identical(normalizePath(sf$filename, mustWork = FALSE), file)) {
        err_line <<- sr[1]
        break
      }
    }
  }
)

elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
if (inherits(result, "error")) {
  msg <- conditionMessage(result)
  if (is.na(err_line)) {
    parse_pos <- regmatches(msg, regexpr("^[^:]*:([0-9]+):[0-9]+:", msg))
    if (length(parse_pos)) err_line <- as.integer(sub("^[^:]*:([0-9]+):.*", "\\1", parse_pos))
  }
  cat(sprintf("ERROR%s: %s\n", if (is.na(err_line)) "" else sprintf(" (line %d)", err_line), msg))
  quit(status = 1)
}

outputs <- list.files(".", pattern = "\\.(pdf|png|svg|csv)$", recursive = TRUE, full.names = TRUE)
outputs <- outputs[file.mtime(outputs) >= started]
outputs <- outputs[!grepl("^\\./(\\.venv|renv)/", outputs)]
cat(sprintf("OK in %.1fs\n", elapsed))
if (length(outputs)) cat(paste0("  ", sub("^\\./", "", outputs)), sep = "\n")
