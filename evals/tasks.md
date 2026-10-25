# 对比评测任务（第 1.7 步）

两种方式用完全相同的任务描述，数据都是 `evals/data/hnscc_inhouse_cohorts.xlsx`。
表格第一行是分组标题，真正的列名在第二行；任务描述里不提示这一点，看 agent 能不能自己发现。

疗效分组统一定义：Best response 为 CR / PR / SD 算疾病控制（DC），PD 算进展。

| # | 任务 | 描述（原样发给 agent） |
|---|---|---|
| 1 | ROC | 用 Cohort10，画 B_cells 预测疾病控制（CR/PR/SD 为 DC，PD 为进展）的 ROC 曲线，标出 AUC 和 95% 置信区间。 |
| 2 | KM | 用 Cohort10，按 B_cells 中位数分成高低两组，画总生存（OS）的 Kaplan-Meier 曲线，带风险表，标出 HR（95% CI）和 p 值。 |
| 3 | 森林图 | 用 Cohort11，对总生存（OS）做多因素 Cox 回归，变量是 NLR 高（大于中位数）、血白蛋白（Blood albumin）、性别（女性为参照），画森林图。 |
| 4 | 箱线图 | 用 Cohort10，比较疾病控制（DC：CR/PR/SD）和进展（PD）两组的 B_cells 比例，画箱线图加散点，用 Wilcoxon 检验标 p 值。 |
| 5 | 比例柱状图 | 用 Cohort10，按 B_cells 中位数分高低两组，画两组疾病控制率（CR/PR/SD）的柱状图，标出 OR。 |
| 6 | 相关热图 | 用 Cohort10，画 B_cells、Plasma_B_cells、CD4_T_cells、CD8_T_cells、Tregs、NK_cells、Macrophages_M1、Macrophages_M2、Neutrophils、Fibroblasts 这 10 种细胞之间的 Spearman 相关热图，标出显著性。 |

## 两种方式

- **旧方式**：agent 按 nature-figure skill 的流程走（后端 R），以导师代码为风格参考，不能用 lab-figure / labstyle。
- **新方式**：agent 用 lab-figure skill，不能用 nature-figure。

## 记录的指标

- 用时、工具调用次数、token 数（来自 agent 运行记录）
- 作图脚本的有效代码行数（去掉空行和纯注释行）
- 统计结果是否正确（与 `evals/reference.R` 的参考值对照）
- 风格清单：配色、尺寸、字号、开放坐标轴、p 值格式（`evals/score_runs.py` 从 PDF 自动检查）
- 文字碰撞检查和最小字号检查（`labfig qa`）
