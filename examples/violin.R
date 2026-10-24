# ---- data ----
library(labstyle)
d <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort11", skip = 1)

# ---- plot ----
p <- lab_violin(d, x = "Status of stage", y = "NLR", ylab = "NLR")
save_fig(p, "violin", dir = "examples/out")
lab_stats(p)
