#' P-value text as in the original analysis code: 2 decimals when p >= 0.05,
#' 3 decimals down to 0.0095, scientific notation below that.
format_p_value <- function(p) {
  vapply(p, function(x) {
    if (is.na(x)) return(NA_character_)
    if (x >= 0.05) return(as.character(round(x, 2)))
    if (x >= 0.0095) return(as.character(round(x, 3)))
    format(x, scientific = TRUE, digits = 2)
  }, character(1), USE.NAMES = FALSE)
}

p_to_symbol <- function(p) {
  vapply(p, function(x) {
    if (is.na(x)) return("ns")
    if (x < 0.001) return("***")
    if (x < 0.01) return("**")
    if (x < 0.05) return("*")
    "ns"
  }, character(1), USE.NAMES = FALSE)
}

#' Statistics a template computed (AUC, HR, p values, ...), as a data frame.
lab_stats <- function(p) attr(p, "lab_stats")
