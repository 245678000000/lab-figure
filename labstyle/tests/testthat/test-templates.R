test_that("lab_roc: single curve, Youden and multi-curve", {
  p <- lab_roc(roc_data(), "outcome", "s100b")
  expect_renders(p)
  s <- lab_stats(p)
  expect_equal(round(s$auc, 3), 0.731)  # pROC's documented AUC for aSAH s100b
  expect_equal(attr(p, "lab_size"), "roc")

  py <- lab_roc(roc_data(), "outcome", "s100b", youden = TRUE)
  expect_true("youden_cutoff" %in% names(lab_stats(py)))
  expect_renders(py)

  pm <- lab_roc(roc_data(), "outcome", c("s100b", "ndka", "wfns"))
  expect_equal(nrow(lab_stats(pm)), 3)
  expect_renders(pm)
})

test_that("lab_km: score split, explicit group, >2 groups", {
  p <- lab_km(lung_data(), "time", "status", score = "age")
  expect_renders(p)
  s <- lab_stats(p)
  expect_equal(s$test, "cox")
  expect_true(s$hr > 0 && s$p > 0)

  pg <- lab_km(lung_data(), "time", "status", group = "sex", risk_table = FALSE)
  expect_renders(pg)

  d <- lung_data()
  d$ecog <- factor(d$ph.ecog)
  p3 <- lab_km(d[d$ph.ecog %in% 0:2, ], "time", "status", group = "ecog")
  expect_equal(lab_stats(p3)$test, "logrank")
  expect_renders(p3)
})

test_that("lab_cox_table + lab_forest", {
  tab <- lab_cox_table(lung_data(), "time", "status", c("age", "sex", "ph.ecog"))
  expect_equal(nrow(tab), 3)
  expect_true(all(c("term", "estimate", "lower", "upper", "p") %in% names(tab)))
  p <- lab_forest(tab)
  expect_renders(p)
  expect_equal(attr(p, "lab_size")[1], 5.5)
})

test_that("lab_box and lab_violin compute the Wilcoxon test", {
  p <- lab_box(ToothGrowth, "supp", "len")
  expect_renders(p)
  expect_equal(lab_stats(p)$p,
               suppressWarnings(wilcox.test(len ~ supp, data = ToothGrowth))$p.value)

  # no ties, n < 50: exact p, as wilcox.test's default in the original code
  d <- data.frame(g = rep(c("A", "B"), each = 8), v = c(1:8, 5.5 + 1:8))
  expect_equal(lab_stats(lab_box(d, "g", "v"))$p, wilcox.test(v ~ g, data = d)$p.value)

  d <- ToothGrowth
  d$dose <- factor(d$dose)
  p3 <- lab_box(d, "dose", "len", comparisons = "all")
  expect_equal(nrow(lab_stats(p3)), 3)
  expect_renders(p3)

  pv <- lab_violin(ToothGrowth, "supp", "len")
  expect_renders(pv)
})

test_that("lab_box keeps the p-value bracket inside a fixed ylim", {
  p <- lab_box(ToothGrowth, "supp", "len", ylim = c(0, 40))
  b <- ggplot2::ggplot_build(p)
  label_y <- unlist(lapply(b$data, function(l) if ("label" %in% names(l)) l$y))
  expect_length(label_y, 1)
  expect_lt(label_y, 40)
})

test_that("lab_rate_bar reports OR as in calc_group_rate_or", {
  d <- data.frame(group = rep(c("Low", "High"), each = 20),
                  event = c(rep(1, 4), rep(0, 16), rep(1, 12), rep(0, 8)))
  p <- lab_rate_bar(d, "group", "event", levels = c("Low", "High"))
  s <- lab_stats(p)
  expect_equal(s$rate, c(20, 60))
  expect_equal(s$or[1], round((60 / 40) / (20 / 80), 1))
  expect_renders(p)
})

test_that("lab_auc_table + lab_auc_bar, with and without datasets", {
  tab <- lab_auc_table(roc_data(), "outcome", c("s100b", "ndka", "wfns"))
  expect_equal(nrow(tab), 3)
  expect_renders(lab_auc_bar(tab))

  d <- roc_data()
  by_ds <- lab_auc_table(d, "outcome", c("s100b", "ndka"), by = "gender")
  expect_equal(nrow(by_ds), 4)
  expect_renders(lab_auc_bar(by_ds, dataset = "dataset"))
})

test_that("lab_cor_heatmap and lab_pie", {
  p <- lab_cor_heatmap(mtcars, c("mpg", "disp", "hp", "wt", "qsec"))
  expect_equal(nrow(lab_stats(p)), 25)
  expect_renders(p)
  expect_renders(lab_cor_heatmap(mtcars, c("mpg", "hp"), c("wt", "qsec", "drat")))

  pie <- lab_pie(mtcars, "cyl")
  expect_equal(sum(lab_stats(pie)$count), nrow(mtcars))
  expect_renders(pie)
})

test_that("template size survives adding layers", {
  p <- lab_box(ToothGrowth, "supp", "len") + labs(y = "Tooth length")
  expect_equal(attr(p, "lab_size"), "narrow")
})
