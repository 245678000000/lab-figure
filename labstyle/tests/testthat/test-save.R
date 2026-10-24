test_that("save_fig writes pdf + png at the template's preset size", {
  dir <- tempfile()
  p <- lab_roc(roc_data(), "outcome", "s100b")
  paths <- save_fig(p, "roc", dir = dir, data = roc_data())
  expect_true(all(file.exists(paths)))
  expect_equal(basename(paths), c("roc.pdf", "roc.png", "roc_source_data.csv"))

  # PDF MediaBox is in points: 2.7 x 2.2 in -> 194.4 x 158.4 (R may round)
  raw <- readBin(paths[1], "raw", file.size(paths[1]))
  box <- rawToChar(grepRaw("/MediaBox \\[[^]]+\\]", raw, value = TRUE))
  expect_match(box, "194(\\.\\d+)? 158")
})

test_that("save_fig accepts explicit sizes and rejects unknown presets", {
  dir <- tempfile()
  p <- ggplot2::ggplot(mtcars, ggplot2::aes(wt, mpg)) + ggplot2::geom_point() + theme_lab()
  expect_no_error(save_fig(p, "x.pdf", size = c(3, 2), dir = dir, formats = "pdf"))
  expect_true(file.exists(file.path(dir, "x.pdf")))
  expect_error(save_fig(p, "x", size = "huge", dir = dir), "unknown size preset")
})
