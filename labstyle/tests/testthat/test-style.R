test_that("palettes and presets match the style spec", {
  expect_equal(lab_colors("binary"), c("#00305d", "#9c1915"))
  expect_length(lab_colors("categorical"), 10)
  expect_length(lab_colors("clusters"), 100)
  expect_equal(lab_sizes()$single, c(2.3, 2.7))
  expect_error(lab_colors("nope"), "unknown palette")
  expect_error(lab_colors("binary", 3), "has 2 colours")
})

test_that("p-value formatting follows the original rules", {
  expect_equal(format_p_value(c(0.234, 0.0312, 0.00012, NA)),
               c("0.23", "0.031", "1.2e-04", NA))
  expect_equal(p_to_symbol(c(0.0005, 0.005, 0.03, 0.2, NA)),
               c("***", "**", "*", "ns", "ns"))
})

test_that("theme_lab has open axes by default and a border when boxed", {
  t <- theme_lab()
  expect_s3_class(t$panel.grid, "element_blank")
  expect_s3_class(theme_lab(boxed = TRUE)$axis.line, "element_blank")
})

test_that("binary outcome coercion", {
  expect_equal(labstyle:::.as_binary(c(0, 1, NA)), c(0L, 1L, NA))
  expect_message(r <- labstyle:::.as_binary(c(1, 2, 2)), "2 as the event")
  expect_equal(r, c(0L, 1L, 1L))
  expect_error(labstyle:::.as_binary(c("PR", "PD")), "set positive")
  expect_equal(labstyle:::.as_binary(c("PR", "PD"), positive = "PR"), c(1L, 0L))
})
