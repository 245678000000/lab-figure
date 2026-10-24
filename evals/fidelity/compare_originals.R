# Draws the same data with the advisor's original helper functions and with
# the labstyle templates, for a side-by-side check. Run from the repo root:
#   Rscript evals/fidelity/compare_originals.R
#   .venv/bin/python -I evals/fidelity/side_by_side.py
suppressPackageStartupMessages({
  library(labstyle)
  library(ggplot2)
  library(dplyr)
  library(tidyr)
  library(survival)
  library(survminer)
  library(forestplot)
  library(ggsignif)
  library(grid)
})

out <- "evals/fidelity/out"
dir.create(file.path(out, "original"), recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(out, "template"), recursive = TRUE, showWarnings = FALSE)

# Load only the plotting helpers from the original utils.R (sourcing it whole
# would pull in Bioconductor packages the plots do not need).
wanted <- c("save_roc_plot", "save_km_plot", "save_forest_plot", "save_feature_boxplot",
            "save_irAE_barplot", "calc_group_rate_or", "format_p_value", "save_pdf")
exprs <- parse("evals/fidelity/original_utils.R", keep.source = FALSE)
orig <- new.env(parent = globalenv())
for (e in exprs) {
  if (is.call(e) && identical(e[[1]], as.name("<-")) && as.character(e[[2]]) %in% wanted) {
    eval(e, orig)
  }
}
orig$result_figure_dir <- file.path(out, "original")

hnscc10 <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort10", skip = 1)
hnscc11 <- readxl::read_excel("evals/data/hnscc_inhouse_cohorts.xlsx", sheet = "Cohort11", skip = 1)
hnscc10$Response <- ifelse(hnscc10$`Best response` %in% c("CR", "PR", "SD"), "DC", "PD")

# ROC ----
roc_data <- data.frame(phenotype = as.integer(hnscc10$Response == "DC"), feature = hnscc10$B_cells)
orig$save_roc_plot(roc_data, "roc.pdf")
save_fig(lab_roc(hnscc10, "Response", "B_cells", positive = "DC"), "roc",
         dir = file.path(out, "template"), formats = "pdf")

# Kaplan-Meier ----
km_df <- data.frame(B_cells = hnscc10$B_cells, OS_time = hnscc10$`OS months`,
                    OS_event = hnscc10$`OS status`)
orig$save_km_plot(km_df, "B_cells", "OS", "cohort10", xlim_max = 60)
file.rename(file.path(out, "original", "KM_curve_OS_B_cells_cohort10.pdf"),
            file.path(out, "original", "km.pdf"))
save_fig(lab_km(hnscc10, "OS months", "OS status", score = "B_cells", xmax = 60, break_by = 10,
                ylab = "Overall \nsurvival probability"),
         "km", dir = file.path(out, "template"), formats = "pdf")

# Forest ----
hnscc11$NLR_high <- as.integer(hnscc11$NLR > median(hnscc11$NLR))
hnscc11$Sex <- factor(hnscc11$Sex, levels = c("FEMALE", "MALE"))
tab <- lab_cox_table(hnscc11, "OS months", "OS status",
                     terms = c("NLR_high", "Blood albumin (g/dl)", "Sex"),
                     labels = c("NLR high", "Albumin", "Male sex"))
orig$save_forest_plot(data.frame(Variable = tab$term, mean = tab$estimate, lower = tab$lower,
                                 upper = tab$upper, pval = tab$p),
                      "forest.pdf", "Hazard ratio")
save_fig(lab_forest(tab, xlim = c(0, 4), xbreaks = 0:3), "forest",
         dir = file.path(out, "template"), formats = "pdf")

# Box ----
lab_names <- c(PD = "Mild or no irAE", DC = "Severe irAE")  # labels hard-coded in the original
box_data <- data.frame(phenotype_label = factor(lab_names[hnscc10$Response], levels = lab_names),
                       feature = hnscc10$B_cells / 100)
orig$save_feature_boxplot(box_data, "box.pdf", ylabel = "B cells (%)", ylim = 60)
save_fig(lab_box(box_data, "phenotype_label", "feature", percent = TRUE, ylab = "B cells (%)",
                 ylim = c(0, 60)),
         "box", dir = file.path(out, "template"), formats = "pdf")

# Rate bar ----
bar_data <- data.frame(group = factor(ifelse(hnscc10$B_cells > median(hnscc10$B_cells), "High", "Low"),
                                      levels = c("Low", "High")),
                       phenotype = as.integer(hnscc10$Response == "DC"))
orig$save_irAE_barplot(bar_data, "rate_bar.pdf")
save_fig(lab_rate_bar(bar_data, "group", "phenotype", ylab = "Severe irAE (%)"), "rate_bar",
         dir = file.path(out, "template"), formats = "pdf")

cat("wrote", out, "\n")
