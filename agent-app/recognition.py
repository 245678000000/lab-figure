"""Recognise exported result tables by explicit column signatures; never transform units."""
import re
from preferences import group_key


def recognize_frame(d):
    index={}
    for name in d.columns:
        index.setdefault(re.sub(r'[\s_.-]+','',str(name)).casefold(),[]).append(str(name))
    def col(*aliases):
        for name in aliases:
            found=index.get(re.sub(r'[\s_.-]+','',name).casefold(),[])
            if len(found)==1: return found[0]
        return None
    candidates=[]
    def add(name,evidence,suggestions,notes=None,subset=None):
        candidates.append({'name':name,'evidence':evidence,'suggestions':suggestions,'notes':notes or [],'subset':subset})
    gene=col('gene','gene_id','symbol','gene_symbol','feature','features.plot')
    effect=col('log2FoldChange'); padj=col('padj'); mean=col('baseMean')
    if effect and padj and mean:
        mapping={'effect':effect,'padj':padj,'mean':mean}
        if gene: mapping['label']=gene
        notes=['读取已有差异结果，不重新进行差异检验；不会用原始 P 值替代校正 P 值。']
        if not gene: notes.append('未找到明确基因列，请在列映射中指定；不会把行号当作基因名。')
        add('DESeq2 差异结果',[effect,padj,mean],[{'chart':'volcano','columns':mapping},{'chart':'ma','columns':mapping}],notes)
    marker_effect=col('avg_log2FC'); marker_p=col('p_val_adj')
    if marker_p and (marker_effect or col('avg_logFC')):
        notes=['使用已有 marker 结果，不把 pct.1 / pct.2 自动当作 DotPlot 的百分比。']
        mapping={'padj':marker_p}
        if gene: mapping['label']=gene
        if marker_effect: mapping['effect']=marker_effect
        else: notes.append('avg_logFC 未声明对数底，确认并转换为 log2FC 后再映射；不会自动当作 log2。')
        cluster=col('cluster','ident','comparison','contrast')
        subset=None
        if cluster and d[cluster].nunique()>1:
            subset={'column':cluster,'values':sorted({group_key(x) for x in d[cluster].dropna().unique()})}
            notes.append('检测到多个分群或比较，请先选择一个再画火山图，避免混合不同对照。')
        add('Seurat marker 结果',[c for c in [marker_effect or col('avg_logFC'),marker_p,cluster] if c],[{'chart':'volcano','columns':mapping}],notes,subset)
    term=col('Description'); ep=col('p.adjust'); ratio=col('GeneRatio'); count=col('Count')
    if term and ep and ratio and count:
        mapping={'label':term,'padj':ep,'ratio':ratio,'count':count}
        cluster=col('Cluster','comparison','contrast'); subset=None
        notes=['保留全部条目，GeneRatio 支持 a/b；不会重新运行 GO / KEGG 富集。']
        if cluster and d[cluster].nunique()>1:
            subset={'column':cluster,'values':sorted({group_key(x) for x in d[cluster].dropna().unique()})}
            notes.append('包含多个比较，请先选择一个比较。')
        add('clusterProfiler 富集结果',[term,ep,ratio,count],[{'chart':'enrichment_dot','columns':mapping},{'chart':'enrichment_bar','columns':mapping}],notes,subset)
    elif col('NES') and ep and term:
        add('GSEA 结果汇总',[col('NES'),ep,term],[],['这是 NES / 显著性汇总，缺少逐位 running ES；不能仅凭 NES 生成 GSEA 运行曲线。'])
    group=col('celltype','cell_type','seurat_clusters','cluster','annotation','group','ident','id')
    for method,x,y in [('UMAP',col('UMAP_1'),col('UMAP_2')),('t-SNE',col('tSNE_1','TSNE_1'),col('tSNE_2','TSNE_2'))]:
        if x and y:
            mapping={'x':x,'y':y}
            if group: mapping['group']=group
            add('已有 '+method+' 坐标',[x,y]+([group] if group else []),[{'chart':'embedding','columns':mapping,'embedding_method':method}],['只读取已有坐标，不把任意两列重命名为新计算的嵌入。'])
    avg=col('avg.exp','avg_exp'); pct=col('pct.exp','pct_exp'); feature=col('features.plot','gene'); dot_group=col('id','celltype','cluster','group')
    if avg and pct and feature and dot_group:
        add('Seurat DotPlot 长表',[feature,dot_group,avg,pct],[{'chart':'marker_dot','columns':{'label':feature,'group':dot_group,'value':avg,'pct':pct}}],['按 Seurat DotPlot 的 0–100 百分比列使用 pct.exp；自定义表请核对单位，不自动将 0–1 乘以 100。'])
    return {'candidates':candidates,'basis':'仅按列结构匹配，来源及分析定义需核对。'}
