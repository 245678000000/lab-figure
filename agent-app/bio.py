"""Bioinformatics single-chart recipes; original implementation over labstyle/ggplot2."""
import json

import numpy as np
import pandas as pd


def entry(name, family, fields, numeric=(), hint="", optional=None):
    return {"name": name, "family": family, "fields": fields, "numeric": list(numeric), "hint": hint, "optional": optional or {}}


BIO_CATALOG = {
    "volcano": entry("火山图", "差异表达", {"label": "基因名", "effect": "log2 fold change", "padj": "校正后 P 值"}, ["effect", "padj"], "读取已完成差异分析的结果；不从表达矩阵计算差异检验。全部基因保留。"),
    "ma": entry("MA 图", "差异表达", {"label": "基因名", "mean": "平均表达量", "effect": "log2 fold change", "padj": "校正后 P 值"}, ["mean", "effect", "padj"], "读取已计算的平均表达、log2FC 与校正 P 值。"),
    "expression_heatmap": entry("表达矩阵热图", "差异表达", {"label": "行标识（如基因）", "predictors": "表达矩阵列（多选）"}, ["predictors"], "宽表：每行一个基因，所选数值列为样本。缩放方式需明确选择；缺失格保留。"),
    "embedding": entry("UMAP / t-SNE 分群图", "单细胞", {"x": "已有嵌入坐标 1", "y": "已有嵌入坐标 2", "group": "细胞类型 / 分群"}, ["x", "y"], "使用真实已有坐标；不会将任意两列数值重新命名为计算得到的 UMAP。"),
    "feature": entry("FeaturePlot", "单细胞", {"x": "已有嵌入坐标 1", "y": "已有嵌入坐标 2", "value": "基因表达 / 评分"}, ["x", "y", "value"], "每行一个细胞或点，使用已有嵌入坐标与表达值。"),
    "marker_dot": entry("Marker DotPlot", "单细胞", {"label": "基因", "group": "细胞类型", "value": "平均表达", "pct": "表达细胞比例（0–100）"}, ["value", "pct"], "长表：每行一个基因×细胞群；比例必须为 0–100%。不自动推断比例单位。"),
    "composition": entry("细胞比例堆叠图", "单细胞", {"sample": "样本 / 条件", "group": "细胞类型"}, [], "默认每行一个细胞；已有汇总计数时请指定计数列。只计算组成，不做细胞级显著性推断。", {"count": "汇总计数（可选）"}),
    "enrichment_dot": entry("富集气泡图", "功能富集", {"label": "通路 / 条目", "ratio": "GeneRatio（数值或 a/b）", "count": "基因数", "padj": "校正后 P 值"}, ["count", "padj"], "读取已有 GO/KEGG 富集结果，不在线计算富集。所有条目默认保留。"),
    "enrichment_bar": entry("富集柱状图", "功能富集", {"label": "通路 / 条目", "padj": "校正后 P 值"}, ["padj"], "读取已有富集结果，横轴为 −log10(校正 P 值)。"),
    "gsea": entry("GSEA 富集曲线", "功能富集", {"rank": "基因排序位置", "value": "已有 running ES"}, ["rank", "value"], "读取单个基因集的已有 running ES 曲线；不会据此伪造 NES 或显著性。"),
    "paired": entry("配对连线图", "配对与相关", {"pair": "配对 ID", "group": "两个条件", "value": "测量值"}, ["value"], "每对恰好两个条件、每条件一条记录；拒绝重复或不完整配对。"),
    "paired_delta": entry("配对差值图", "配对与相关", {"pair": "配对 ID", "group": "两个条件", "value": "测量值"}, ["value"], "须明确参考条件；差值为另一条件 − 参考条件，附配对 Wilcoxon 检验。"),
    "scatter": entry("相关散点图", "配对与相关", {"x": "X 数值", "y": "Y 数值"}, ["x", "y"], "SCC、PCC 分别计算并保存。回归线为线性趋势，不代表因果关系。", {"group": "着色分组（可选）"}),
    "pca": entry("PCA", "样本检查", {"label": "样本标识", "predictors": "分析特征（多选）"}, ["predictors"], "每行一个样本；从所选数值重新计算 PCA。是否标准化须明确选择。", {"group": "着色分组（可选）"}),
    "sample_distance": entry("样本距离热图", "样本检查", {"label": "样本标识", "predictors": "分析特征（多选）"}, ["predictors"], "每行一个样本，计算所选特征的欧氏距离；相似度不能用于确定混样或责任来源。"),
    "missingness": entry("缺失值分布", "样本检查", {"predictors": "检查列（多选）"}, [], "展示原表所选列缺失比例；不删除缺失行，不进行插补。"),
    "upset": entry("UpSet 集合交集图", "集合与互作", {"predictors": "集合成员列（0/1，多选）"}, ["predictors"], "每行一个元素，每列为一个集合的 0/1 成员标记；支持 2–6 个集合，全部非空交集保留。"),
    "lr_dot": entry("配体–受体气泡矩阵", "集合与互作", {"label": "配体–受体对", "group": "发送→接收群", "value": "已有通信分数", "padj": "校正后 P 值"}, ["value", "padj"], "读取已有通信分析结果；不从表达相似性推断细胞通信。"),
    "network": entry("互作网络图", "集合与互作", {"source": "起点", "target": "终点", "weight": "非负互作权重"}, ["weight"], "读取已有边表，采用固定环形布局；节点大小为连接次数，不自动推断互作。"),
    "histogram": entry("数值分布直方图", "样本检查", {"value": "数值列"}, ["value"], "保留全部有效观测，展示频数与基本描述统计。"),
    "custom": entry("自定义单图", "自定义", {"x": "X 列", "y": "Y 列"}, [], "选择几何图层与列映射，生成可审查 R 脚本。", {"group": "分组（可选）"}),
    "free": entry("AI 自由作图", "自定义", {}, [], "没有合适模板时用：在下方对话里描述想要的图（可以贴截图），AI 按实验室风格写 R 代码并运行。需要先连接模型。"),
    "waterfall": entry("瀑布图", "临床与肿瘤", {"label": "患者 ID", "value": "最佳变化（%）"}, ["value"], "每行一位患者，按变化从大到小排列；虚线为 RECIST +20% / −30%。", {"group": "着色（如最佳疗效，可选）"}),
    "swimmer": entry("泳道图", "临床与肿瘤", {"label": "患者 ID", "time": "治疗时长"}, ["time"], "每行一位患者，条长为治疗时长；选“仍在治疗”(0/1) 列时在条末画箭头。", {"group": "着色（可选）", "ongoing": "仍在治疗（0/1，可选）"}),
    "oncoprint": entry("OncoPrint 突变图谱", "临床与肿瘤", {"sample": "样本", "label": "基因", "alteration": "突变类型"}, [], "长表：每行一个样本×基因的突变；显示突变样本最多的 20 个基因。同一基因多种突变记为 Multi_hit。"),
    "nomogram": entry("列线图", "预测模型", {"outcome": "二分类结局", "predictors": "模型变量（多选）"}, [], "Logistic 回归：每个变量换算成分数，总分对应预测概率。统计表给出 OR 与 95% CI。"),
    "calibration": entry("校准曲线", "预测模型", {"outcome": "二分类结局", "predictor": "预测概率（0–1）"}, ["predictor"], "按预测概率十分位分组，比较平均预测概率与实际发生率；报告 Brier、校准斜率和 Hosmer–Lemeshow 检验。"),
    "dca": entry("DCA 决策曲线", "预测模型", {"outcome": "二分类结局", "predictors": "预测概率列（0–1，可多选）"}, ["predictors"], "各阈值概率下的净获益，与“全部治疗”“全不治疗”比较。"),
    "time_roc": entry("时间依赖 ROC", "预测模型", {"time": "生存时间", "event": "事件状态", "predictor": "预测指标"}, ["time", "predictor"], "在各时间点比较已发生事件者和仍无事件者（删失按 IPCW 加权，与 timeROC 一致）。时间点在参数里填写。"),
    "ridge": entry("山脊图", "分布与流向", {"group": "分组", "value": "数值指标"}, ["value"], "每组一条密度曲线，上下排列。"),
    "density": entry("密度图", "分布与流向", {"value": "数值指标"}, ["value"], "密度曲线；选择分组时每组一条，叠加显示。", {"group": "分组（可选）"}),
    "sankey": entry("桑基图", "分布与流向", {"predictors": "各阶段列（多选 2–4 列，按表中列的先后为阶段顺序）"}, [], "每行一个对象（或用计数列汇总），展示各阶段类别之间的流向。", {"count": "计数（可选）"}),
    "venn": entry("韦恩图", "分布与流向", {"predictors": "集合成员列（0/1，多选 2–4 列）"}, ["predictors"], "每行一个元素，每列是一个集合的 0/1 成员标记；超过 4 个集合请用 UpSet。"),
    "manhattan": entry("曼哈顿图", "GWAS", {"chr": "染色体", "pos": "位置（bp）", "pvalue": "P 值"}, ["pos", "pvalue"], "读取已完成的关联分析结果。全基因组显著线 5e-8、提示线 1e-5；可选 SNP 名称列标注最显著位点。", {"label": "SNP 名称（可选）"}),
    "qq": entry("QQ 图", "GWAS", {"pvalue": "P 值"}, ["pvalue"], "观测与期望 −log10(P)，含 95% 置信带和基因组膨胀系数 λ。"),
}


def validate_bio(d, spec, report):
    chart, c = spec.chart, spec.columns
    if chart in ("volcano", "ma", "lr_dot", "enrichment_dot", "enrichment_bar"):
        p = d[c["padj"]]
        if ((p < 0) | (p > 1)).any():
            raise ValueError("校正 P 值必须在 0–1 范围内")
        if (p == 0).any():
            report["notes"].append(f"{int((p == 0).sum())} 个零 P 值在 −log10 显示时使用 1e-300 下限，原始值保留。")
        report["notes"].append("读取用户提供的预计算结果；未重新执行差异、富集或细胞通信检验。")
    if chart == "enrichment_dot":
        def ratio(value):
            try:
                a = str(value).split("/")
                return float(a[0]) / float(a[1]) if len(a) == 2 else float(value)
            except (ValueError, ZeroDivisionError):
                raise ValueError("GeneRatio 需为 0–1 数值或 a/b 分数") from None
        ratios = d[c["ratio"]].map(ratio)
        if not np.isfinite(ratios).all() or not ratios.between(0, 1).all():
            raise ValueError("GeneRatio 必须在 0–1 范围内")
    if chart in ("enrichment_dot", "composition") and c.get("count"):
        if (d[c["count"]] < 0).any():
            raise ValueError("计数不能为负数")
        if (d[c["count"]] % 1 != 0).any():
            raise ValueError("基因数 / 细胞数应为整数，请核对输入单位")
        if chart == "composition" and (d.groupby(c["sample"])[c["count"]].sum() <= 0).any():
            raise ValueError("每个样本的汇总计数必须大于零")
    if chart == "marker_dot" and not d[c["pct"]].between(0, 100).all():
        raise ValueError("表达细胞比例必须在 0–100 范围，请先明确比例单位")
    if chart in ("marker_dot", "lr_dot") and d.duplicated([c["label"], c["group"]]).any():
        raise ValueError("气泡矩阵存在重复的行×列组合，请先明确汇总方式")
    if chart in ("expression_heatmap", "pca", "sample_distance"):
        if d[c["label"]].duplicated().any():
            raise ValueError("行标识必须唯一；请明确重复记录的处理方式")
        if len(c["predictors"]) < 2:
            raise ValueError("至少选择两列数值特征")
        if chart == "sample_distance" and len(d) > 100:
            raise ValueError("样本距离热图最多显示 100 个样本，请选择样本表而不是细胞表")
        if chart == "expression_heatmap" and len(d) > 300:
            raise ValueError("单张表达热图最多显示 300 行，请先明确需要展示的基因集合")
        if chart == 'pca':
            report['feature_count'] = len(c['predictors'])
            if min(len(d), len(c['predictors'])) > 1000:
                raise ValueError('精确 PCA 的样本数与特征数中较小一项最多 1,000；请明确选择需要分析的样本或特征')
            if not (d[c['predictors']].var(axis=0) > 0).any():
                raise ValueError('PCA 特征均无样本间方差，无法计算解释方差')
            report['notes'].append(f"精确 PCA 使用 {len(c['predictors']):,} 个特征；未自动挑选高变基因。")
        if spec.scaling != "none":
            variance = d[c["predictors"]].std(axis=1 if spec.scaling == "row_z" else 0)
            if (variance == 0).any() or variance.isna().any():
                raise ValueError("所选缩放方向存在零方差或不足两个有效值的行/列，无法计算 Z-score，请明确处理规则")
    if chart in ("paired", "paired_delta"):
        groups = sorted(d[c["group"]].astype(str).unique())
        if len(groups) != 2 or not spec.reference or spec.reference not in groups:
            raise ValueError("配对图必须有两个条件，并明确选择参考条件")
        if d.duplicated([c["pair"], c["group"]]).any() or not d.groupby(c["pair"])[c["group"]].nunique().eq(2).all():
            raise ValueError("配对数据存在重复或不完整配对；请明确处理规则，不能自动删掉不完整配对")
        report["pairs"] = int(d[c["pair"]].nunique())
        report["notes"].append(f"以 {spec.reference} 为参考；差值为另一条件减参考条件。配对 ID 而非观测行是检验单位。")
    if chart == "gsea":
        if d[c["rank"]].duplicated().any():
            raise ValueError("GSEA 排序位置必须唯一；一次只读取一条基因集曲线")
        report["notes"].append("running ES 来自输入数据；不计算 NES、P 值或 FDR。")
    if chart in ("embedding", "feature"):
        report["notes"].append(f"展示输入的 {spec.embedding_method} 坐标，未重新计算降维。")
    if chart == "upset":
        columns = c["predictors"]
        if not 2 <= len(columns) <= 6:
            raise ValueError("UpSet 请选择 2–6 个集合")
        if not d[columns].isin([0, 1]).all().all():
            raise ValueError("UpSet 成员标记必须为 0/1；缺失成员关系不能当作 0")
        none = int(d[columns].eq(0).all(axis=1).sum())
        report["notes"].append(f"全部非空交集保留；另有 {none} 个元素不属于任何所选集合，不显示在非空交集柱中，原始记录保留。")
    if chart == "network":
        if (d[c["weight"]] < 0).any():
            raise ValueError("网络权重必须非负")
        if len(set(d[c["source"]]) | set(d[c["target"]])) > 60:
            raise ValueError("单图最多显示 60 个节点；请先明确需要展示的子网络")
    if chart == "custom" and spec.geometry in ("point", "line", "box", "violin"):
        for role in ("y",) if spec.geometry in ("box", "violin") else ("x", "y"):
            if not pd.api.types.is_numeric_dtype(d[c[role]]):
                raise ValueError(f"{role.upper()} 轴需为数值列")
    if chart == "custom" and spec.geometry == "bar" and not pd.api.types.is_numeric_dtype(d[c["y"]]):
        raise ValueError("柱高需使用数值列；此入口绘制已有数值，不自动作显著性检验")
    if chart == "custom" and spec.geometry == "bar":
        keys = [c["x"]] + ([c["group"]] if c.get("group") else [])
        if d.duplicated(keys).any():
            raise ValueError("每组每个 X 类别需有唯一的已有柱高；请先明确重复记录的汇总方法")
    if chart == "waterfall" and d[c["label"]].duplicated().any():
        raise ValueError("患者 ID 有重复；瀑布图每位患者一行")
    if chart == "swimmer":
        if (d[c["time"]] < 0).any():
            raise ValueError("治疗时长不能为负数")
        if c.get("ongoing") and not d[c["ongoing"]].dropna().isin([0, 1, True, False]).all():
            raise ValueError("“仍在治疗”列须为 0/1 或 TRUE/FALSE")
    if chart in ("calibration", "dca"):
        for col in [c["predictor"]] if chart == "calibration" else c["predictors"]:
            if not d[col].between(0, 1).all():
                raise ValueError(f"{col} 应为 0–1 的预测概率")
    if chart == "nomogram" and len(c["predictors"]) > 10:
        raise ValueError("列线图最多选择 10 个变量")
    if chart == "time_roc":
        if (d[c["time"]] < 0).any():
            raise ValueError("生存时间不能为负数")
        try:
            points = [float(v) for v in spec.time_points.replace("，", ",").split(",") if v.strip()]
        except ValueError:
            raise ValueError("时间点请写成数字，用逗号分隔，例如 12,36,60") from None
        if not 1 <= len(points) <= 5 or min(points) <= 0 or max(points) >= d[c["time"]].max():
            raise ValueError("请填写 1–5 个时间点，均大于 0 且小于最长随访时间")
    if chart == "ridge" and not 2 <= d[c["group"]].nunique() <= 20:
        raise ValueError("山脊图需要 2–20 个分组")
    if chart == "sankey":
        if not 2 <= len(c["predictors"]) <= 4:
            raise ValueError("桑基图请选择 2–4 个阶段列")
        if any(d[col].nunique() > 15 for col in c["predictors"]):
            raise ValueError("每个阶段最多 15 个类别")
    if chart == "venn":
        if not 2 <= len(c["predictors"]) <= 4:
            raise ValueError("韦恩图请选择 2–4 个集合；更多集合请用 UpSet")
        if not d[c["predictors"]].isin([0, 1]).all().all():
            raise ValueError("韦恩图成员标记必须为 0/1")
    if chart in ("manhattan", "qq") and not d[c["pvalue"]].between(0, 1, inclusive="right").all():
        raise ValueError("P 值必须在 (0, 1] 范围内")
    return d, report


def demo_recipe(chart):
    """Synthetic examples with explicit mappings, never patient-derived placeholders."""
    rng = np.random.default_rng(31)
    if chart in ("volcano", "ma"):
        d = pd.DataFrame({"gene": [f"Gene_{i+1}" for i in range(150)], "log2FC": rng.normal(0, 1.5, 150), "padj": 10 ** -rng.uniform(0, 5, 150), "mean": rng.uniform(1, 1000, 150)})
        return d, {"label": "gene", "effect": "log2FC", "padj": "padj", "mean": "mean"}, {}
    if chart == "expression_heatmap":
        d = pd.DataFrame(rng.normal(5, 1.5, (12, 4)), columns=["sample_A", "sample_B", "sample_C", "sample_D"])
        d.insert(0, "gene", [f"Gene_{i+1}" for i in range(12)])
        return d, {"label": "gene", "predictors": list(d.columns[1:])}, {"scaling": "row_z"}
    if chart in ("embedding", "feature", "scatter"):
        n = 180
        groups = np.repeat(["T cell", "B cell", "Myeloid"], n // 3)
        x = rng.normal(0, 1, n) + np.repeat([-2, 2, 0], n // 3)
        d = pd.DataFrame({"x": x, "y": .4 * x + rng.normal(0, 1, n) + np.repeat([0, 0, 3], n // 3), "group": groups, "value": np.maximum(0, rng.normal(2, 1, n))})
        return d, {"x": "x", "y": "y", "group": "group", "value": "value"}, {"embedding_method": "provided"}
    if chart in ("marker_dot", "lr_dot"):
        d = pd.DataFrame([(f"Gene_{i+1}" if chart == "marker_dot" else f"L{i+1}–R{i+1}", g) for i in range(8) for g in ("T cell", "B cell", "Myeloid")], columns=["gene", "group"])
        d["value"] = rng.uniform(0, 3, len(d)); d["pct"] = rng.uniform(1, 100, len(d)); d["padj"] = 10 ** -rng.uniform(0, 4, len(d))
        return d, {"label": "gene", "group": "group", "value": "value", "pct": "pct", "padj": "padj"}, {}
    if chart == "composition":
        d = pd.DataFrame([(s, g, int(rng.integers(10, 100))) for s in ("Sample_A", "Sample_B", "Sample_C", "Sample_D") for g in ("T cell", "B cell", "Myeloid")], columns=["sample", "group", "count"])
        return d, {"sample": "sample", "group": "group", "count": "count"}, {}
    if chart in ("enrichment_dot", "enrichment_bar"):
        d = pd.DataFrame({"term": [f"Pathway {i+1}" for i in range(10)], "padj": 10 ** -rng.uniform(1, 5, 10), "count": rng.integers(4, 30, 10), "GeneRatio": [f"{i}/100" for i in range(5, 15)]})
        return d, {"label": "term", "padj": "padj", "count": "count", "ratio": "GeneRatio"}, {}
    if chart == "gsea":
        x = np.arange(1, 101)
        d = pd.DataFrame({"rank": x, "running_ES": np.sin(x * np.pi / 100) * .45 - .002 * x})
        return d, {"rank": "rank", "value": "running_ES"}, {}
    if chart in ("paired", "paired_delta"):
        base = rng.normal(5, 1, 12)
        d = pd.DataFrame([(f"Pair_{i+1}", condition, float(base[i] + (rng.normal(.8, .4) if condition == "After" else 0))) for i in range(12) for condition in ("Before", "After")], columns=["pair", "group", "value"])
        return d, {"pair": "pair", "group": "group", "value": "value"}, {"reference": "Before"}
    if chart in ("pca", "sample_distance"):
        d = pd.DataFrame(rng.normal(0, 1, (12, 5)), columns=[f"feature_{i+1}" for i in range(5)])
        d.insert(0, "sample", [f"Sample_{i+1}" for i in range(12)])
        d["group"] = ["A"] * 6 + ["B"] * 6
        return d, {"label": "sample", "predictors": [f"feature_{i+1}" for i in range(5)], "group": "group"}, {"scaling": "column_z", "matrix_orientation": "samples"}
    if chart == "missingness":
        d = pd.DataFrame(rng.normal(0, 1, (30, 4)), columns=[f"feature_{i+1}" for i in range(4)])
        d.iloc[:4, 0] = np.nan; d.iloc[4:13, 2] = np.nan
        return d, {"predictors": list(d.columns)}, {}
    if chart == "upset":
        d = pd.DataFrame(rng.integers(0, 2, (60, 3)), columns=["set_A", "set_B", "set_C"])
        return d, {"predictors": list(d.columns)}, {}
    if chart == "network":
        d = pd.DataFrame({"source": ["A", "A", "B", "C", "D"], "target": ["B", "C", "D", "D", "A"], "weight": [2., 1., 4., 3., 1.]})
        return d, {"source": "source", "target": "target", "weight": "weight"}, {}
    if chart == "histogram":
        return pd.DataFrame({"value": rng.normal(5, 1, 100)}), {"value": "value"}, {}
    if chart in ("waterfall", "swimmer"):
        n = 30
        d = pd.DataFrame({"patient": [f"P{i+1:02d}" for i in range(n)], "best_change": np.round(rng.normal(-12, 32, n), 1),
                          "response": rng.choice(["CR", "PR", "SD", "PD"], n, p=[.1, .25, .35, .3]),
                          "months": np.round(rng.exponential(9, n) + .5, 1), "ongoing": rng.integers(0, 2, n)})
        if chart == "waterfall":
            return d, {"label": "patient", "value": "best_change", "group": "response"}, {}
        return d, {"label": "patient", "time": "months", "group": "response", "ongoing": "ongoing"}, {}
    if chart == "oncoprint":
        genes = ["TP53", "KRAS", "PIK3CA", "CDKN2A", "NOTCH1", "FAT1"]
        rows = [(f"S{s+1:02d}", g, rng.choice(["Missense", "Nonsense", "Frame_shift", "Splice"]))
                for s in range(30) for g in genes if rng.random() < .55 - .07 * genes.index(g)]
        return pd.DataFrame(rows, columns=["sample", "gene", "type"]), {"sample": "sample", "label": "gene", "alteration": "type"}, {}
    if chart in ("nomogram", "calibration", "dca", "time_roc"):
        n = 150
        d = pd.DataFrame({"score": np.round(rng.normal(0, 1, n), 3), "age": np.round(rng.normal(60, 9, n)),
                          "stage": rng.choice(["I-II", "III-IV"], n)})
        lp = -.5 + .9 * d.score + .03 * (d.age - 60) + .6 * (d.stage == "III-IV")
        d["response"] = rng.binomial(1, 1 / (1 + np.exp(-lp)))
        d["model_prob"] = np.round(1 / (1 + np.exp(-lp)), 4)
        d["simple_prob"] = np.round(1 / (1 + np.exp(-(-.4 + .7 * d.score))), 4)
        d["os_months"] = np.round(rng.exponential(30 * np.exp(-.5 * d.score)) + .5, 1)
        d["death"] = rng.binomial(1, .7, n)
        if chart == "nomogram":
            return d, {"outcome": "response", "predictors": ["score", "age", "stage"]}, {"positive": "1"}
        if chart == "calibration":
            return d, {"outcome": "response", "predictor": "model_prob"}, {"positive": "1"}
        if chart == "dca":
            return d, {"outcome": "response", "predictors": ["model_prob", "simple_prob"]}, {"positive": "1"}
        return d, {"time": "os_months", "event": "death", "predictor": "score"}, {"positive": "1", "time_points": "12,24,36"}
    if chart in ("ridge", "density"):
        groups = np.repeat(["T cell", "B cell", "Myeloid", "NK"], 60)
        d = pd.DataFrame({"cell_type": groups, "signature": np.round(rng.normal(0, 1, 240) + np.repeat([0, .8, -.5, 1.4], 60), 3)})
        return d, {"group": "cell_type", "value": "signature"}, {}
    if chart == "sankey":
        n = 80
        first = rng.choice(["SD", "PR", "PD"], n, p=[.45, .3, .25])
        second = np.where(rng.random(n) < .6, first, rng.choice(["CR", "PR", "SD", "PD"], n))
        third = np.where(rng.random(n) < .7, second, rng.choice(["CR", "PR", "SD", "PD"], n))
        return pd.DataFrame({"baseline": first, "week_12": second, "week_24": third}), {"predictors": ["baseline", "week_12", "week_24"]}, {}
    if chart == "venn":
        return pd.DataFrame(rng.integers(0, 2, (120, 3)), columns=["DEG_set_A", "DEG_set_B", "DEG_set_C"]), {"predictors": ["DEG_set_A", "DEG_set_B", "DEG_set_C"]}, {}
    if chart in ("manhattan", "qq"):
        chromosomes = [str(i) for i in range(1, 23)]
        d = pd.DataFrame({"chr": np.repeat(chromosomes, 150), "pos": np.tile(np.arange(1, 151) * 500_000, 22), "p": rng.uniform(0, 1, 3300)})
        d.loc[[400, 401, 2000], "p"] = [2e-9, 4e-8, 6e-11]
        d["snp"] = [f"rs{1000 + i}" for i in range(len(d))]
        return d, ({"chr": "chr", "pos": "pos", "pvalue": "p", "label": "snp"} if chart == "manhattan" else {"pvalue": "p"}), {}
    if chart == "free":
        return pd.DataFrame({"x": np.arange(30), "y": rng.normal(0, 1, 30).cumsum()}), {}, {}
    return pd.DataFrame({"x": np.arange(30), "y": rng.normal(0, 1, 30).cumsum()}), {"x": "x", "y": "y"}, {"geometry": "line"}
