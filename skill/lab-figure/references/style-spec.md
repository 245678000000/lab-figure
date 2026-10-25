# 实验室作图风格规范

来源：rootchang 的 5 个公开仓库（HNSCC_Bcells、Neutrophil_EGR1、melanoma_irAE、LORIS、PENCIL_reusability_report）。
括号里的数字是该写法在这些代码里出现的次数。

所有数值都在 `labstyle` 包里定义（`labstyle/R/style.R`）。作图脚本里不要再写死颜色、字号或尺寸。

## 坐标轴与背景

- **开放坐标轴**：无网格（`panel.grid = element_blank`，179）、无边框（`panel.border = element_blank`，81），
  黑色轴线（`axis.line` 黑色，40）、黑色刻度和刻度文字。
  文件开头常写 `theme_set(theme_bw(base_size = 12))`（28），但随后几乎每张图都去掉网格和边框，
  所以实际成图是开放坐标轴。`theme_lab()` 默认就是这个样子（2026-10-24 看过风格样张后确认）；
  `theme_lab(boxed = TRUE)` 或 `options(labstyle.boxed = TRUE)` 保留边框，作为备选。
- **基础字号**：12 pt（`base_size = 12`）。注释文字（AUC、HR、p 值）用 ggplot 的 `size = 4`（约 11 pt）。
  原 `save_km_plot` 的 HR 文字是 `size = 5`，在 3.3 英寸宽的图里会压住曲线，这里统一改成 4，
  并自动放在曲线最少经过的角落。
- **图例**：两组对比时去掉图例（`legend.position = "none"`，118），用 x 轴标签区分组别。
  KM 曲线的图例放在图内右上角。
- **x 轴标签**：组名较长时旋转 45°（27）。

## 配色

| 名称 | 用途 | 颜色 |
|---|---|---|
| `binary` | 两组对比（Low/High、无/有、阴性/阳性） | `#00305d` 深蓝、`#9c1915` 暗红（22） |
| `categorical` | 3–10 个类别 | `#1c4f27` `#81144e` `#79831e` `#00305d` `#C0C0C0` `#9c1915` `black` `#404040` `#808080` `#D3D3D3` |
| `dataset` | 多队列、多数据集 | `#1c4f27` `#81144e` `#79831e` `#00305d` `#9c1915` `black` `grey` `#f58231` `#e6194b` `#3cb44b` `#42d4f4` |
| `clusters` | 单细胞聚类（类别很多时） | `melanoma_irAE/code/utils.R` 里 `color_clusters` 的全部 100 色 |
| `diverging` | 相关性热图 | `#00305d` → 白 → `#9c1915` |
| `accent` | 强调点（如 Youden 切点） | `red` |

两组顺序固定为"参照组在前"：Low → 深蓝，High → 暗红。

## 尺寸预设（英寸，宽 × 高）

| 预设 | 尺寸 | 来源 |
|---|---|---|
| `single` | 2.3 × 2.7 | 最常见的单面板（width 2.3 出现 25 次，height 2.7 出现 26 次） |
| `narrow` | 1.5 × 3.3 | 两组箱线图（`save_feature_boxplot`） |
| `bar2` | 1.43 × 2.57 | 两组比例柱状图（`save_irAE_barplot`：1.5 × 2.7 × 0.95） |
| `roc` | 2.7 × 2.2 | ROC（`save_roc_plot`） |
| `km` | 3.3 × 3.0 | KM 曲线 + 风险表（`save_km_plot`） |
| `forest` | 5.5 × 3.4 | 森林图（`save_forest_plot`） |
| `violin` | 3.0 × 4.0 | 小提琴图（Neutrophil_EGR1 Figure2） |
| `auc_bar` | 2.0 × 3.5 | AUC 柱状图（`save_auc_barplot`） |
| `pie` | 3.6 × 2.4 | 饼图（`plot_pie`） |
| `wide` | 4.6 × 2.7 | 两个 single 并排 |

每个模板都自带默认预设，`save_fig()` 不填 `size` 时会自动使用。

## 统计标注

- p 值格式（`format_p_value`）：p ≥ 0.05 保留 2 位小数；0.0095 ≤ p < 0.05 保留 3 位小数；更小的用科学计数法，2 位有效数字。
- 星号（`p_to_symbol`）：`***` < 0.001，`**` < 0.01，`*` < 0.05，否则 `ns`。
- 两组比较默认用 Wilcoxon 秩和检验（R 默认：小样本且无并列值时为精确检验），用括线标注 `p = …`。
- ROC 标注三行：`AUC = 0.xx` / `95% CI 下限-上限` / `n: 阳性类 n, 阴性类 n`，置信区间用 DeLong 法（`pROC::ci.auc`）。
- KM 标注 `HR = x` / `(下限-上限)` / `p = …`，来自以第一组为参照的单因素 Cox 模型。
- 比例柱状图：OR 算法同原代码，另加 Wald 95% CI 和 Fisher 精确检验 p。
- 相关热图：星号用 Benjamini-Hochberg 校正后的 p（与 HNSCC_Bcells 的热图一致），每对变量只算一次。

## 相对导师原代码的增补（2026-10-25）

对比评测里旧方式自己加上、确实更好的细节，统一加进了模板，都可以关掉：

| 增补 | 模板 | 关闭参数 |
|---|---|---|
| 各组样本量 n | ROC 标注、KM 图例、箱线图 / 小提琴图 x 轴、比例柱状图柱顶 | `show_n = FALSE` / `show_counts = FALSE` |
| 森林图印出 95% CI 文字 | `lab_forest` | `ci_text = FALSE` |
| OR 的 95% CI 和 Fisher p | `lab_rate_bar` | `show_ci = FALSE`、`show_p = FALSE` |
| BH 校正、只画下三角、星号说明 | `lab_cor_heatmap` | `p_adjust = "none"`、`triangle = "full"`、`note = FALSE` |

为放下这些内容，尺寸也相应调整：箱线图显示 n 时每组 0.6 英寸（两组约 1.95 英寸），森林图带 CI 文字时宽 6.5 英寸。

## 导出

- PDF：`pdf(useDingbats = FALSE)`，字体为 Helvetica，导出后文字仍可编辑。
- PNG：300 dpi，用 ragg 输出，供预览和放入 PPT。
- 可选：用 `data =` 参数同时导出源数据 CSV（Nature 系期刊要求提供源数据）。
- 最终投稿前跑一遍检查：文字碰撞检查和最小字号检查（≥ 5 pt）。
