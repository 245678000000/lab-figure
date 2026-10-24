# ---- data ----
library(labstyle)
d <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort10", skip = 1)
d$Response <- ifelse(d$`Best response` %in% c("CR", "PR"), "R", "NR")

# ---- plot ----
p <- lab_box(d, x = "Response", y = "B_cells", levels = c("NR", "R"), ylab = "B cells (%)")
save_fig(p, "box", dir = "examples/out")
lab_stats(p)
