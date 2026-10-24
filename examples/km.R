# ---- data ----
library(labstyle)
d <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort10", skip = 1)

# ---- plot ----
p <- lab_km(d, time = "OS months", event = "OS status", score = "B_cells",
            ylab = "Overall\nsurvival probability")
save_fig(p, "km", dir = "examples/out")
lab_stats(p)
