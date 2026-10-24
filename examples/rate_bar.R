# ---- data ----
library(labstyle)
d <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort10", skip = 1)
d$Response <- as.integer(d$`Best response` %in% c("CR", "PR", "SD"))
d$B_group <- ifelse(d$B_cells > median(d$B_cells), "High", "Low")

# ---- plot ----
p <- lab_rate_bar(d, group = "B_group", outcome = "Response", levels = c("Low", "High"),
                  ylab = "Disease control (%)")
save_fig(p, "rate_bar", dir = "examples/out")
lab_stats(p)
