# Built-in datasets used across the template tests.
roc_data <- function() {
  d <- pROC::aSAH
  d$outcome <- factor(d$outcome, levels = c("Good", "Poor"))
  d
}

lung_data <- function() {
  d <- survival::lung
  d$sex <- factor(d$sex, levels = c(1, 2), labels = c("Male", "Female"))
  d
}

# Draws the plot on a throwaway device so layout/stat errors surface.
expect_renders <- function(p) {
  f <- tempfile(fileext = ".pdf")
  grDevices::pdf(f, width = 5, height = 4)
  on.exit({
    grDevices::dev.off()
    unlink(f)
  })
  expect_no_error(print(p))
}
