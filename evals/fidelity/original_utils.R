
result_figure_dir <- "./Figures/"
data_dir <- "./SourceData/"
dir.create(result_figure_dir, showWarnings = FALSE, recursive = TRUE)


library(AnnotationDbi)
library(binom)
library(broom)
library(circlize)
library(clusterProfiler)
library(ComplexHeatmap)
library(dplyr)
library(enrichplot)
library(forestplot)
library(ggplot2)
library(ggpubr)
library(ggrepel)
library(grid)
library(msigdbr)
library(openxlsx)
library(org.Hs.eg.db)
library(pheatmap)
library(pROC)
library(readr)
library(readxl)
library(stringr)
library(survival)
library(survminer)
library(tidyr)
library(VennDiagram)
library(fgsea)
library(scales)

phenotype_types <- c("actionable", "conventional")

pheno_feat <- "severe_irAE"

sig_feats <- c(
  "CD8T_CM_tripletORp_ratio_pre",
  "CXCL9_pre"
)

other_feats <- c(
  "CD8T_KI67p_ratio_pre",
  "CD4T_KI67p_ratio_pre",
  "Treg_KI67p_ratio_pre",
  "CD4TM_tripletORp_ratio_pre",
  "CD8T_EMRA_CD38p_ratio_pre",
  "CD4T_EM_tripletORp_ratio_pre",
  "CD4T_EM_ratio_pre",
  "CD4T_Naive_ratio_pre",
  "CXCL9_pre",
  "CXCL10_pre",
  "CXCL11_pre",
  "IFNG_pre"
)

all_feats <- unique(c(sig_feats, other_feats))

dataset_colors <- c(
  "#1c4f27", "#81144e", "#79831e", "#00305d", "#9c1915",
  "black", "grey", "#f58231", "#e6194b", "#3cb44b", "#42d4f4"
)


color_clusters <- c(
  "#DC050C", "#FB8072", "#1965B0", "#7BAFDE", "#882E72", "#B17BA6",
  "#FF7F00", "#FDB462", "#E7298A", "#E78AC3", "#33A02C", "#B2DF8A",
  "#55A1B1", "#8DD3C7", "#A6761D", "#E6AB02", "#7570B3", "#BEAED4",
  "#666666", "#999999", "#aa8282", "#d4b7b7", "#8600bf", "#ba5ce3",
  "#808000", "#aeae5c", "#1e90ff", "#00bfff", "#56ff0d", "#ffff00",
  "#8B3800", "#4E8500", "#D70131", "#E64B35B2", "#4DBBD5B2",
  "#00A087B2", "#3C5488B2", "#F39B7FB2", "#4E8500", "#4C00FFFF",
  "#000DFFFF", "#0068FFFF", "#00C1FFFF", "#00FF24FF", "#42FF00FF",
  "#A8FF00FF", "#FFF90CFF", "#FFE247FF", "#FFDB83FF", "#4a5b67",
  "#91D1C2B2", "#DC0000B2", "#7E6148B2", "#B09C85B2", "#15b2d3",
  "#236e96", "#ffd700", "#f3872f", "#ff598f", "#4B0082", "#00FA9A",
  "#FFD700", "#9400D3", "#FF4500", "#DA70D6", "#8B0000", "#5F9EA0",
  "#7FFF00", "#6495ED", "#DB7093", "#FF6347", "#4682B4", "#FF1493",
  "#FFDAB9", "#ADFF2F", "#006400", "#00CED1", "#800080", "#FF69B4",
  "#1E90FF", "#B22222", "#8B4513", "#A52A2A", "#0000FF", "#00FF7F",
  "#FFB6C1", "#32CD32", "#808080", "#D2691E", "#4169E1", "#DAA520",
  "#FF4500", "#98FB98", "#CD5C5C", "#2F4F4F", "#00008B", "#8A2BE2",
  "#CD853F", "#20B2AA", "#DC143C"
)

custom_colors <- c(
  "#1c4f27", "#81144e", "#79831e", "#00305d", "#C0C0C0",
  "#9c1915", "black", "#404040", "#808080", "#D3D3D3"
)



fig_path <- function(file) file.path(result_figure_dir, file)
data_path <- function(file) file.path(data_dir, file)

theme_clean_axis <- function(base_size = 11, x_angle = 0) {
  theme(
    panel.grid = element_blank(),
    panel.background = element_rect(fill = "white"),
    panel.border = element_blank(),
    axis.line = element_line(color = "black"),
    axis.ticks = element_line(color = "black"),
    axis.text = element_text(color = "black", size = base_size),
    axis.text.x = element_text(angle = x_angle, hjust = ifelse(x_angle == 0, 0.5, 1)),
    legend.background = element_rect(fill = NA, color = NA),
    legend.key = element_rect(fill = NA, color = NA)
  )
}

plot_pie <- function(data, suffix, colors = custom_colors) {
  data$Category <- factor(data$Category, levels = unique(data$Category))
  p <- ggplot(data, aes(x = "", y = Count, fill = Category)) +
    geom_col(width = 1) +
    coord_polar(theta = "y") +
    scale_fill_manual(values = colors) +
    theme_void() +
    theme(legend.position = "right") +
    guides(fill = guide_legend(ncol = 1, byrow = FALSE)) +
    labs(title = NULL, fill = NULL)
  save_pdf(print(p), file.path(result_figure_dir, paste0("piePlot_", suffix, ".pdf")), width = 2 * 0.6 * 3, height = 2 * 0.4 * 3)
}

make_binary_score <- function(df, score_col, high_rule = c(">=", ">")) {
  high_rule <- match.arg(high_rule)
  med <- median(df[[score_col]], na.rm = TRUE)
  ok <- !is.na(df[[score_col]])

  score <- rep(NA_character_, nrow(df))
  if (high_rule == ">=") {
    score[ok & df[[score_col]] >= med] <- "High"
    score[ok & df[[score_col]] < med] <- "Low"
  } else {
    score[ok & df[[score_col]] > med] <- "High"
    score[ok & df[[score_col]] <= med] <- "Low"
  }

  df[[score_col]] <- factor(score, levels = c("Low", "High"))
  df
}

plot_binary_rate <- function(data, group_var, group_labels, filename, y_limit = c(0, 50), width = 1.1, height = 2.5) {
  plot_df <- data %>%
    select(group = all_of(group_var), irAE) %>%
    tidyr::drop_na() %>%
    mutate(group = factor(group, levels = names(group_labels), labels = group_labels))

  ratio_df <- plot_df %>%
    group_by(group) %>%
    summarise(irAE_Ratio = mean(irAE) * 100, .groups = "drop")

  p <- ggplot(ratio_df, aes(x = group, y = irAE_Ratio, fill = group)) +
    geom_col(width = 0.6, alpha = 0.8, color = "black") +
    coord_cartesian(ylim = y_limit) +
    labs(x = NULL, y = "Severe-irAE rate (%)", title = NULL) +
    theme_clean_axis(x_angle = 45) +
    theme(legend.position = "none")

  save_pdf(print(p), file.path(result_figure_dir, filename), width = width, height = height)

  print(chisq.test(table(plot_df$group, plot_df$irAE)))
}

plot_continuous_by_irae <- function(data, value_var, y_label, filename, width = 1.2, height = 2.5) {
  plot_df <- data %>%
    select(value = all_of(value_var), irAE = IRAEactionable01) %>%
    tidyr::drop_na() %>%
    mutate(irAE = factor(ifelse(irAE == 1, "Severe irAE", "Mild or no irAE"),
                         levels = c("Mild or no irAE", "Severe irAE")))

  p <- ggplot(plot_df, aes(x = irAE, y = value, fill = irAE)) +
    geom_jitter(width = 0.15, size = 1, alpha = 0.8, color = "grey") +
    geom_boxplot(width = 0.2, outlier.shape = NA, fill = NA, color = "black") +
    labs(x = NULL, y = y_label, title = NULL) +
    theme_clean_axis(x_angle = 45) +
    theme(legend.position = "none")

  save_pdf(print(p), file.path(result_figure_dir, filename), width = width, height = height)
  print(wilcox.test(value ~ irAE, data = plot_df))
}


map_olink_names <- function(x, protein_map) {
  mapped <- protein_map[colnames(x)]
  mapped[is.na(mapped)] <- colnames(x)[is.na(mapped)]
  colnames(x) <- mapped
  x[, !duplicated(colnames(x)), drop = FALSE]
}

extract_cytof <- function(df, feature_names, pattern) {
  keep <- grepl(pattern, feature_names) &
    !grepl("_ABS$", feature_names) &
    !grepl("IGG4", feature_names)

  x <- as.matrix(df[keep])
  colnames(x) <- gsub(paste0("_", pattern, ".*"), "", colnames(x))
  x
}

extract_olink <- function(df, feature_names, pattern, suffix, protein_map) {
  keep <- grepl("OID", feature_names) & grepl(pattern, feature_names)
  x <- as.matrix(df[keep])
  colnames(x) <- gsub(suffix, "", colnames(x))
  map_olink_names(x, protein_map)
}

filter_sparse_features <- function(x, max_na_fraction = 0.5) {
  x[, colMeans(is.na(x)) <= max_na_fraction, drop = FALSE]
}

save_pdf <- function(plot_expr, file, width, height) {
  pdf(file, width = width, height = height, onefile = FALSE)
  on.exit(dev.off(), add = TRUE)
  force(plot_expr)
}

get_cor_and_p <- function(x, y, row_names, col_names) {
  cor_matrix <- matrix(NA_real_, nrow = ncol(x), ncol = ncol(y),
                       dimnames = list(row_names, col_names))
  p_matrix <- cor_matrix

  for (i in seq_len(ncol(x))) {
    for (j in seq_len(ncol(y))) {
      test <- suppressWarnings(cor.test(
        x[, i], y[, j],
        method = "spearman",
        use = "pairwise.complete.obs"
      ))
      cor_matrix[i, j] <- unname(test$estimate)
      p_matrix[i, j] <- test$p.value
    }
  }

  list(cor = cor_matrix, p = p_matrix)
}

make_severe_irAE <- function(df, grade_col = "irAE_grade", out_col = "severe_irAE") {
  if (!grade_col %in% colnames(df)) stop(sprintf("Column '%s' not found.", grade_col))
  grade <- suppressWarnings(as.numeric(df[[grade_col]]))
  df[[out_col]] <- ifelse(is.na(grade), NA, ifelse(grade >= 3, 1, 0))
  df
}

make_any_irAE <- function(df, grade_col = "irAE_grade", out_col = "severe_irAE") {
  if (!grade_col %in% colnames(df)) stop(sprintf("Column '%s' not found.", grade_col))
  grade <- suppressWarnings(as.numeric(df[[grade_col]]))
  df[[out_col]] <- ifelse(is.na(grade), NA, ifelse(grade >= 1, 1, 0))
  df
}

make_severe_irAE_drop_mild <- function(df, grade_col = "irAE_grade", out_col = "severe_irAE") {
  if (!grade_col %in% colnames(df)) {
    stop(sprintf("Column '%s' not found.", grade_col))
  }
  grade <- suppressWarnings(as.numeric(df[[grade_col]]))
  df[[out_col]] <- dplyr::case_when(
    grade >= 3 ~ 1,
    grade == 0 ~ 0,
    TRUE       ~ NA_real_
  )
  df
}

set_irAE_outcome <- function(df, phenotype_type) {
  if (phenotype_type == "actionable") {
    df$severe_irAE <- df$IRAEactionable01
  } else if (phenotype_type == "conventional") {
    df <- make_severe_irAE(df, out_col = "severe_irAE")
  }else if (phenotype_type == "any") {
    df <- make_any_irAE(df, out_col = "severe_irAE")
  }else if (phenotype_type == "drop_mild") {
    df <- make_severe_irAE_drop_mild(df, out_col = "severe_irAE")
  } else {
    stop("phenotype_type must be 'actionable', 'conventional', 'any', or 'drop_mild'.")
  }
  df
}



prepare_binary_plot_data <- function(df,
                                     feature_col,
                                     outcome_col = "severe_irAE",
                                     cutoff = NULL) {

  plot_data <- df %>%
    select(
      feature = all_of(feature_col),
      phenotype = all_of(outcome_col)
    ) %>%
    drop_na()

  # if cutoff not provided, use median
  if (is.null(cutoff)) {
    cutoff <- median(plot_data$feature, na.rm = TRUE)
  }

  plot_data <- plot_data %>%
    mutate(
      group = factor(
        ifelse(feature <= cutoff, "Low", "High"),
        levels = c("Low", "High")
      ),
      phenotype_label = factor(
        phenotype,
        levels = c(0, 1),
        labels = c("Mild or no irAE", "Severe irAE")
      )
    )

  attr(plot_data, "cutoff") <- cutoff

  plot_data
}

get_youden_cutoff <- function(plot_data) {

  roc_obj <- pROC::roc(
    response = plot_data$phenotype,
    predictor = plot_data$feature,
    levels = c(0, 1),
    direction = "<",
    quiet = TRUE
  )

  youden <- pROC::coords(
    roc_obj,
    x = "best",
    best.method = "youden",
    ret = c(
      "threshold",
      "sensitivity",
      "specificity"
    )
  )

  auc <- pROC::auc(roc_obj)

  result <- data.frame(
    cutoff = youden["threshold"],
    sensitivity = youden["sensitivity"],
    specificity = youden["specificity"],
    AUC = as.numeric(auc)
  )

  return(result)
}

calc_group_rate_or <- function(plot_data) {
  rates <- aggregate(
    phenotype ~ group,
    data = plot_data,
    FUN = function(x) mean(as.numeric(x) == 1) * 100
  )

  odds_high <- rates$phenotype[2] / (100 - rates$phenotype[2])
  odds_low <- rates$phenotype[1] / (100 - rates$phenotype[1])
  list(rates = rates, or = round(odds_high / odds_low, 1))
}


save_irAE_barplot <- function(plot_data, file_name, width = 1.5 * 0.95, height = 2.7 * 0.95,
                              phenotype_type = "") {
  stat <- calc_group_rate_or(plot_data)

  y_text <- "Severe irAE (%)"
  if (phenotype_type == "actionable"){
    y_text <- "Actionable severe irAE (%)"
  }else if (phenotype_type == "conventional"){
    y_text <- "CTCAE severe irAE (%)"
  }

  p <- ggplot(stat$rates, aes(x = group, y = phenotype, fill = group)) +
    geom_bar(stat = "identity", color = "black", width = 0.6) +
    labs(x = NULL, y = y_text) +
    ylim(0, 100) +
    theme_classic() +
    theme(
      axis.text = element_text(color = "black"),
      legend.position = "none"
    ) +
    geom_segment(aes(x = 1, xend = 2, y = 90, yend = 90), linewidth = 0.4) +
    geom_segment(aes(x = 1, xend = 1, y = 90, yend = 86), linewidth = 0.4) +
    geom_segment(aes(x = 2, xend = 2, y = 90, yend = 86), linewidth = 0.4) +
    annotate("text", x = 1.5, y = 97, label = paste0("OR = ", stat$or), size = 3)

  pdf(file.path(result_figure_dir, file_name), onefile = FALSE, width = width, height = height)
  print(p)
  dev.off()

  invisible(stat$or)
}

# useless
calc_group_rate_or2 <- function(plot_data) {

  # group order: low, high
  plot_data$group <- factor(
    plot_data$group,
    levels = c("Low", "High")
  )

  # severe irAE rate
  rates <- plot_data %>%
    group_by(group) %>%
    summarise(
      n = n(),
      events = sum(as.numeric(phenotype) == 1),
      rate = mean(as.numeric(phenotype) == 1) * 100,
      .groups = "drop"
    )

  # Wilson CI
  ci <- binom.confint(
    rates$events,
    rates$n,
    method = "wilson"
  )

  rates$lower <- ci$lower * 100
  rates$upper <- ci$upper * 100


  # logistic regression
  fit <- glm(
    phenotype ~ group,
    data = plot_data,
    family = binomial
  )

  coef <- summary(fit)$coefficients["groupHigh", ]

  OR <- exp(coef["Estimate"])
  CI <- exp(
    coef["Estimate"] + c(-1, 1) * 1.96 * coef["Std. Error"]
  )

  p <- coef["Pr(>|z|)"]

  list(
    rates = rates,
    OR = OR,
    CI_low = CI[1],
    CI_high = CI[2],
    p = p
  )
}

# useless
save_irAE_barplot2 <- function(plot_data,
                              file_name,
                              width = 1.5 * 0.95,
                              height = 2.7 * 0.95,
                              phenotype_type = NULL) {

  stat <- calc_group_rate_or2(plot_data)

  rates <- stat$rates

  y_text <- "Severe irAE (%)"
  if (phenotype_type == "actionable"){
    y_text <- "Actionable severe irAE (%)"
  }else if (phenotype_type == "conventional"){
    y_text <- "CTCAE severe irAE (%)"
  }
  
  if (stat$OR > 10000){
    stat$OR = Inf
  }
  label <- paste0(
    "OR = ",
    round(stat$OR, 1),
    " \n(",
    round(stat$CI_low, 1),
    "-",
    round(stat$CI_high, 1),
    ")\n" # ,
    # "p = ",
    # format.pval(stat$p, digits = 3)
  )


  p <- ggplot(
    rates,
    aes(
      x = group,
      y = rate,
      fill = group
    )
  ) +

    geom_bar(
      stat = "identity",
      color = "black",
      width = 0.6
    ) +

    # geom_errorbar(
    #   aes(
    #     ymin = lower,
    #     ymax = upper
    #   ),
    #   width = 0.15,
    #   linewidth = 0.4
    # ) +

    labs(
      x = NULL,
      y = y_text
    ) +

    ylim(0, 100) +

    theme_classic() +

    theme(
      axis.text = element_text(color = "black"),
      legend.position = "none"
    ) +

    annotate(
      "text",
      x = 1.5,
      y = 88,
      label = label,
      size = 3
    )


  pdf(
    file.path(result_figure_dir, file_name),
    onefile = FALSE,
    width = width,
    height = height
  )
  print(p)
  dev.off()
  invisible(stat)
}

save_feature_boxplot <- function(plot_data, file_name,width = 1.5, height = 3.3, ylabel = "% activated CD8Tcm / CD8Tcm", ylim = 90) {
  p_val <- wilcox.test(feature ~ phenotype_label, data = plot_data)$p.value

  p <- ggplot(plot_data, aes(x = phenotype_label, y = feature * 100, fill = phenotype_label)) +
    geom_jitter(aes(color = phenotype_label), width = 0.2, size = 2) +
    geom_boxplot(outlier.shape = NA, alpha = 0.5, color = "black") +
    scale_color_manual(values = c("blue", "brown")) +
    scale_fill_manual(values = c("blue", "brown")) +
    labs(x = NULL, y = ylabel) +
    coord_cartesian(
      ylim = c(0, ylim),
      clip = "off"
    ) +
    theme_classic() +
    theme(
      axis.text = element_text(color = "black"),
      axis.text.x = element_text(angle = 45, hjust = 1),
      legend.position = "none"
    ) +
    geom_signif(
      comparisons = list(c("Mild or no irAE", "Severe irAE")),
      annotations = paste0("p = ", signif(p_val, 2)),
      textsize = 4,
      y_position = 80/90*ylim,
      vjust = -0.5,
      tip_length = 0.05
    )

  pdf(file.path(result_figure_dir, file_name), onefile = FALSE, width = width, height = height)
  print(p)
  dev.off()
}

save_roc_plot <- function(plot_data, file_name) {
  roc_obj <- pROC::roc(
    response = plot_data$phenotype,
    predictor = plot_data$feature,
    levels = c(0, 1),
    direction = "<",
    quiet = TRUE
  )

  auc_ci <- pROC::ci.auc(roc_obj)
  label <- sprintf("AUC = %.2f (%.2f,%.2f)", auc_ci[2], auc_ci[1], auc_ci[3])

  roc_df <- data.frame(
    fpr = 1 - roc_obj$specificities,
    sensitivity = roc_obj$sensitivities
  ) %>%
    arrange(fpr, sensitivity) %>%
    distinct()

  p <- ggplot(roc_df, aes(x = fpr, y = sensitivity)) +
    geom_abline(slope = 1, intercept = 0, linetype = "dashed", color = "gray70") +
    geom_step(direction = "vh", color = "black", linewidth = 1) +
    coord_cartesian(xlim = c(0, 1), ylim = c(0, 1)) +
    labs(x = "1 - Specificity", y = "Sensitivity") +
    annotate("text", x = 0.17, y = 0.1, hjust = 0, label = label, size = 4) +
    theme_classic() +
    theme(axis.text = element_text(color = "black"))

  pdf(file.path(result_figure_dir, file_name), onefile = FALSE, width = 2.7, height = 2.2)
  print(p)
  dev.off()
}


save_roc_plot_with_youden <- function(plot_data, file_name) {

  roc_obj <- pROC::roc(
    response = plot_data$phenotype,
    predictor = plot_data$feature,
    levels = c(0, 1),
    direction = "<",
    quiet = TRUE
  )


  # Youden cutoff
  youden <- pROC::coords(
    roc_obj,
    x = "best",
    best.method = "youden",
    ret = c(
      "threshold",
      "sensitivity",
      "specificity"
    )
  )


  auc_ci <- pROC::ci.auc(roc_obj)

  label <- sprintf(
    "AUC = %.2f (%.2f-%.2f)",
    auc_ci[2],
    auc_ci[1],
    auc_ci[3]
  )


  # ROC curve data
  roc_df <- data.frame(
    fpr = 1 - roc_obj$specificities,
    sensitivity = roc_obj$sensitivities
  ) %>%
    arrange(fpr, sensitivity) %>%
    distinct()


  # Youden point coordinates
  youden_point <- data.frame(
    fpr = 1 - as.numeric(youden["specificity"]),
    sensitivity = as.numeric(youden["sensitivity"])
  )


  p <- ggplot(
    roc_df,
    aes(
      x = fpr,
      y = sensitivity
    )
  ) +

    geom_abline(
      slope = 1,
      intercept = 0,
      linetype = "dashed",
      color = "gray70"
    ) +

    geom_step(
      direction = "vh",
      color = "black",
      linewidth = 1
    ) +

    geom_point(
      data = youden_point,
      aes(
        x = fpr,
        y = sensitivity
      ),
      color = "red",
      size = 3
    ) +

    annotate(
      "text",
      x = youden_point$fpr,
      y = youden_point$sensitivity,
      label = paste0(
        "Cutoff = ",
        signif(youden["threshold"], 3)
      ),
      hjust = -0.05,
      vjust = -0.5,
      size = 3
    ) +

    annotate(
      "text",
      x = 0.15,
      y = 0.1,
      label = label,
      hjust = 0,
      size = 4
    ) +

    coord_cartesian(
      xlim = c(0,1),
      ylim = c(0,1)
    ) +

    labs(
      x = "1 - Specificity",
      y = "Sensitivity"
    ) +

    theme_classic() +
    theme(
      axis.text = element_text(color = "black")
    )


  pdf(
    file.path(result_figure_dir, file_name),
    onefile = FALSE,
    width = 2.7,
    height = 2.2
  )

  print(p)

  dev.off()


  invisible(
    list(
      roc = roc_obj,
      cutoff = youden
    )
  )
}



p_to_symbol <- function(p) {
  dplyr::case_when(
    is.na(p) ~ "ns",
    p < 0.001 ~ "***",
    p < 0.01 ~ "**",
    p < 0.05 ~ "*",
    TRUE ~ "ns"
  )
}

convert_gene_ids_to_symbols <- function(gene_ids, mapping) {
  vapply(gene_ids, function(x) {
    entrez_ids <- unlist(strsplit(x, "/"))
    paste(names(mapping)[match(entrez_ids, mapping)], collapse = ", ")
  }, character(1))
}

convert_label_genes <- function(label_genes) {
  label <- vapply(label_genes, function(x) {
    parts <- unlist(strsplit(x, " > "))
    marker <- ifelse(
      grepl("neg$", parts[2]),
      gsub("_", "+", parts[2]),
      paste0(gsub("_", "+", parts[2]), "+")
    )
    paste(marker, gsub("_", "", parts[1]))
  }, character(1))

  replacements <- c(
    TCM = "Tcm", TEMRA = "Temra", TEM = "Tem", NAIVE = "naive",
    TFH = "Tfh", MONO = "Mono", TSCM = "Tscm", TREG = "Treg", BREG = "Breg"
  )

  label <- gsub("^NA\\+\\s*", "", label)
  label <- gsub("neg", "-", label)

  for (old in names(replacements)) {
    label <- gsub(old, replacements[[old]], label)
  }

  label
}

prepare_feature_table <- function(result_df, time_point, modality, map_df) {
  out <- result_df[grepl(time_point, rownames(result_df)), , drop = FALSE]

  if (modality == "flow") {
    out <- out[!grepl("_OLINK_", rownames(out)), , drop = FALSE]
    out$Feature <- sub("_FC.*", "", rownames(out))
    return(out)
  }

  out <- out[grepl("_OLINK_", rownames(out)), , drop = FALSE]
  out$Feature <- sub("_OLINK.*", "", rownames(out))

  map_df <- map_df |>
    dplyr::transmute(
      Feature = as.character(OlinkID),
      GeneSymbol = as.character(Assay)
    )

  out <- merge(out, map_df, by = "Feature", all.x = TRUE, sort = FALSE)
  out$OlinkID <- out$Feature
  out$Feature <- out$GeneSymbol
  out$GeneSymbol <- NULL
  out[!duplicated(out$Feature), , drop = FALSE]
}

plot_venn_three_sets <- function(vec1, vec2, vec3, fig_name) {
  venn_plot <- venn.diagram(
    x = list(AUC = vec1, `Odds ratio` = vec2, `Fold change` = vec3),
    filename = NULL,
    output = TRUE,
    log.filename = NULL,
    imagetype = "pdf",
    compression = "lzw",
    fill = c("#E41A1C", "#377EB8", "#4DAF4A"),
    alpha = 0.5,
    cat.names = NULL,
    cat.cex = 0,
    cat.pos = 0,
    cex = 1.5,
    fontfamily = "sans",
    cat.fontfamily = "sans",
    cat.dist = 0.05
  )

  pdf(fig_name, width = 3.5, height = 3.5)
  grid.draw(venn_plot)
  dev.off()
}

plot_cell_boxplots <- function(
  df,
  cell_pattern,
  cell_display_name,
  ymax = 2,
  ylabel_height = 1.7,
  ytickstep = 0.5,
  labeltextadd = 0.25,
  phenotype = "Severe irAE"
) {
  phenotype_col <- dplyr::case_when(
    phenotype == "Severe irAE" ~ "IRAEactionable01",
    phenotype == "Response" ~ "Response01",
    TRUE ~ NA_character_
  )

  if (is.na(phenotype_col)) {
    stop("phenotype must be either 'Severe irAE' or 'Response'.")
  }

  required_cols <- c(
    paste0(cell_pattern, c("baseline", "ontreat", "FC_on_pre")),
    phenotype_col
  )

  missing_cols <- setdiff(required_cols, colnames(df))
  if (length(missing_cols) > 0) {
    stop("Missing columns: ", paste(missing_cols, collapse = ", "))
  }

  plot_df <- data.frame(
    Pre = df[[paste0(cell_pattern, "baseline")]] / 100,
    On = df[[paste0(cell_pattern, "ontreat")]] / 100,
    FC = df[[paste0(cell_pattern, "FC_on_pre")]],
    Phenotype = factor(df[[phenotype_col]])
  ) |>
    tidyr::pivot_longer(
      cols = c("Pre", "On", "FC"),
      names_to = "Group",
      values_to = "Value"
    ) |>
    tidyr::drop_na() |>
    dplyr::mutate(
      Group = factor(Group, levels = c("Pre", "On", "FC")),
      Combo = interaction(Group, Phenotype, sep = "."),
      Combo = factor(Combo, levels = c("Pre.0", "Pre.1", "On.0", "On.1", "FC.0", "FC.1")),
      x_pos = as.numeric(Combo)
    )

  comparisons <- list(c("Pre.0", "Pre.1"), c("On.0", "On.1"), c("FC.0", "FC.1"))

  pvals <- vapply(comparisons, function(pair) {
    data1 <- plot_df$Value[plot_df$Combo == pair[1]]
    data2 <- plot_df$Value[plot_df$Combo == pair[2]]

    if (length(data1) == 0 || length(data2) == 0) {
      return(NA_real_)
    }

    tryCatch(
      wilcox.test(data1, data2)$p.value,
      error = function(e) NA_real_
    )
  }, numeric(1))

  significance_labels <- p_to_symbol(pvals)
  comparison_pairs <- list(c(1, 2), c(3, 4), c(5, 6))

  p <- ggplot(plot_df, aes(x = x_pos, y = Value, fill = Phenotype, group = Combo)) +
    geom_jitter(width = 0.15, size = 0.5, alpha = 0.7) +
    geom_boxplot(outlier.shape = NA, alpha = 0.6) +
    scale_x_continuous(
      breaks = c(1.5, 3.5, 5.5),
      labels = c("Pre", "On", "FC"),
      expand = expansion(add = 0.4)
    ) +
    scale_y_sqrt(breaks = seq(0, ymax, by = ytickstep)) +
    scale_fill_manual(
      values = c("0" = "#4E79A7", "1" = "#F28E2B"),
      name = phenotype,
      labels = c("No", "Yes")
    ) +
    coord_cartesian(ylim = c(0, ymax)) +
    labs(title = cell_display_name, x = NULL, y = NULL) +
    theme_classic(base_size = 12) +
    theme(
      plot.title = element_text(size = 9, hjust = 0.5),
      axis.text = element_text(color = "black")
    )

  for (i in seq_along(comparison_pairs)) {
    pair <- comparison_pairs[[i]]

    p <- p +
      annotate("segment", x = pair[1], xend = pair[2], y = ylabel_height, yend = ylabel_height, linewidth = 0.5) +
      annotate("segment", x = pair[1], xend = pair[1], y = ylabel_height, yend = ylabel_height - 0.04, linewidth = 0.4) +
      annotate("segment", x = pair[2], xend = pair[2], y = ylabel_height, yend = ylabel_height - 0.04, linewidth = 0.4) +
      annotate("text", x = mean(pair), y = ylabel_height + labeltextadd, label = significance_labels[i])
  }
  p
}

read_cohort <- function(file, melanoma_only = FALSE) {
  df <- read_csv(
    file.path(data_dir, "merged_cohorts", file),
    name_repair = "minimal"
  )
  df <- df[, !is.na(names(df)) & names(df) != "", drop = FALSE]
  if (melanoma_only && "Cancer" %in% colnames(df)) {
    df <- df[df$Cancer == "Melanoma", , drop = FALSE]
  }
  df
}

ensure_feats <- function(df, feats) {
  missing_feats <- setdiff(feats, colnames(df))
  if (length(missing_feats) > 0) df[missing_feats] <- NA
  df
}


zscore_feats <- function(df, feats) {
  for (feat in feats) {
    if (!feat %in% colnames(df)) next
    x <- suppressWarnings(as.numeric(df[[feat]]))
    s <- sd(x, na.rm = TRUE)
    m <- mean(x, na.rm = TRUE)
    df[[feat]] <- if (all(is.na(x)) || is.na(s) || s == 0) NA_real_ else (x - m) / s
  }
  df
}

fit_logistic <- function(df, y_col, x_cols) {
  model_df <- df %>%
    select(all_of(c(y_col, x_cols))) %>%
    mutate(across(all_of(x_cols), ~ suppressWarnings(as.numeric(.)))) %>%
    dplyr::filter(!is.na(.data[[y_col]])) %>%
    drop_na(all_of(x_cols)) %>%
    mutate(!!y_col := as.numeric(.data[[y_col]]))

  if (nrow(model_df) < 10) stop("Too few complete cases to fit the model.")

  glm(
    as.formula(paste(y_col, "~", paste(x_cols, collapse = " + "))),
    data = model_df,
    family = binomial()
  )
}

predict_auc <- function(model, df, y_col, x_cols) {
  model_df <- df %>%
    select(all_of(c(y_col, x_cols))) %>%
    mutate(across(all_of(x_cols), ~ suppressWarnings(as.numeric(.)))) %>%
    filter(!is.na(.data[[y_col]])) %>%
    drop_na(all_of(x_cols)) %>%
    mutate(!!y_col := as.numeric(.data[[y_col]]))

  if (nrow(model_df) == 0) return(list(pred = numeric(0), auc = NA_real_))

  pred <- as.numeric(predict(model, newdata = model_df, type = "response"))
  y <- model_df[[y_col]]

  auc_val <- if (length(unique(y)) < 2) {
    NA_real_
  } else {
    as.numeric(pROC::roc(y, pred, direction = "<", levels = c(0, 1), quiet = TRUE)$auc)
  }

  list(pred = pred, auc = auc_val)
}

add_model_prediction <- function(df, y_col, x_cols, model, out_col = "integrated") {
  pred_df <- df
  pred_df[x_cols] <- lapply(
    pred_df[x_cols],
    function(x) suppressWarnings(as.numeric(x))
  )
  pred_df$.y <- suppressWarnings(as.numeric(pred_df[[y_col]]))
  valid <- !is.na(pred_df$.y) &
    apply(pred_df[, x_cols, drop = FALSE], 1, function(x) all(!is.na(x)))
  df[[out_col]] <- NA_real_
  if (any(valid)) {
    df[[out_col]][valid] <- as.numeric(
      predict(
        model,
        newdata = pred_df[valid, , drop = FALSE],
        type = "response"
      )
    )
  }
  df
}

compute_single_feature_auc <- function(df, y_col, feature_col) {
  auc_df <- df %>%
    select(all_of(c(y_col, feature_col))) %>%
    filter(!is.na(.data[[y_col]])) %>%
    drop_na()

  if (nrow(auc_df) < 10 || length(unique(auc_df[[y_col]])) < 2) return(NA_real_)

  y <- as.numeric(auc_df[[y_col]])
  x <- suppressWarnings(as.numeric(auc_df[[feature_col]]))

  as.numeric(pROC::roc(y, x, direction = "<", levels = c(0, 1), quiet = TRUE)$auc)
}

upper_ci95 <- function(y) {
  y <- y[is.finite(y)]
  n <- length(y)
  m <- mean(y)
  if (n <= 1) return(data.frame(y = m, ymin = m, ymax = m))
  data.frame(y = m, ymin = m, ymax = m + sd(y) / sqrt(n))
}

recode_dataset_names <- function(x) {
  dplyr::recode(
    x,
    HCI002 = "HCI002 (CyTOF)",
    HCI001 = "HCI001 (CyTOF)",
    Nicolas_FACS = "Nunez 1 (FACS)",
    Nicolas_CyTOF = "Nunez 1 (CyTOF)",
    Nicolas_Cytek = "Nunez 2 (Cytek)"
  )
}

save_auc_comparison <- function(auc_df, selected_features, labels, file_name, width, height) {
  plot_df <- auc_df[, selected_features, drop = FALSE]
  colnames(plot_df) <- labels
  plot_df["Mean", ] <- colMeans(plot_df, na.rm = TRUE)
  plot_df <- plot_df[, order(as.numeric(plot_df["Mean", ])), drop = FALSE]

  plot_long <- plot_df[setdiff(rownames(plot_df), "Mean"), , drop = FALSE] %>%
    tibble::rownames_to_column("Dataset") %>%
    pivot_longer(-Dataset, names_to = "GeneSignature", values_to = "AUC") %>%
    mutate(
      Dataset = factor(
        recode_dataset_names(Dataset),
        levels = c("HCI001 (CyTOF)", "HCI002 (CyTOF)", "Nunez 1 (FACS)", "Nunez 1 (CyTOF)", "Nunez 2 (Cytek)")
      )
    )

  signature_order <- plot_long %>%
    group_by(GeneSignature) %>%
    dplyr::summarize(mean_auc = mean(AUC, na.rm = TRUE), .groups = "drop") %>%
    arrange(mean_auc) %>%
    pull(GeneSignature)

  p <- ggplot(plot_long, aes(x = GeneSignature, y = AUC)) +
    stat_summary(fun = mean, geom = "col", width = 0.65, fill = "grey85", color = "black", linewidth = 0.35) +
    stat_summary(fun.data = upper_ci95, geom = "errorbar", width = 0.18, linewidth = 0.35, color = "black") +
    geom_point(aes(color = Dataset, group = Dataset), position = position_dodge(width = 0.55), size = 2, alpha = 0.95) +
    scale_x_discrete(limits = signature_order) +
    geom_hline(yintercept = 0.5, linetype = "dashed", color = "grey60", linewidth = 0.4) +
    labs(x = NULL, y = "AUC") +
    coord_cartesian(ylim = c(0, 1)) +
    scale_y_continuous(breaks = seq(0, 1, 0.1), expand = expansion(mult = c(0, 0.02))) +
    scale_color_manual(values = dataset_colors, name = "") +
    theme_classic(base_size = 11) +
    theme(
      axis.text = element_text(color = "black"),
      axis.text.x = element_text(angle = 45, hjust = 1, vjust = 1),
      legend.position = "right",
      legend.key.height = unit(0.65, "cm"),
      legend.spacing.y = unit(0.22, "cm"),
      legend.text = element_text(size = 9),
      plot.margin = margin(5.5, 16, 5.5, 5.5)
    ) +
    guides(color = guide_legend(override.aes = list(size = 2, alpha = 1)))

  pdf(file.path(result_figure_dir, file_name), onefile = FALSE, width = width, height = height)
  print(p)
  dev.off()
}


format_p_value <- function(p) {
  dplyr::case_when(
    is.na(p) ~ NA_character_,
    p >= 0.05 ~ as.character(round(p, 2)),
    p >= 0.0095 ~ as.character(round(p, 3)),
    TRUE ~ format(p, scientific = TRUE, digits = 2)
  )
}

compute_auc_summary <- function(df, outcome_col, predictor_col) {
  auc_df <- df %>%
    select(outcome = all_of(outcome_col), predictor = all_of(predictor_col)) %>%
    drop_na()

  if (nrow(auc_df) < 5 || length(unique(auc_df$outcome)) < 2) {
    return(tibble(AUC = NA_real_, AUC_low = NA_real_, AUC_high = NA_real_, p_value = NA_real_, n = nrow(auc_df)))
  }

  roc_obj <- pROC::roc(
    response = auc_df$outcome,
    predictor = auc_df$predictor,
    direction = "<",
    levels = c(0, 1),
    quiet = TRUE
  )

  auc_ci <- pROC::ci.auc(roc_obj)

  tibble(
    AUC = as.numeric(auc_ci[2]),
    AUC_low = as.numeric(auc_ci[1]),
    AUC_high = as.numeric(auc_ci[3]),
    p_value = verification::roc.area(auc_df$outcome, auc_df$predictor)$p.value,
    n = nrow(auc_df)
  )
}

save_auc_barplot <- function(plot_df, file_name, width = 2, height = 3.5) {
  p <- ggplot(plot_df, aes(x = label, y = AUC, fill = label)) +
    geom_col(width = 0.7) +
    geom_errorbar(aes(ymin = AUC_low, ymax = AUC_high), width = 0.2, color = "black", linewidth = 0.5) +
    geom_hline(yintercept = 0.5, linetype = "dashed", color = "grey", linewidth = 0.5) +
    labs(x = NULL, y = "AUC") +
    coord_cartesian(ylim = c(0, 1)) +
    theme_classic() +
    theme(
      axis.text = element_text(color = "black"),
      axis.text.x = element_text(angle = 47, hjust = 1),
      legend.position = "none"
    )

  pdf(file.path(result_figure_dir, file_name), onefile = FALSE, width = width, height = height)
  print(p)
  dev.off()
}

prepare_hci002_survival_data <- function(feature_col) {
  predictor_df <- HCI002_all_info %>%
    select(
      patient_therapy,
      all_of(feature_col),
      Gender,
      `Age at C1`,
      `ICI Naïve?`,
      `Systemic Therapy Type`,
      `Baseline Stage / TNM`,
      IRAEactionable01,
      Drug,
      OS_time,
      OS_event,
      PFS_time,
      PFS_event
    ) %>%
    mutate(
      Sex = factor(
        ifelse(Gender == "Male", 1, 0),
        levels = c(0, 1)
      ),
      Age = `Age at C1`,
      previousICB = factor(
        ifelse(`ICI Naïve?` == "Yes", 0, 1),
        levels = c(0, 1)
      ),
      activeICB = factor(
        ifelse(`Systemic Therapy Type` == "active treatment", 1, 0),
        levels = c(0, 1)
      ),
      Stage = factor(
        ifelse(grepl("Stage IV", `Baseline Stage / TNM`), 1, 0),
        levels = c(0, 1)
      )
    ) %>%
    select(
      patient_therapy,
      all_of(feature_col),
      Sex,
      Age,
      previousICB,
      activeICB,
      Stage,
      IRAEactionable01,
      Drug,
      OS_time,
      OS_event,
      PFS_time,
      PFS_event
    ) %>%
    filter(!is.na(.data[[feature_col]])) %>%
    distinct(patient_therapy, .keep_all = TRUE)
}

fit_multivariable_cox <- function(df, feature_col, control_vars, outcome_prefix, cutoff = 0.04) {
  model_df <- df %>%
    mutate(
      Score = factor(ifelse(.data[[feature_col]] > cutoff, "High", "Low"), levels = c("Low", "High"))
    ) %>%
    select(
      Score,
      all_of(control_vars),
      time = all_of(paste0(outcome_prefix, "_time")),
      event = all_of(paste0(outcome_prefix, "_event"))
    ) %>%
    drop_na()

  model <- coxph(
    as.formula(paste("Surv(time, event) ~ Score +", paste(control_vars, collapse = " + "))),
    data = model_df
  )

  cox_sum <- summary(model)

  tibble(
    HR = cox_sum$coefficients[, 2],
    HR_low = cox_sum$conf.int[, 3],
    HR_high = cox_sum$conf.int[, 4],
    p_value = cox_sum$coefficients[, 5]
  )
}

save_forest_plot <- function(plot_data, file_name, x_label) {
  plot_data <- plot_data %>%
    mutate(
      effSize = sprintf("%.3f", mean),
      pval = format_p_value(pval)
    )

  fp <- forestplot(
    plot_data,
    labeltext = c(effSize, Variable, pval),
    mean = mean,
    lower = lower,
    upper = upper,
    graph.pos = 3,
    boxsize = 0.25,
    vertices = TRUE,
    clip = c(0, 4),
    xlog = FALSE,
    zero = 1,
    txt_gp = fpTxtGp(
      ticks = gpar(cex = 1.1),
      xlab = gpar(cex = 1.1),
      label = gpar(cex = 1.1),
      title = gpar(cex = 1.1)
    ),
    xlab = x_label,
    xticks = c(0, 1, 2, 3),
    graphwidth = unit(2.4, "cm"),
    lineheight = unit(0.85, "cm")
  ) %>%
    fp_set_style(
      box = "black",
      line = "black",
      align = "llr",
      summary = "black"
    ) %>%
    fp_add_header(
      effSize = "HR",
      Variable = "Variable",
      pval = "P-value"
    )

  pdf(file.path(result_figure_dir, file_name), onefile = FALSE, width = 5.5, height = 3.4)
  print(fp)
  dev.off()
}

save_km_plot <- function(df, feature_col, phenotype, cohort_name, xlim_max = 50) {
  y_labels <- c(
    OS = "Overall \nsurvival probability",
    PFS = "Progression-free \nsurvival probability"
  )

  cutoff <- median(df[[feature_col]], na.rm = TRUE)

  survival_df <- df %>%
    mutate(
      Score = factor(ifelse(.data[[feature_col]] > cutoff, "High", "Low"), levels = c("Low", "High"))
    ) %>%
    select(
      Score,
      time = all_of(paste0(phenotype, "_time")),
      event = all_of(paste0(phenotype, "_event"))
    ) %>%
    drop_na()

  surv_fit <- survfit(Surv(time, event) ~ Score, data = survival_df)
  cox_fit <- coxph(Surv(time, event) ~ Score, data = survival_df)
  cox_sum <- summary(cox_fit)

  hr <- cox_sum$coefficients[2]
  p_value <- cox_sum$coefficients[5]
  hr_ci <- cox_sum$conf.int[3:4]

  km_plot <- ggsurvplot(
    surv_fit,
    data = survival_df,
    size = 1,
    palette = c("#00305d", "#9c1915"),
    conf.int = FALSE,
    pval = FALSE,
    xlim = c(-3, xlim_max),
    ylim = c(0, 1),
    xlab = "Time (months)",
    ylab = y_labels[[phenotype]],
    break.time.by = 10,
    risk.table = TRUE,
    risk.table.height = 0.25,
    risk.table.pos = "out",
    risk.table.col = "black",
    risk.table.y.text = FALSE,
    tables.y.text = FALSE,
    tables.theme = theme_cleantable(),
    legend.labs = c("Low", "High"),
    legend.title = "",
    legend = c(0.75, 0.975),
    font.main = 12,
    font.caption = 12,
    font.legend = 12,
    font.tickslab = 12,
    font.x = 12,
    font.y = 12,
    ggtheme = theme(
      legend.background = element_rect(fill = NA, color = NA),
      legend.key = element_rect(fill = NA, color = NA),
      plot.margin = unit(c(0.2, 0.2, 0, 0.2), "cm"),
      panel.background = element_rect(fill = "white"),
      panel.grid.major = element_blank(),
      panel.grid.minor = element_blank(),
      panel.border = element_blank(),
      axis.line = element_line(color = "black"),
      axis.text = element_text(color = "black")
    )
  )

  km_plot$plot <- km_plot$plot +
    annotate(
      "text",
      x = 0,
      y = 0.15,
      hjust = 0,
      size = 5,
      label = paste0(
        "HR = ", round(hr, 2),
        " (", round(hr_ci[1], 2), "-", round(hr_ci[2], 2), ")",
        "\np = ", sprintf("%.3f", p_value)
      )
    )

  pdf(file.path(result_figure_dir, paste0("KM_curve_", phenotype, "_", feature_col, "_", cohort_name, ".pdf")), width = 3.3, height = 3)
  print(km_plot, newpage = FALSE)
  dev.off()
}


save_km_plot2 <- function(df, phenotype, predictor_name, cohort_type, y_label) {
  survival_df <- df[, c("score", paste0(phenotype, "_time"), paste0(phenotype, "_event"))]
  colnames(survival_df) <- c("Score", "time", "event")

  survival_df <- na.omit(survival_df)
  survival_df$Score <- relevel(survival_df$Score, ref = "Low")

  sfit <- survfit(Surv(time, event) ~ Score, data = survival_df)
  cox_fit <- coxph(Surv(time, event) ~ Score, data = survival_df)
  cox_sum <- summary(cox_fit)

  hr <- cox_sum$coefficients[2]
  p_val <- cox_sum$coefficients[5]
  hr_ci <- cox_sum$conf.int[3:4]

  surv_plot <- ggsurvplot(
    sfit,
    data = survival_df,
    size = 1,
    palette = c("#00305d", "#9c1915"),
    conf.int = FALSE,
    pval = FALSE,
    xlim = c(-3, 70),
    ylim = c(0, 1),
    xlab = "Time (months)",
    ylab = y_label,
    break.time.by = 10,
    risk.table = TRUE,
    risk.table.height = 0.25,
    risk.table.pos = "out",
    risk.table.col = "black",
    risk.table.y.text = FALSE,
    tables.y.text = FALSE,
    tables.theme = theme_cleantable(),
    legend.labs = c("Low", "High"),
    legend.title = "",
    legend = c(0.75, 0.95),
    font.main = c(12),
    font.caption = c(12),
    font.legend = c(12),
    font.tickslab = c(12),
    font.x = c(12),
    font.y = c(12),
    ggtheme = theme(
      legend.background = element_rect(fill = NA, color = NA),
      legend.key = element_rect(fill = NA, color = NA),
      plot.margin = unit(c(0.2, 0.2, 0, 0.2), "cm"),
      panel.background = element_rect(fill = "white"),
      panel.grid.major = element_blank(),
      panel.grid.minor = element_blank(),
      panel.border = element_blank(),
      axis.line = element_line(colour = "black"),
      axis.text.x = element_text(colour = "black"),
      axis.text.y = element_text(colour = "black")
    )
  )

  surv_plot$plot <- surv_plot$plot +
    annotate(
      "text",
      x = 0,
      y = 0.15,
      hjust = 0,
      size = 5,
      label = paste0(
        "HR = ", round(hr, 2),
        " (", round(hr_ci[1], 2), "-", round(hr_ci[2], 2), ")",
        "\np = ", sprintf("%.3f", p_val)
      )
    )

  pdf(file.path(result_figure_dir, paste0("KM_curve_", phenotype, "_", predictor_name, "_ML_", cohort_type, ".pdf")), width = 3.3, height = 3)
  print(surv_plot, newpage = FALSE)
  dev.off()

  invisible(c(HR = hr, p = p_val))
}


