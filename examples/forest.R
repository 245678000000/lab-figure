# ---- data ----
library(labstyle)
d <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort11", skip = 1)
d$NLR_high <- as.integer(d$NLR > median(d$NLR))
d$Sex <- factor(d$Sex, levels = c("FEMALE", "MALE"))

# ---- plot ----
tab <- lab_cox_table(d, "OS months", "OS status",
                     terms = c("NLR_high", "Blood albumin (g/dl)", "Sex"),
                     labels = c("NLR high", "Albumin (g/dl)", "Male sex"))
p <- lab_forest(tab)
save_fig(p, "forest", dir = "examples/out")
tab
