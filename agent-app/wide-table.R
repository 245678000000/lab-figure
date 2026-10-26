# Read the frozen CSV without read.table's quadratic overhead for very wide lists.
# The schema records column order and types; no values or feature choices are inferred.
ais_read_wide <- function() {
  schema <- jsonlite::fromJSON("source-schema.json")
  count <- length(schema$columns)
  values <- scan("source_data.csv", what = "", sep = ",", quote = "\"",
                 quiet = TRUE, comment.char = "", blank.lines.skip = FALSE,
                 na.strings = character(0), encoding = "UTF-8")
  if (count < 1 || length(values) != count * (schema$rows + 1))
    stop("Source CSV dimensions differ from source-schema.json")
  if (!identical(values[seq_len(count)], schema$columns))
    stop("Source CSV column names differ from source-schema.json")
  cells <- matrix(values[-seq_len(count)], ncol = count, byrow = TRUE)
  result <- lapply(seq_len(count), function(i) {
    column <- cells[, i]
    if (schema$types[i] == "numeric") return(as.numeric(column))
    if (schema$types[i] == "logical") return(as.logical(column))
    column
  })
  names(result) <- schema$columns
  class(result) <- "data.frame"
  attr(result, "row.names") <- seq_len(schema$rows)
  result
}
