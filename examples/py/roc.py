# ---- data ----
import pandas as pd
from labstyle_py import lab_roc, lab_stats, save_fig

d = pd.read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet_name="Cohort10", header=1)
d["Response"] = d["Best response"].isin(["CR", "PR"]).map({True: "R", False: "NR"})

# ---- plot ----
fig = lab_roc(d, outcome="Response", predictor="B_cells", positive="R")
save_fig(fig, "roc", dir="examples/out/py")
print(lab_stats(fig))
