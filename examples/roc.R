# ---- data ----
library(labstyle)
d <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort10", skip = 1)
d$Response <- ifelse(d$`Best response` %in% c("CR", "PR"), "R", "NR")

# ---- plot ----
p <- lab_roc(d, outcome = "Response", predictor = "B_cells", positive = "R")
save_fig(p, "roc", dir = "examples/out")
lab_stats(p)
