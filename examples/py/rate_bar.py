# ---- data ----
import pandas as pd
from labstyle_py import lab_rate_bar, lab_stats, save_fig

d = pd.read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet_name="Cohort10", header=1)
d["Response"] = d["Best response"].isin(["CR", "PR", "SD"]).astype(int)
d["B_group"] = (d["B_cells"] > d["B_cells"].median()).map({True: "High", False: "Low"})

# ---- plot ----
fig = lab_rate_bar(d, group="B_group", outcome="Response", levels=["Low", "High"],
                   ylab="Disease control (%)")
save_fig(fig, "rate_bar", dir="examples/out/py")
print(lab_stats(fig))
