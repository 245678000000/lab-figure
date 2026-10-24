# ---- data ----
library(labstyle)
d <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort11", skip = 1)
d$Stage <- sub("[ABC]$", "", d$`TNM stage`)

# ---- plot ----
p <- lab_pie(d[!is.na(d$Stage), ], category = "Stage", levels = c("I", "II", "III", "IV"))
save_fig(p, "pie", dir = "examples/out")
