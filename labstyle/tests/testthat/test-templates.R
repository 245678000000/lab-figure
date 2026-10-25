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

test_that("lab_roc shows class sizes under the AUC", {
  p <- lab_roc(roc_data(), "outcome", "s100b")
  expect_equal(lab_stats(p)$n_pos, sum(roc_data()$outcome == "Poor"))
  expect_equal(lab_stats(p)$n_neg, sum(roc_data()$outcome == "Good"))
  label <- ggplot2::ggplot_build(p)$data[[3]]$label
  expect_equal(label, "AUC = 0.73\n95% CI 0.63-0.83\nn: Poor 41, Good 72")
  no_n <- ggplot2::ggplot_build(lab_roc(roc_data(), "outcome", "s100b", show_n = FALSE))
  expect_false(grepl("n:", no_n$data[[3]]$label))
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

test_that("lab_km puts group sizes in the legend", {
  p <- lab_km(lung_data(), "time", "status", group = "sex", risk_table = FALSE)
  legend <- ggplot2::get_guide_data(p, "colour")$.label
  expect_equal(legend, c("Male (n = 138)", "Female (n = 90)"))
  expect_equal(lab_stats(p)$n_by_group, "Male: 138; Female: 90")
})

test_that("lab_cox_table + lab_forest", {
  tab <- lab_cox_table(lung_data(), "time", "status", c("age", "sex", "ph.ecog"))
  expect_equal(nrow(tab), 3)
  expect_true(all(c("term", "estimate", "lower", "upper", "p") %in% names(tab)))
  p <- lab_forest(tab)
  expect_renders(p)
  expect_true(attr(p, "lab_size")[1] > 5.5)   # wider for the CI column

  est_text <- ggplot2::ggplot_build(p[[1]])$data[[1]]$label
  expect_equal(est_text[1], sprintf("%.2f (%.2f-%.2f)", tab$estimate[1], tab$lower[1], tab$upper[1]))
  expect_equal(est_text[length(est_text)], "HR (95% CI)")

  plain <- lab_forest(tab, ci_text = FALSE)
  expect_lt(attr(plain, "lab_size")[1], attr(p, "lab_size")[1])
  expect_equal(ggplot2::ggplot_build(plain[[1]])$data[[1]]$label[1], sprintf("%.3f", tab$estimate[1]))
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

test_that("lab_box and lab_violin label groups with their sizes", {
  box_x <- ggplot2::layer_scales(lab_box(ToothGrowth, "supp", "len"))$x$get_labels()
  expect_equal(box_x, c("OJ\n(n = 30)", "VC\n(n = 30)"))        # short names: upright
  long <- data.frame(g = rep(c("Mild or no irAE", "Severe irAE"), each = 5), v = 1:10)
  long_x <- ggplot2::layer_scales(lab_box(long, "g", "v"))$x$get_labels()
  expect_equal(long_x, c("Mild or no irAE (n = 5)", "Severe irAE (n = 5)"))  # long: 45 degrees
  violin_x <- ggplot2::layer_scales(lab_violin(ToothGrowth, "supp", "len"))$x$get_labels()
  expect_equal(violin_x, c("OJ\n(n = 30)", "VC\n(n = 30)"))
  plain <- ggplot2::layer_scales(lab_box(ToothGrowth, "supp", "len", show_n = FALSE))$x$get_labels()
  expect_equal(plain, c("OJ", "VC"))
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
  expect_equal(round(s$or[1], 1), round((60 / 40) / (20 / 80), 1))
  expect_renders(p)
})

test_that("lab_rate_bar OR CI matches logistic regression; Fisher p; counts", {
  d <- data.frame(group = factor(rep(c("Low", "High"), each = 17), levels = c("Low", "High")),
                  event = c(rep(1, 4), rep(0, 13), rep(1, 8), rep(0, 9)))
  s <- lab_stats(lab_rate_bar(d, "group", "event"))
  wald <- exp(confint.default(glm(event ~ group, family = binomial, data = d)))["groupHigh", ]
  # glm converges iteratively (to ~1e-6); the 2x2 formula is exact
  expect_equal(c(s$or_lower[1], s$or_upper[1]), unname(wald), tolerance = 1e-5)
  expect_equal(round(c(s$or_lower[1], s$or_upper[1]), 2), c(0.66, 12.57))  # old-way run, HNSCC data
  expect_equal(s$fisher_p[1], fisher.test(table(d$group, d$event))$p.value)

  labels <- unlist(lapply(ggplot2::ggplot_build(lab_rate_bar(d, "group", "event"))$data,
                          function(l) l$label))
  expect_true(all(c("4/17", "8/17") %in% labels))
  expect_true(any(grepl("OR = 2.9\n\\(0.7-12.6\\)\np = 0.28", labels)))

  zero <- data.frame(group = rep(c("A", "B"), each = 5), event = c(rep(0, 5), 1, 1, 0, 0, 0))
  expect_true(is.finite(lab_stats(lab_rate_bar(zero, "group", "event"))$or_upper[1]))
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
  vars <- c("mpg", "disp", "hp", "wt", "qsec")
  p <- lab_cor_heatmap(mtcars, vars)
  s <- lab_stats(p)
  expect_equal(nrow(s), 10)                                    # each pair once
  expect_equal(s$p_adj, p.adjust(s$p, "BH"))
  expect_equal(nrow(ggplot2::ggplot_build(p)$data[[1]]), 10)   # lower triangle only
  expect_renders(p)

  full <- lab_cor_heatmap(mtcars, vars, triangle = "full", p_adjust = "none")
  expect_equal(nrow(ggplot2::ggplot_build(full)$data[[1]]), 25)
  expect_equal(nrow(lab_stats(full)), 10)
  expect_equal(lab_stats(full)$p_adj, lab_stats(full)$p)

  rect <- lab_cor_heatmap(mtcars, c("mpg", "hp"), c("wt", "qsec", "drat"))
  expect_equal(nrow(lab_stats(rect)), 6)
  expect_renders(rect)

  pie <- lab_pie(mtcars, "cyl")
  expect_equal(sum(lab_stats(pie)$count), nrow(mtcars))
  expect_renders(pie)
})

test_that("template size survives adding layers", {
  p <- lab_box(ToothGrowth, "supp", "len", show_n = FALSE) + labs(y = "Tooth length")
  expect_equal(attr(p, "lab_size"), "narrow")
  p_n <- lab_box(ToothGrowth, "supp", "len") + labs(y = "Tooth length")
  expect_equal(attr(p_n, "lab_size"), c(1.95, 3.3))
})
