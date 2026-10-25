# Reference answers for evals/tasks.md, computed directly with survival /
# pROC / stats (no templates), so either arm's numbers can be checked.
#   Rscript evals/reference.R  ->  evals/reference.json
suppressPackageStartupMessages(library(survival))
xl <- "evals/data/hnscc_inhouse_cohorts.xlsx"
c10 <- as.data.frame(readxl::read_excel(xl, sheet = "Cohort10", skip = 1))
c11 <- as.data.frame(readxl::read_excel(xl, sheet = "Cohort11", skip = 1))
dc <- as.integer(c10$`Best response` %in% c("CR", "PR", "SD"))
high <- as.integer(c10$B_cells > median(c10$B_cells))

roc <- pROC::roc(dc, c10$B_cells, levels = c(0, 1), direction = "<", quiet = TRUE)
roc_ci <- as.numeric(pROC::ci.auc(roc))

km_fit <- summary(coxph(Surv(`OS months`, `OS status`) ~ high, data = c10))

c11$NLR_high <- as.integer(c11$NLR > median(c11$NLR))
c11$Sex <- factor(c11$Sex, levels = c("FEMALE", "MALE"))
fo <- summary(coxph(Surv(`OS months`, `OS status`) ~ NLR_high + `Blood albumin (g/dl)` + Sex, data = c11))

rates <- tapply(dc, high, mean)
odds <- rates / (1 - rates)

cells <- c("B_cells", "Plasma_B_cells", "CD4_T_cells", "CD8_T_cells", "Tregs",
           "NK_cells", "Macrophages_M1", "Macrophages_M2", "Neutrophils", "Fibroblasts")
r <- suppressWarnings(cor(c10[cells], method = "spearman"))
p <- outer(cells, cells, Vectorize(function(a, b) {
  suppressWarnings(cor.test(c10[[a]], c10[[b]], method = "spearman", exact = FALSE)$p.value)
}))
upper <- upper.tri(r)

ref <- list(
  roc = list(auc = roc_ci[2], lower = roc_ci[1], upper = roc_ci[3], n_dc = sum(dc), n_pd = sum(!dc)),
  km = list(hr = km_fit$conf.int[1, 1], lower = km_fit$conf.int[1, 3], upper = km_fit$conf.int[1, 4],
            p_cox = km_fit$coefficients[1, 5], p_logrank = km_fit$sctest[["pvalue"]],
            median_cutoff = median(c10$B_cells)),
  forest = data.frame(term = rownames(fo$conf.int), hr = fo$conf.int[, 1],
                      lower = fo$conf.int[, 3], upper = fo$conf.int[, 4], p = fo$coefficients[, 5],
                      row.names = NULL),
  box = list(p_wilcox = wilcox.test(c10$B_cells[dc == 1], c10$B_cells[dc == 0])$p.value,
             p_wilcox_approx = wilcox.test(c10$B_cells[dc == 1], c10$B_cells[dc == 0], exact = FALSE)$p.value),
  rate_bar = list(rate_low = unname(rates["0"]) * 100, rate_high = unname(rates["1"]) * 100,
                  or = unname(odds["1"] / odds["0"]),
                  fisher_p = fisher.test(table(high, dc))$p.value),
  heatmap = list(n_pairs = sum(upper), n_sig_005 = sum(p[upper] < 0.05),
                 r_B_Plasma = r["B_cells", "Plasma_B_cells"], r_CD4_Tregs = r["CD4_T_cells", "Tregs"])
)
jsonlite::write_json(ref, "evals/reference.json", auto_unbox = TRUE, digits = 6, pretty = TRUE)
str(ref, give.attr = FALSE)
