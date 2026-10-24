# ---- data ----
library(labstyle)
d <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort10", skip = 1)
d$Response <- ifelse(d$`Best response` %in% c("CR", "PR", "SD"), "DC", "PD")
cells <- c("B_cells", "CD8_T_cells", "Tregs", "NK_cells", "Macrophages_M2")

# ---- plot ----
tab <- lab_auc_table(d, outcome = "Response", predictors = cells, positive = "DC")
p <- lab_auc_bar(tab)
save_fig(p, "auc_bar", dir = "examples/out")
tab
