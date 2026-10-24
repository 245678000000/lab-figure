# Installs what labstyle and the skill need, then labstyle itself.
# Run from the repo root:  Rscript setup/install_r_packages.R
options(repos = c(CRAN = "https://cloud.r-project.org"))
need <- c(
  # labstyle
  "ggplot2", "patchwork", "pROC", "survival", "ragg", "svglite", "testthat",
  # reading data in figure scripts
  "readxl", "openxlsx", "jsonlite",
  # only for the side-by-side check against the original helper functions
  "survminer", "forestplot", "ggpubr", "ggsignif", "dplyr", "tidyr"
)
missing <- setdiff(need, rownames(installed.packages()))
if (length(missing)) {
  install.packages(missing, type = if (.Platform$OS.type == "unix" && Sys.info()[["sysname"]] == "Darwin") "binary" else getOption("pkgType"))
}
still <- setdiff(need, rownames(installed.packages()))
if (length(still)) stop("could not install: ", paste(still, collapse = ", "))
install.packages("labstyle", repos = NULL, type = "source")
cat("labstyle", as.character(packageVersion("labstyle")), "installed\n")
