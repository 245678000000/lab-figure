# ---- data ----
library(labstyle)
d <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort10", skip = 1)
cells <- c("B_cells", "Plasma_B_cells", "CD4_T_cells", "CD8_T_cells", "Tregs",
           "NK_cells", "Macrophages_M1", "Macrophages_M2", "Neutrophils", "Fibroblasts")

# ---- plot ----
p <- lab_cor_heatmap(d, vars = cells)
save_fig(p, "cor_heatmap", dir = "examples/out")
