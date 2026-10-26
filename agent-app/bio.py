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
    "custom": entry("自定义单图", "自定义", {"x": "X 列", "y": "Y 列"}, [], "选择几何图层与列映射，生成可审查 R 脚本。不会执行模型提供的任意代码。", {"group": "分组（可选）"}),
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
    return d, report


def compile_bio(spec, default_size=None):
    cfg = json.dumps(spec.model_dump(), ensure_ascii=True)
    header = '''# Generated by AISI-figure: one chart, reproducible from source_data.csv.
# figure-style.R is included in the complete reproduction ZIP.
library(labstyle)
library(ggplot2)
source("figure-style.R")
d <- if(file.exists("source-schema.json")) { source("wide-table.R"); ais_read_wide() } else read.csv("source_data.csv", check.names = FALSE, encoding = "UTF-8", stringsAsFactors = FALSE)
cfg <- jsonlite::fromJSON(CONFIG)
col <- function(role) d[[cfg$columns[[role]]]]
has <- function(role) !is.null(cfg$columns[[role]]) && nzchar(cfg$columns[[role]])
features <- unlist(cfg$columns$predictors)
if(isTRUE(cfg$all_numeric_features)) features <- unlist(jsonlite::fromJSON("analysis-settings.json")$columns$predictors)
pal <- function(n) lab_colors(if (n <= 2) "binary" else if (n <= 10) "categorical" else "clusters", n)
logp <- function(x) -log10(pmax(x, 1e-300))
set.seed(42)
s <- data.frame()
wh <- ais_size(cfg$chart)
'''.replace("CONFIG", '"analysis-settings.json"' if len(spec.columns.get('predictors', [])) > 200 else json.dumps(cfg, ensure_ascii=True))
    chart = spec.chart
    if default_size:
        header = header.replace('wh <- ais_size(cfg$chart)', f'wh <- c({default_size[0]}, {default_size[1]})  # width, height in inches')
    if chart in ("volcano", "ma"):
        body = '''z <- data.frame(gene = col("label"), effect = col("effect"), padj = col("padj"))
z$status <- factor(ifelse(z$padj < cfg$p_threshold & z$effect >= cfg$effect_threshold, "Up", ifelse(z$padj < cfg$p_threshold & z$effect <= -cfg$effect_threshold, "Down", "Other")), levels=c("Down","Other","Up"))
z$plot_y <- logp(z$padj)
'''
        if chart == "volcano":
            body += '''p <- ggplot(z, aes(effect, plot_y, colour=status)) + geom_point(size=ais_house$point$standard, alpha=.7) + geom_vline(xintercept=c(-cfg$effect_threshold,cfg$effect_threshold), linetype=2, linewidth=ais_house$line$thin, colour=ais_house$neutral$guide) + geom_hline(yintercept=logp(cfg$p_threshold),linetype=2,linewidth=ais_house$line$thin,colour=ais_house$neutral$guide) + labs(x="log2 fold change",y="-log10(adjusted P)")
if (cfg$label_count > 0) { candidates <- z[z$status!="Other",]; lab <- head(candidates[order(candidates$padj, -abs(candidates$effect)),], cfg$label_count); p <- p + ggrepel::geom_text_repel(data=lab,aes(label=gene),size=ais_house$text$small,max.overlaps=Inf,seed=42,box.padding=.4,point.padding=.2,show.legend=FALSE,max.time=1) }
'''
        else:
            body += '''z$mean <- col("mean")
p <- ggplot(z,aes(mean,effect,colour=status)) + geom_point(size=ais_house$point$standard,alpha=.7) + geom_hline(yintercept=c(-cfg$effect_threshold,0,cfg$effect_threshold),linetype=2,linewidth=ais_house$line$thin,colour=ais_house$neutral$guide) + labs(x="Mean expression (input units)",y="log2 fold change")
'''
        body += '''p <- p + scale_colour_manual(values=c("Down"=lab_colors("binary")[1],"Other"=ais_house$neutral$other,"Up"=lab_colors("binary")[2]),drop=FALSE) + ais_theme()
s <- data.frame(status=levels(z$status), genes=as.integer(table(z$status)),effect_threshold=cfg$effect_threshold,p_threshold=cfg$p_threshold)
'''
    elif chart in ("embedding", "feature", "scatter"):
        body = '''z <- data.frame(x=col("x"),y=col("y"))
'''
        if chart == "feature":
            body += '''z$value <- col("value")
p <- ggplot(z,aes(x,y,colour=value)) + geom_point(size=ais_house$point$dense,alpha=.85) + scale_colour_gradient(low=ais_house$neutral$light,high=lab_colors("binary")[2],name=cfg$columns$value) + ais_theme() + coord_equal()
s <- data.frame(n=nrow(z),min=min(z$value),max=max(z$value),mean=mean(z$value))
'''
        elif chart == "embedding":
            body += '''z$group <- factor(col("group"))
p <- ggplot(z,aes(x,y,colour=group)) + geom_point(size=ais_house$point$dense,alpha=.8) + scale_colour_manual(values=pal(nlevels(z$group)),name=cfg$columns$group) + ais_theme() + coord_equal()
s <- data.frame(group=levels(z$group),n=as.integer(table(z$group)))
'''
        else:
            body += '''if (has("group")) z$group <- factor(col("group"))
p <- ggplot(z,aes(x,y)) + geom_point(size=ais_house$point$standard,alpha=.75) + geom_smooth(method="lm",formula=y~x,se=TRUE,colour=lab_colors("binary")[1],linewidth=ais_house$line$curve) + ais_theme()
if (has("group")) p <- p + aes(colour=group) + scale_colour_manual(values=pal(nlevels(z$group)),name=cfg$columns$group)
s <- do.call(rbind,lapply(c("spearman","pearson"),function(m) { ct <- suppressWarnings(cor.test(z$x,z$y,method=m,exact=FALSE)); data.frame(method=m,r=unname(ct$estimate),p=ct$p.value,n=nrow(z)) }))
p <- p + labs(caption=paste(sprintf("%s r = %.3f; p = %.3g",s$method,s$r,s$p),collapse="\\n"))
'''
        body += '''p <- p + labs(x=cfg$columns$x,y=cfg$columns$y)
'''
    elif chart in ("expression_heatmap", "sample_distance"):
        body = '''m <- as.matrix(d[,features,drop=FALSE]); rownames(m) <- as.character(col("label"))
if(cfg$scaling == "row_z") { m <- t(scale(t(m))); m[is.nan(m)] <- 0 }
if(cfg$scaling == "column_z") { m <- scale(m); m[is.nan(m)] <- 0 }
'''
        if chart == "sample_distance":
            body += '''m <- as.matrix(dist(m,method="euclidean"))
'''
        body += '''z <- data.frame(row=rep(rownames(m),times=ncol(m)),column=rep(colnames(m),each=nrow(m)),value=as.vector(m))
z$row <- factor(z$row,levels=rev(rownames(m))); z$column <- factor(z$column,levels=colnames(m))
p <- ggplot(z,aes(column,row,fill=value)) + geom_tile() + labs(x=NULL,y=NULL,fill=if(cfg$chart=="sample_distance") "Euclidean distance" else cfg$scaling) + ais_theme(x_angle=45) + theme(panel.grid=element_blank())
if(cfg$chart=="expression_heatmap" && cfg$scaling!="none") p <- p + scale_fill_gradient2(low=lab_colors("binary")[1],mid="white",high=lab_colors("binary")[2],midpoint=0,na.value=ais_house$neutral$missing) else p <- p + scale_fill_gradient(low="white",high=lab_colors("binary")[1],na.value=ais_house$neutral$missing)
s <- z
wh <- ais_matrix_size(nrow(m),ncol(m),rownames(m),colnames(m))
'''
    elif chart in ("marker_dot", "lr_dot"):
        body = '''z <- data.frame(label=col("label"),group=col("group"),value=col("value"))
z$size <- if(cfg$chart=="marker_dot") col("pct") else logp(col("padj"))
if(cfg$chart=="lr_dot") z$padj <- col("padj")
p <- ggplot(z,aes(group,label,size=size,colour=value)) + geom_point() + scale_size_continuous(range=c(ais_house$point$dense,ais_house$point$standard*3),name=if(cfg$chart=="marker_dot") "Percent expressing" else "-log10(adjusted P)") + scale_colour_gradient(low=ais_house$neutral$missing,high=lab_colors("binary")[2],name=cfg$columns$value) + labs(x=NULL,y=NULL) + ais_theme(x_angle=45)
s <- z
wh <- ais_matrix_size(length(unique(z$label)),length(unique(z$group)),unique(z$label),unique(z$group),legend_labels=c(cfg$columns$value,if(cfg$chart=="marker_dot") "Percent expressing" else "-log10(adjusted P)"))
'''
    elif chart == "composition":
        body = '''z <- data.frame(sample=col("sample"),group=col("group"),count=if(has("count")) col("count") else 1)
z <- aggregate(count~sample+group,z,sum); z$fraction <- z$count/ave(z$count,z$sample,FUN=sum)
z$group <- factor(z$group)
p <- ggplot(z,aes(sample,fraction,fill=group)) + geom_col(width=.75) + scale_fill_manual(values=pal(nlevels(z$group)),name=cfg$columns$group) + scale_y_continuous(labels=function(x) paste0(round(x*100),"%")) + labs(x=cfg$columns$sample,y="Cell composition") + ais_theme(x_angle=45)
s <- z
'''
    elif chart in ("enrichment_dot", "enrichment_bar"):
        body = '''z <- data.frame(term=col("label"),padj=col("padj"))
z$significance <- logp(z$padj)
'''
        if chart == "enrichment_dot":
            body += '''ratio <- function(v) vapply(strsplit(as.character(v),"/",fixed=TRUE),function(a) if(length(a)==2) as.numeric(a[1])/as.numeric(a[2]) else as.numeric(a[1]),numeric(1))
z$ratio <- ratio(col("ratio")); z$count <- col("count")
p <- ggplot(z,aes(ratio,reorder(term,significance),size=count,colour=significance)) + geom_point() + scale_colour_gradient(low=ais_house$neutral$other,high=lab_colors("binary")[2],name="-log10(adjusted P)") + scale_size_continuous(range=c(ais_house$point$standard,ais_house$point$standard*3),name="Gene count") + labs(x="Gene ratio",y=NULL) + ais_theme()
'''
        else:
            body += '''p <- ggplot(z,aes(significance,reorder(term,significance))) + geom_col(fill=lab_colors("binary")[1],width=.7) + labs(x="-log10(adjusted P)",y=NULL) + ais_theme()
'''
        body += '''s <- z; wh <- ais_category_size(nrow(z),z$term,legend=cfg$chart=="enrichment_dot")
'''
    elif chart == "gsea":
        body = '''z <- data.frame(rank=col("rank"),running_ES=col("value")); z <- z[order(z$rank),]
p <- ggplot(z,aes(rank,running_ES)) + geom_hline(yintercept=0,colour=ais_house$neutral$guide,linewidth=ais_house$line$thin) + geom_line(colour=lab_colors("binary")[1],linewidth=ais_house$line$curve) + labs(x="Rank in ordered gene list",y="Running enrichment score (input)") + ais_theme()
s <- data.frame(input_points=nrow(z),max_running_ES=max(z$running_ES),min_running_ES=min(z$running_ES))
'''
    elif chart in ("paired", "paired_delta"):
        body = '''z <- data.frame(pair=as.character(col("pair")),condition=as.character(col("group")),value=col("value"))
other <- setdiff(sort(unique(z$condition)),cfg$reference); z$condition <- factor(z$condition,levels=c(cfg$reference,other))
a <- z[z$condition==cfg$reference,]; b <- z[z$condition==other,]; b <- b[match(a$pair,b$pair),]
delta <- b$value-a$value
wt <- suppressWarnings(wilcox.test(b$value,a$value,paired=TRUE,exact=FALSE))
s <- data.frame(reference=cfg$reference,comparison=other,n_pairs=length(delta),mean_delta=mean(delta),median_delta=median(delta),test="paired Wilcoxon",p=wt$p.value)
'''
        if chart == "paired":
            body += '''p <- ggplot(z,aes(condition,value,group=pair)) + geom_line(colour=ais_house$neutral$other,linewidth=ais_house$line$standard) + geom_point(aes(colour=condition),size=ais_house$point$standard) + scale_colour_manual(values=pal(2),guide="none") + labs(x=NULL,y=cfg$columns$value) + ais_theme()
'''
        else:
            body += '''dd <- data.frame(pair=factor(a$pair,levels=a$pair),delta=delta)
p <- ggplot(dd,aes(pair,delta)) + geom_hline(yintercept=0,linetype=2,colour=ais_house$neutral$guide) + geom_segment(aes(xend=pair,y=0,yend=delta),colour=ais_house$neutral$guide) + geom_point(colour=lab_colors("binary")[1],size=ais_house$point$standard) + labs(x="Pair ID",y=paste0(other," - ",cfg$reference)) + ais_theme(x_angle=45)
'''
        body += '''p <- p + labs(caption=sprintf("Paired Wilcoxon p = %s\\nn = %d pairs",format_p_value(wt$p.value),length(delta)))
'''
    elif chart == "pca":
        body = '''m <- as.matrix(d[,features,drop=FALSE])
if(cfg$scaling=="row_z") m <- t(scale(t(m)))
fit <- prcomp(m,center=TRUE,scale.=cfg$scaling=="column_z")
variance <- fit$sdev^2/sum(fit$sdev^2)
z <- data.frame(sample=col("label"),PC1=fit$x[,1],PC2=fit$x[,2])
p <- ggplot(z,aes(PC1,PC2)) + geom_point(size=ais_house$point$standard,colour=lab_colors("binary")[1]) + labs(x=sprintf("PC1 (%.1f%%)",100*variance[1]),y=sprintf("PC2 (%.1f%%)",100*variance[2])) + ais_theme()
if(has("group")) { z$group <- factor(col("group")); p <- ggplot(z,aes(PC1,PC2,colour=group)) + geom_point(size=ais_house$point$standard) + scale_colour_manual(values=pal(nlevels(z$group)),name=cfg$columns$group) + labs(x=sprintf("PC1 (%.1f%%)",100*variance[1]),y=sprintf("PC2 (%.1f%%)",100*variance[2])) + ais_theme() }
s <- data.frame(component=paste0("PC",seq_along(variance)),variance_explained=variance)
write.csv(z,"pca_coordinates.csv",row.names=FALSE); write.csv(fit$rotation,"pca_loadings.csv")
'''
    elif chart == "missingness":
        body = '''s <- data.frame(column=features,missing=vapply(d[,features,drop=FALSE],function(x) sum(is.na(x)),integer(1)),rows=nrow(d))
s$fraction <- s$missing/s$rows
p <- ggplot(s,aes(reorder(column,fraction),fraction)) + geom_col(fill=lab_colors("binary")[1],width=.7) + coord_flip() + scale_y_continuous(labels=function(x) paste0(round(100*x),"%"),limits=c(0,1)) + labs(x=NULL,y="Missing values") + ais_theme()
wh <- ais_category_size(length(features),features)
'''
    elif chart == "upset":
        body = '''m <- as.matrix(d[,features,drop=FALSE]); combinations <- apply(m,1,paste0,collapse="")
tab <- sort(table(combinations),decreasing=TRUE); tab <- tab[names(tab)!=paste0(rep(0,ncol(m)),collapse="")]
if(length(tab)==0) stop("No non-empty intersections")
z <- data.frame(intersection=names(tab),count=as.numeric(tab)); z$intersection <- factor(z$intersection,levels=names(tab))
top <- ggplot(z,aes(intersection,count)) + geom_col(fill=lab_colors("binary")[1],width=.7) + labs(x=NULL,y="Intersection size") + ais_theme() + theme(axis.text.x=element_blank(),axis.ticks.x=element_blank())
grid <- expand.grid(intersection=names(tab),set=seq_along(features)); grid$member <- mapply(function(x,i) as.integer(substr(x,i,i)),grid$intersection,grid$set)
grid$intersection <- factor(grid$intersection,levels=names(tab))
bottom <- ggplot(grid,aes(intersection,set)) + geom_point(colour=ais_house$neutral$light,size=ais_house$point$standard) + geom_line(data=grid[grid$member==1,],aes(group=intersection),colour=lab_colors("binary")[1],linewidth=ais_house$line$standard) + geom_point(data=grid[grid$member==1,],colour=lab_colors("binary")[1],size=ais_house$point$standard) + scale_y_continuous(breaks=seq_along(features),labels=features) + labs(x="Exact intersection membership",y=NULL) + ais_theme() + theme(axis.text.x=element_blank(),axis.ticks.x=element_blank())
p <- patchwork::wrap_plots(top,bottom,ncol=1,heights=c(2,1)); s <- z
wh <- ais_matrix_size(length(features)+5,length(tab),features,names(tab))
'''
    elif chart == "network":
        body = '''edges <- data.frame(source=as.character(col("source")),target=as.character(col("target")),weight=col("weight"))
names <- sort(unique(c(edges$source,edges$target))); angle <- seq(0,2*pi,length.out=length(names)+1)[-1]
nodes <- data.frame(node=names,x=cos(angle),y=sin(angle)); nodes$degree <- as.integer(table(factor(c(edges$source,edges$target),levels=names)))
edges$x <- nodes$x[match(edges$source,nodes$node)]; edges$y <- nodes$y[match(edges$source,nodes$node)]; edges$xend <- nodes$x[match(edges$target,nodes$node)]; edges$yend <- nodes$y[match(edges$target,nodes$node)]
p <- ggplot() + geom_segment(data=edges,aes(x,y,xend=xend,yend=yend,linewidth=weight),alpha=.35,colour=lab_colors("binary")[1],arrow=grid::arrow(length=grid::unit(.08,"inches"))) + scale_linewidth_continuous(range=c(.2,2),name="Input weight") + geom_point(data=nodes,aes(x,y,size=degree),colour=lab_colors("binary")[1]) + ggrepel::geom_text_repel(data=nodes,aes(x,y,label=node),size=ais_house$text$small,seed=42,max.overlaps=Inf,show.legend=FALSE) + coord_equal(clip="off") + ais_theme() + theme(axis.title=element_blank(),axis.text=element_blank(),axis.ticks=element_blank(),axis.line=element_blank())
s <- nodes
'''
    elif chart == "histogram":
        body = '''z <- data.frame(value=col("value"))
p <- ggplot(z,aes(value)) + geom_histogram(bins=cfg$bins,fill=lab_colors("binary")[1],colour="white",linewidth=ais_house$line$thin) + labs(x=cfg$columns$value,y="Frequency") + ais_theme()
s <- data.frame(n=nrow(z),mean=mean(z$value),sd=sd(z$value),median=median(z$value),min=min(z$value),max=max(z$value))
'''
    else:
        body = '''z <- data.frame(x=col("x"),y=col("y"))
if(has("group")) z$group <- factor(col("group"))
if(cfg$geometry %in% c("box","violin")) z$x <- factor(z$x)
p <- ggplot(z,aes(x,y))
if(has("group")) p <- p + aes(colour=group)
if(cfg$geometry=="point") p <- p + geom_point(size=ais_house$point$standard,alpha=.75)
if(cfg$geometry=="line") p <- p + geom_line(linewidth=ais_house$line$curve) + geom_point(size=ais_house$point$standard)
if(cfg$geometry=="bar") p <- p + geom_col(fill=lab_colors("binary")[1],width=.7)
if(cfg$geometry=="box") p <- p + geom_boxplot() + geom_jitter(width=.12,size=ais_house$point$standard)
if(cfg$geometry=="violin") p <- p + geom_violin() + geom_point(position=position_jitter(width=.1,seed=42),size=ais_house$point$standard)
if(has("group")) p <- p + scale_colour_manual(values=pal(nlevels(z$group)),name=cfg$columns$group)
p <- p + labs(x=cfg$columns$x,y=cfg$columns$y) + ais_theme()
s <- data.frame(input_rows=nrow(z),geometry=cfg$geometry)
'''
    footer = '''
if(nzchar(cfg$title)) { if(cfg$chart=="upset") p <- p + patchwork::plot_annotation(title=cfg$title) else p <- p + labs(title=cfg$title) }
if(nzchar(cfg$x_label) && cfg$chart!="upset") p <- p + labs(x=cfg$x_label)
if(nzchar(cfg$y_label) && cfg$chart!="upset") p <- p + labs(y=cfg$y_label)
if(cfg$size!="template") wh <- lab_sizes()[[cfg$size]]
p <- ais_apply_colors(p)
wh <- ais_export_size(wh)
ais_write_style(wh)
save_fig(p,"figure",dir=".",size=wh,formats=c("pdf","png","svg"))
if(any(grepl("[^ -~]",c(names(d),unlist(d[vapply(d,is.character,logical(1))]),cfg$title,cfg$x_label,cfg$y_label),perl=TRUE))) { grDevices::cairo_pdf("figure.pdf",width=wh[1],height=wh[2],family="Arial"); print(p); grDevices::dev.off() }
jsonlite::write_json(s,"stats.json",dataframe="rows",auto_unbox=TRUE,na="null",pretty=TRUE,digits=NA)
write.csv(s,"statistics.csv",row.names=FALSE)
writeLines(capture.output(sessionInfo()),"session-info.txt")
'''
    return header + body + footer


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
    return pd.DataFrame({"x": np.arange(30), "y": rng.normal(0, 1, 30).cumsum()}), {"x": "x", "y": "y"}, {"geometry": "line"}
