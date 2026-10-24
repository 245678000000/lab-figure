# Every house style value lives here. See skill/lab-figure/references/style-spec.md
# for where each one comes from in the original analysis code.

.lab_style <- list(
  base_size = 12,
  # ggplot text sizes (mm) for in-panel statistics, per template, as in the
  # originals except km (5 in save_km_plot; 4 keeps the label off the curves)
  text = list(roc = 4, km = 4, box = 4, bar = 3, forest = 4.6, heatmap = 3, small = 3),
  colors = list(
    binary = c("#00305d", "#9c1915"),
    categorical = c(
      "#1c4f27", "#81144e", "#79831e", "#00305d", "#C0C0C0",
      "#9c1915", "black", "#404040", "#808080", "#D3D3D3"
    ),
    dataset = c(
      "#1c4f27", "#81144e", "#79831e", "#00305d", "#9c1915",
      "black", "grey", "#f58231", "#e6194b", "#3cb44b", "#42d4f4"
    ),
    clusters = c(
      "#DC050C", "#FB8072", "#1965B0", "#7BAFDE", "#882E72", "#B17BA6",
      "#FF7F00", "#FDB462", "#E7298A", "#E78AC3", "#33A02C", "#B2DF8A",
      "#55A1B1", "#8DD3C7", "#A6761D", "#E6AB02", "#7570B3", "#BEAED4",
      "#666666", "#999999", "#aa8282", "#d4b7b7", "#8600bf", "#ba5ce3",
      "#808000", "#aeae5c", "#1e90ff", "#00bfff", "#56ff0d", "#ffff00",
      "#8B3800", "#4E8500", "#D70131", "#E64B35B2", "#4DBBD5B2", "#00A087B2",
      "#3C5488B2", "#F39B7FB2", "#4E8500", "#4C00FFFF", "#000DFFFF", "#0068FFFF",
      "#00C1FFFF", "#00FF24FF", "#42FF00FF", "#A8FF00FF", "#FFF90CFF",
      "#FFE247FF", "#FFDB83FF", "#4a5b67", "#91D1C2B2", "#DC0000B2", "#7E6148B2",
      "#B09C85B2", "#15b2d3", "#236e96", "#ffd700", "#f3872f", "#ff598f",
      "#4B0082", "#00FA9A", "#FFD700", "#9400D3", "#FF4500", "#DA70D6",
      "#8B0000", "#5F9EA0", "#7FFF00", "#6495ED", "#DB7093", "#FF6347",
      "#4682B4", "#FF1493", "#FFDAB9", "#ADFF2F", "#006400", "#00CED1",
      "#800080", "#FF69B4", "#1E90FF", "#B22222", "#8B4513", "#A52A2A",
      "#0000FF", "#00FF7F", "#FFB6C1", "#32CD32", "#808080", "#D2691E",
      "#4169E1", "#DAA520", "#FF4500", "#98FB98", "#CD5C5C", "#2F4F4F",
      "#00008B", "#8A2BE2", "#CD853F", "#20B2AA", "#DC143C"
    ),
    diverging = c("#00305d", "white", "#9c1915"),
    accent = "red"
  ),
  # width x height in inches
  sizes = list(
    single = c(2.3, 2.7),
    narrow = c(1.5, 3.3),
    bar2 = c(1.425, 2.565),
    roc = c(2.7, 2.2),
    roc_multi = c(3.2, 3.0),
    km = c(3.3, 3.0),
    forest = c(5.5, 3.4),
    violin = c(3.0, 4.0),
    auc_bar = c(2.0, 3.5),
    pie = c(3.6, 2.4),
    wide = c(4.6, 2.7)
  ),
  dpi = 300
)

#' House colour palettes: "binary", "categorical", "dataset", "clusters",
#' "diverging" or "accent". With `n`, returns the first n colours.
lab_colors <- function(set = "binary", n = NULL) {
  pal <- .lab_style$colors[[set]]
  if (is.null(pal)) {
    stop(sprintf("unknown palette '%s'; use one of: %s",
                 set, paste(names(.lab_style$colors), collapse = ", ")), call. = FALSE)
  }
  if (is.null(n)) return(pal)
  if (n > length(pal)) {
    stop(sprintf("palette '%s' has %d colours, %d requested", set, length(pal), n), call. = FALSE)
  }
  pal[seq_len(n)]
}

#' Named list of size presets (width, height in inches).
lab_sizes <- function() .lab_style$sizes

# Smallest house palette that has n colours.
.palette_for <- function(n) {
  if (n <= 2) return(lab_colors("binary", n))
  if (n <= 10) return(lab_colors("categorical", n))
  lab_colors("clusters", n)
}
