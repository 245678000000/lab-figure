# Omics, clinical, model, distribution and GWAS templates.

synthetic <- function(n = 80, seed = 1) {
  set.seed(seed)
  d <- data.frame(id = sprintf("P%02d", seq_len(n)), group = sample(c("A", "B", "C"), n, TRUE),
                  score = stats::rnorm(n), age = round(stats::rnorm(n, 60, 9)),
                  time = round(stats::rexp(n, 1 / 24), 1), dead = stats::rbinom(n, 1, 0.6))
  d$y <- stats::rbinom(n, 1, stats::plogis(0.8 * d$score))
  d$risk <- stats::fitted(stats::glm(y ~ score, data = d, family = stats::binomial()))
  d
}

test_that("omics templates render and report their statistics", {
  set.seed(2)
  de <- data.frame(gene = paste0("G", 1:200), lfc = stats::rnorm(200, 0, 1.5), padj = 10^-stats::runif(200, 0, 5),
                   base = stats::runif(200, 1, 1000))
  p <- lab_volcano(de, "gene", "lfc", "padj")
  s <- lab_stats(p)
  expect_equal(sum(s$genes), 200)
  expect_equal(s$genes[s$status == "Up"], sum(de$padj < 0.05 & de$lfc >= 1))
  expect_renders(p)
  expect_renders(lab_ma(de, "gene", "base", "lfc", "padj"))

  m <- data.frame(sample = paste0("S", 1:12), f1 = stats::rnorm(12), f2 = stats::rnorm(12), f3 = stats::rnorm(12),
                  grp = rep(c("x", "y"), 6))
  pca <- lab_pca(m, "sample", c("f1", "f2", "f3"), group = "grp", scaling = "column_z")
  expect_equal(sum(lab_stats(pca)$variance_explained), 1)
  expect_named(attr(pca, "lab_tables"), c("pca_coordinates", "pca_loadings"))
  expect_renders(lab_expression_heatmap(m, "sample", c("f1", "f2", "f3"), scaling = "row_z"))
  expect_renders(lab_sample_distance(m, "sample", c("f1", "f2", "f3")))

  paired <- data.frame(pair = rep(paste0("p", 1:8), each = 2), cond = rep(c("pre", "post"), 8),
                       value = c(rbind(1:8, 1:8 + 0.5 + stats::rnorm(8, 0, 0.1))))
  s <- lab_stats(lab_paired(paired, "pair", "cond", "value", reference = "pre"))
  expect_equal(s$p, stats::wilcox.test(paired$value[paired$cond == "post"], paired$value[paired$cond == "pre"],
                                       paired = TRUE, exact = FALSE)$p.value)
  expect_equal(nrow(lab_stats(lab_scatter(m, "f1", "f2"))), 2)
  expect_renders(lab_upset(data.frame(a = c(1, 1, 0, 1), b = c(0, 1, 1, 1)), c("a", "b")))
})

test_that("clinical templates sort and count patients", {
  d <- synthetic()
  d$change <- round(stats::rnorm(nrow(d), -10, 30), 1)
  p <- lab_waterfall(d, "id", "change", group = "group")
  expect_equal(sum(lab_stats(p)$n), nrow(d))
  expect_equal(sum(lab_stats(p)$n_decrease_30), sum(d$change <= -30))
  expect_renders(p)
  d$on <- stats::rbinom(nrow(d), 1, 0.3)
  s <- lab_stats(lab_swimmer(d[1:20, ], "id", "time", ongoing = "on"))
  expect_equal(s$ongoing, sum(d$on[1:20]))

  mut <- data.frame(sample = c("s1", "s1", "s2", "s2", "s3", "s3"), gene = c("TP53", "TP53", "KRAS", "TP53", "TP53", "KRAS"),
                    type = c("Missense", "Nonsense", "Missense", "Missense", "Missense", "Splice"))
  s <- lab_stats(lab_oncoprint(mut, "sample", "gene", "type"))
  expect_equal(s$gene, c("TP53", "KRAS"))
  expect_equal(s$n_altered, c(3, 2))           # two TP53 hits in s1 count once
})

test_that("prediction-model templates match their reference formulas", {
  d <- synthetic(200)
  nom <- lab_nomogram(d, c("score", "age"), outcome = "y")
  fit <- stats::glm(y ~ score + age, data = d, family = stats::binomial())
  expect_equal(lab_stats(nom)$estimate, unname(stats::coef(fit)[-1]))
  expect_renders(nom)
  cox <- lab_nomogram(d, c("score", "age"), time = "time", event = "dead", times = c(12, 24))
  expect_equal(lab_stats(cox)$hr, unname(exp(stats::coef(survival::coxph(survival::Surv(time, dead) ~ score + age, d)))))

  cal <- lab_stats(lab_calibration(d, "y", "risk"))
  expect_equal(cal$brier, mean((d$risk - d$y)^2))
  expect_equal(cal$slope, 1, tolerance = 1e-6)   # in-sample logistic fit is perfectly calibrated

  dca <- lab_stats(lab_dca(d, "y", "risk"))
  all <- dca[dca$model == "Treat all", ]
  prev <- mean(d$y)
  expect_equal(all$net_benefit, prev - (1 - prev) * all$threshold / (1 - all$threshold))
  expect_true(all(dca$net_benefit[dca$model == "Treat none"] == 0))

  # Without censoring before t, the time-dependent AUC is the plain
  # Mann-Whitney AUC of cases (event before t) against controls (after t).
  e <- data.frame(time = 1:100, dead = 1, marker = rev(1:100) + stats::rnorm(100, 0, 30))
  s <- lab_stats(lab_time_roc(e, "time", "dead", "marker", times = 50))
  cases <- e$marker[e$time < 50]
  controls <- e$marker[e$time > 50]
  expect_equal(s$auc, mean(outer(cases, controls, ">") + 0.5 * outer(cases, controls, "==")))
})

test_that("distribution templates", {
  d <- synthetic()
  expect_equal(lab_stats(lab_ridge(d, "group", "score"))$n, as.vector(table(d$group)))
  expect_renders(lab_density(d, "score", group = "group"))

  flow <- data.frame(t0 = c("SD", "SD", "PR", "PD"), t1 = c("PR", "SD", "CR", "PD"), n = c(3, 2, 4, 1))
  s <- lab_stats(lab_sankey(flow, c("t0", "t1"), count = "n"))
  expect_equal(sum(s$n), 10)
  expect_equal(s$n[s$from == "PR" & s$to == "CR"], 4)

  sets <- data.frame(a = c(1, 1, 0, 0, 1), b = c(0, 1, 1, 0, 1), c = c(0, 0, 1, 0, 1), d = c(1, 0, 0, 0, 1))
  for (k in 2:4) {
    s <- lab_stats(lab_venn(sets, names(sets)[seq_len(k)]))
    expect_equal(nrow(s), 2^k)                     # every region plus "none of the sets"
    expect_equal(sum(s$count), nrow(sets))
  }
})

test_that("GWAS templates", {
  set.seed(3)
  g <- data.frame(chr = rep(c(1:3, "X"), each = 500), pos = rep(1:500, 4) * 1000, p = stats::runif(2000))
  g$p[1] <- 1e-10
  s <- lab_stats(lab_manhattan(g, "chr", "pos", "p"))
  expect_equal(s$genome_wide, 1)
  expect_equal(lab_stats(lab_qq(g, "p"))$lambda_gc, stats::median(stats::qchisq(g$p, 1, lower.tail = FALSE)) / stats::qchisq(0.5, 1))
})
