# Live-preview worker for the editor extension: a long-running R process that
# reads one JSON request per line on stdin and writes one JSON response per
# line on stdout.
#
#   {"id": 1, "cmd": "render", "path": "/abs/fig.R", "code": "...", "cwd": "/abs/project",
#    "size": null | "wide" | [w, h]}
#   {"id": 2, "cmd": "reset"}    drop the cached data section
#   {"id": 3, "cmd": "ping"}
#
# A render evaluates the script's data section (above "# ---- plot ----") only
# when its text or working directory changed, then the plot section in a fresh
# child environment. save_fig() calls are captured instead of writing files and
# returned as SVG. Anything the script prints is returned in `output`.

.preview <- new.env(parent = emptyenv())
.preview$active <- FALSE
.preview$figures <- list()

.plot_marker <- "^\\s*#\\s*-+\\s*plot\\s*-+\\s*$"

#' Run the preview worker until stdin closes. Used by the editor extension.
serve <- function() {
  grDevices::pdf(NULL)  # plots printed by scripts go nowhere instead of Rplots.pdf
  cache <- new.env(parent = emptyenv())
  input <- file("stdin")
  open(input)
  on.exit(close(input), add = TRUE)
  .serve_reply(list(event = "ready", r = R.version.string,
                    labstyle = as.character(utils::packageVersion("labstyle"))))
  repeat {
    line <- readLines(input, n = 1, warn = FALSE)
    if (length(line) == 0) break
    if (!nzchar(trimws(line))) next
    req <- tryCatch(jsonlite::fromJSON(line, simplifyVector = TRUE), error = function(e) NULL)
    if (is.null(req)) {
      .serve_reply(list(ok = FALSE, error = "request is not valid JSON"))
      next
    }
    res <- switch(req$cmd %||% "",
      render = .serve_render(req, cache),
      reset = {
        rm(list = ls(cache), envir = cache)
        list(ok = TRUE)
      },
      ping = list(ok = TRUE),
      list(ok = FALSE, error = paste0("unknown cmd: ", req$cmd %||% "<none>"))
    )
    res$id <- req$id
    .serve_reply(res)
  }
  invisible()
}

.serve_reply <- function(x) {
  cat(jsonlite::toJSON(x, auto_unbox = TRUE, null = "null", na = "null", digits = NA,
                       force = TRUE), "\n", sep = "", file = stdout())
  flush(stdout())
}

.serve_render <- function(req, cache) {
  started <- Sys.time()
  path <- req$path %||% "<preview>"
  cwd <- req$cwd %||% getwd()
  old_wd <- setwd(cwd)
  on.exit(setwd(old_wd), add = TRUE)

  lines <- strsplit(req$code %||% "", "\n", fixed = TRUE)[[1]]
  exprs <- tryCatch(
    parse(text = lines, keep.source = TRUE, srcfile = srcfilecopy(path, lines)),
    error = function(e) e
  )
  if (inherits(exprs, "error")) {
    return(.serve_error(conditionMessage(exprs), .parse_error_line(conditionMessage(exprs)),
                        "parse", started))
  }

  marker <- grep(.plot_marker, lines)[1]
  srcrefs <- attr(exprs, "srcref")
  first_line <- vapply(srcrefs, function(s) s[1], integer(1))
  in_data <- if (is.na(marker)) rep(FALSE, length(exprs)) else first_line < marker
  data_key <- paste(c(cwd, lines[seq_len(if (is.na(marker)) 0 else marker - 1)]), collapse = "\n")

  log <- new.env(parent = emptyenv())
  log$output <- character()
  log$warnings <- character()
  cached <- identical(cache$key, data_key) && !is.null(cache$env)
  if (!cached) {
    denv <- new.env(parent = globalenv())
    err <- .serve_eval(exprs[in_data], srcrefs[in_data], denv, path, log)
    if (!is.null(err)) {
      rm(list = ls(cache), envir = cache)
      return(.serve_error(err$message, err$line, "data", started, log))
    }
    cache$key <- data_key
    cache$env <- denv
  }

  penv <- new.env(parent = cache$env)
  .preview$active <- TRUE
  .preview$figures <- list()
  on.exit({
    .preview$active <- FALSE
    .preview$figures <- list()
  }, add = TRUE)
  err <- .serve_eval(exprs[!in_data], srcrefs[!in_data], penv, path, log)
  if (!is.null(err)) return(.serve_error(err$message, err$line, "plot", started, log, cached))

  figures <- .preview$figures
  if (length(figures) == 0 && exists("p", envir = penv, inherits = FALSE)) {
    p <- get("p", envir = penv)
    figures <- list(list(plot = p, name = "p",
                         size = .resolve_size(attr(p, "lab_size") %||% "single")))
  }
  if (length(figures) == 0) {
    return(.serve_error("no figure: call save_fig(p, ...) or assign the plot to `p`",
                        NA_integer_, "plot", started, log, cached))
  }

  override <- req$size
  out <- list()
  for (fig in figures) {
    wh <- if (is.null(override)) fig$size else .resolve_size(override)
    svg <- tryCatch(.serve_svg(fig$plot, wh), error = function(e) e)
    if (inherits(svg, "error")) {
      return(.serve_error(paste0("drawing ", fig$name, ": ", conditionMessage(svg)),
                          NA_integer_, "draw", started, log, cached))
    }
    stats <- attr(fig$plot, "lab_stats")
    out[[length(out) + 1]] <- list(name = fig$name, width = wh[1], height = wh[2], svg = svg,
                                   stats = if (is.data.frame(stats)) stats else NULL)
  }
  list(ok = TRUE, figures = out, cached = cached,
       ms = round(as.numeric(difftime(Sys.time(), started, units = "secs")) * 1000),
       output = paste(log$output, collapse = "\n"), warnings = unique(log$warnings))
}

# Evaluates top-level expressions; returns NULL or list(message, line).
# Each one is evaluated with its srcref attached, so calls it makes carry
# script line numbers (as source() does).
.serve_eval <- function(exprs, srcrefs, env, path, log) {
  for (i in seq_along(exprs)) {
    err_line <- srcrefs[[i]][1]
    ei <- exprs[i]
    attr(ei, "srcref") <- srcrefs[i]
    result <- NULL
    out <- utils::capture.output(
      result <- withCallingHandlers(
        tryCatch({
          v <- withVisible(eval(ei, env))
          if (v$visible && !is.null(v$value)) print(v$value)
          NULL
        }, error = function(e) e),
        warning = function(w) {
          log$warnings <- c(log$warnings, conditionMessage(w))
          invokeRestart("muffleWarning")
        },
        message = function(m) {
          log$output <- c(log$output, sub("\n$", "", conditionMessage(m)))
          invokeRestart("muffleMessage")
        },
        error = function(e) {
          # the innermost call made from this script gives the most precise line
          for (cl in rev(sys.calls())) {
            sr <- attr(cl, "srcref")
            sf <- if (!is.null(sr)) attr(sr, "srcfile") else NULL
            if (!is.null(sf) && identical(sf$filename, path)) {
              err_line <<- sr[1]
              break
            }
          }
        }
      ),
      type = "output"
    )
    log$output <- c(log$output, out)
    if (inherits(result, "error")) return(list(message = conditionMessage(result), line = err_line))
  }
  NULL
}

.serve_svg <- function(p, wh) {
  s <- svglite::svgstring(width = wh[1], height = wh[2], standalone = TRUE)
  dev <- grDevices::dev.cur()
  on.exit(grDevices::dev.off(dev), add = TRUE)
  if (inherits(p, "grob") || inherits(p, "gtable")) grid::grid.draw(p) else print(p)
  grDevices::dev.off(dev)
  on.exit()
  as.character(s())
}

.serve_error <- function(message, line, section, started, log = NULL, cached = FALSE) {
  list(ok = FALSE, error = message, line = if (is.na(line)) NULL else line, section = section,
       cached = cached,
       ms = round(as.numeric(difftime(Sys.time(), started, units = "secs")) * 1000),
       output = if (is.null(log)) "" else paste(log$output, collapse = "\n"),
       warnings = if (is.null(log)) list() else unique(log$warnings))
}

.parse_error_line <- function(msg) {
  m <- regmatches(msg, regexpr(":([0-9]+):[0-9]+:", msg))
  if (length(m)) as.integer(sub("^:([0-9]+):.*", "\\1", m)) else NA_integer_
}
