"""Local data inspection, reproducible template compilation, and figure execution."""
from __future__ import annotations

import hashlib
import copy
import csv
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from bio import BIO_CATALOG, compile_bio, validate_bio
from recognition import recognize_frame
import preferences
import task_control

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
STORE = Path(os.environ.get("LAB_AGENT_STORAGE", ROOT / "workspace")).resolve()
STORE.mkdir(parents=True, exist_ok=True)
ARTIFACT_FILES = {'figure.pdf','figure.png','figure.svg','figure.R','figure.py','source_data.csv',
                  'statistics.csv','stats.json','manifest.json','render.log','collision-audit.json',
                  'session-info.txt','figure-style.R','figure-style.json','figure_style.py',
                  'plot-settings.json','render-colors.json','pca_coordinates.csv','pca_loadings.csv',
                  'analysis-settings.json','source-schema.json','wide-table.R','analysis-context.json',
                  'figure-edit.R','figure_edit_helpers.py','figure-edit-info.json'}


def build_bundle(folder):
    """Include known outputs, also repairing historical bundles without rerendering."""
    files = sorted(p for p in folder.iterdir() if p.is_file() and not p.is_symlink() and p.name in ARTIFACT_FILES)
    target = folder / 'reproduce.zip'
    if target.exists():
        try:
            with zipfile.ZipFile(target) as z:
                if set(z.namelist()) == {p.name for p in files} and all(z.getinfo(p.name).file_size == p.stat().st_size and target.stat().st_mtime >= p.stat().st_mtime for p in files):
                    return target
        except (OSError, zipfile.BadZipFile, KeyError):
            pass
    temporary = folder / ('bundle-' + uuid.uuid4().hex + '.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
            for file in files:
                z.write(file, file.name)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
RSCRIPT = str(REPO / ".runtime/R/bin/Rscript.exe")
CATALOG = {
    "roc": {"name": "ROC 曲线", "fields": {"outcome": "二分类结局", "predictor": "预测指标"}, "numeric": ["predictor"]},
    "box": {"name": "箱线图", "fields": {"group": "分组", "value": "数值指标"}, "numeric": ["value"]},
    "violin": {"name": "小提琴图", "fields": {"group": "分组", "value": "数值指标"}, "numeric": ["value"]},
    "km": {"name": "KM 生存曲线", "fields": {"time": "生存时间", "event": "事件状态", "group": "分组"}, "numeric": ["time"]},
    "forest": {"name": "Cox 森林图", "fields": {"time": "生存时间", "event": "事件状态", "predictors": "模型变量（可多选）"}, "numeric": ["time"]},
    "rate_bar": {"name": "应答率柱状图", "fields": {"group": "分组", "outcome": "二分类结局"}, "numeric": []},
    "auc_bar": {"name": "AUC 对比", "fields": {"outcome": "二分类结局", "predictors": "预测指标（可多选）"}, "numeric": ["predictors"]},
    "cor_heatmap": {"name": "相关性热图", "fields": {"predictors": "相关指标（至少两列）"}, "numeric": ["predictors"]},
    "pie": {"name": "构成饼图", "fields": {"group": "类别"}, "numeric": []},
}
for info in CATALOG.values():
    info.setdefault("family", "基础与临床")
    info.setdefault("optional", {})
    info.setdefault("hint", "按所选变量调用已有实验室作图模板。")
CATALOG.update(BIO_CATALOG)


class PlotSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chart: Literal[tuple(CATALOG)] = "roc"
    engine: Literal["r", "python"] = "r"
    columns: dict[str, str | list[str]] = Field(default_factory=dict)
    positive: str = ""
    direction: Literal["<", ">"] = "<"
    method: Literal["spearman", "pearson"] = "spearman"
    title: str = Field(default="", max_length=120)
    x_label: str = Field(default="", max_length=120)
    y_label: str = Field(default="", max_length=120)
    size: Literal["template", "single", "wide", "narrow", "roc", "roc_multi", "km", "forest", "violin", "auc_bar", "pie", "bar2"] = "template"
    show_n: bool = True
    comparisons: Literal["default", "all", "none"] = "default"
    exvivo: bool = False
    p_threshold: float = Field(default=.05, gt=0, le=1)
    effect_threshold: float = Field(default=1, gt=0)
    label_count: int = Field(default=10, ge=0, le=30)
    scaling: Literal["none", "row_z", "column_z"] = "none"
    reference: str = ""
    embedding_method: Literal["UMAP", "t-SNE", "provided"] = "UMAP"
    bins: int = Field(default=30, ge=3, le=100)
    geometry: Literal["point", "line", "bar", "box", "violin"] = "point"
    width_mm: float | None = Field(default=None, ge=25, le=400)
    height_mm: float | None = Field(default=None, ge=25, le=450)
    use_group_colors: bool = True
    subset_column: str = ""
    subset_value: str = ""
    matrix_orientation: Literal["", "samples"] = ""
    all_numeric_features: bool = False

    @model_validator(mode="after")
    def check_export_selection(self):
        if self.height_mm is not None and self.width_mm is None:
            raise ValueError("自定义高度需要同时填写宽度")
        if bool(self.subset_column) != bool(self.subset_value):
            raise ValueError("请同时选择筛选列和筛选值")
        return self


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def located(kind, key):
    if not re.fullmatch(r"[a-f0-9]{12}", key):
        raise ValueError("无效的记录编号")
    p = STORE / kind / key
    if not p.is_dir():
        raise ValueError("记录不存在")
    return p


MAX_ROWS = 100_000
MAX_COLUMNS = 50_001
MAX_CELLS = 10_000_000
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def check_table_size(rows, columns):
    if rows > MAX_ROWS:
        raise ValueError('表格最多支持 100,000 行')
    if columns > MAX_COLUMNS:
        raise ValueError('表格最多支持 50,001 列（包括标识列）')
    if rows * columns > MAX_CELLS:
        raise ValueError('表格最多支持 10,000,000 个单元格，请先选择需要的样本或特征')


def _identifier_read_options(columns, string_columns):
    if not string_columns:
        return {}
    # Keep identifier tokens lexical while retaining normal NA parsing for measurements.
    tokens = ['', '#N/A', '#N/A N/A', '#NA', '-1.#IND', '-1.#QNAN', '-NaN', '-nan', '1.#IND', '1.#QNAN', '<NA>', 'N/A', 'NA', 'NULL', 'NaN', 'None', 'n/a', 'nan', 'null']
    return {'dtype': {c: str for c in string_columns}, 'keep_default_na': False,
            'na_values': {c: tokens for c in columns if c not in string_columns}}


def check_column_names(names):
    # Check the actual header before pandas silently renames repeated names.
    names = [str(name) for name in names if name is not None and str(name).strip()]
    if len(set(names)) != len(names):
        raise ValueError('存在重复列名，请为每列设置唯一名称')


def read_table(path, sheet=None, header=1, string_columns=None):
    if not 1 <= header <= 30:
        raise ValueError("表头行需在 1–30 之间")
    if path.suffix.lower() == ".xlsx":
        with pd.ExcelFile(path) as book:
            sheets = book.sheet_names
            selected = sheet or sheets[0]
            if selected not in sheets:
                raise ValueError("工作表不存在")
            ws = book.book[selected]
            check_table_size(max(0, ws.max_row - header), ws.max_column)
            check_column_names(next(ws.iter_rows(min_row=header, max_row=header, values_only=True), ()))
            names = pd.read_excel(book, sheet_name=selected, header=header - 1, nrows=0).columns
            d = pd.read_excel(book, sheet_name=selected, header=header - 1, **_identifier_read_options(names, string_columns))
    else:
        sheets, selected = [], None
        for encoding in ["utf-8-sig", "gb18030"]:
            try:
                with path.open(encoding=encoding, newline='') as source:
                    rows = (row for row in csv.reader(source, delimiter='\t' if path.suffix.lower() == '.tsv' else ',')
                            if row and not (len(row) == 1 and not row[0].strip()))
                    for _ in range(header):
                        names = next(rows, [])
                    check_column_names(names)
                options = dict(sep="\t" if path.suffix.lower() == ".tsv" else ",", encoding=encoding, header=header - 1)
                names = pd.read_csv(path, nrows=0, **options).columns
                columns = len(names)
                options.update(_identifier_read_options(names, string_columns))
                check_table_size(0, columns)
                limit = min(MAX_ROWS, MAX_CELLS // max(1, columns))
                d = pd.read_csv(path, nrows=limit + 1, **options)
                check_table_size(len(d), columns)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("文件编码无法识别，请保存为 UTF-8 CSV")
    d = d.dropna(how="all").reset_index(drop=True)
    d.columns = [str(c) for c in d.columns]
    if not len(d) or not len(d.columns):
        raise ValueError("表格没有数据，请检查工作表和表头行")
    check_table_size(len(d), len(d.columns))
    if len(set(d.columns)) != len(d.columns):
        raise ValueError("存在重复列名，请为每列设置唯一名称")
    return d, sheets, selected


def exclusions():
    source = REPO.parent / "analysis_config/exvivo_sample_exclusions.tsv"
    if not source.exists():
        raise ValueError("ex vivo 排除清单缺失，请恢复 analysis_config/exvivo_sample_exclusions.tsv")
    tab = pd.read_csv(source, sep="\t").fillna("")
    aliases = set()
    for _, row in tab.iterrows():
        for key in ("canonical_sample_id", "geo_sample_id", "aliases"):
            aliases.update(str(v).casefold() for v in str(row[key]).split(";") if v)
    return aliases, source


def exclusion_mask(d):
    aliases, _ = exclusions()
    mask = pd.Series(False, index=d.index)
    # Exact, case-insensitive alias matching. HNSCC3_LD is never a prefix match.
    for col in d.select_dtypes(exclude=["number", "bool"]).columns:
        mask |= d[col].astype(str).str.strip().str.casefold().isin(aliases)
    return mask


def summarize(d):
    cols = []
    missing = d.isna().sum()
    numeric = set(d.select_dtypes(include=['number']).columns)
    minima = d[list(numeric)].min() if numeric else {}
    maxima = d[list(numeric)].max() if numeric else {}
    for col in d.columns:
        series = d[col]
        is_numeric = col in numeric
        distinct = series.dropna().unique()
        vals = [str(v) for v in distinct[:16]]
        low, high = minima.get(col), maxima.get(col)
        cols.append({'name': col, 'type': 'numeric' if is_numeric else 'categorical',
                     'missing': int(missing[col]), 'unique': len(distinct),
                     'values': vals, 'min': float(low) if low is not None and np.isfinite(low) else None,
                     'max': float(high) if high is not None and np.isfinite(high) else None})
    return {'rows': len(d), 'column_count': len(d.columns), 'columns': cols,
            'missing': int(missing.sum()), 'preview_columns': min(24, len(d.columns)),
            'preview': json.loads(d.iloc[:12, :24].to_json(orient='records', date_format='iso')),
            'exclusion_matches': int(exclusion_mask(d).sum())}


def store_dataset(content, filename, demo=False):
    suffix = Path(filename).suffix.lower()
    if suffix not in (".csv", ".tsv", ".xlsx"):
        raise ValueError("请选择 CSV、TSV 或 XLSX 文件")
    key = uuid.uuid4().hex[:12]
    folder = STORE / "datasets" / key
    folder.mkdir(parents=True)
    source = folder / ("original" + suffix)
    source.write_bytes(content)
    d, sheets, sheet = read_table(source)
    metadata = {"id": key, "filename": Path(filename.replace("\\", "/")).name, "original": source.name,
                "sha256": hashlib.sha256(content).hexdigest(), "sheet": sheet, "sheets": sheets,
                "header": 1, "demo": demo, "created": time.time(), "summary": summarize(d), "recognition": recognize_frame(d)}
    write_json(folder / "metadata.json", metadata)
    return metadata


def load_dataset(key, string_columns=None):
    folder = located("datasets", key)
    metadata = read_json(folder / "metadata.json")
    identifiers = list(dict.fromkeys([*metadata.get('id_columns', []), *(string_columns or [])]))
    d, _, _ = read_table(folder / metadata["original"], metadata["sheet"], metadata["header"], string_columns=identifiers)
    return d, metadata


def demo_dataset():
    rng = np.random.default_rng(42)
    n = 72
    group = np.array(["Control"] * 36 + ["Treatment"] * 36)
    outcome = np.concatenate([rng.binomial(1, .28, 36), rng.binomial(1, .64, 36)])
    d = pd.DataFrame({"sample_id": [f"DEMO_{i+1:03}" for i in range(n)], "group": group,
                      "response": outcome, "score": np.round(rng.normal(0, 1, n) + outcome * .8, 3),
                      "marker_b": np.round(rng.normal(5, 1.3, n) + outcome * .6, 3),
                      "marker_c": np.round(rng.normal(3, .8, n) + (group == "Treatment") * .6, 3),
                      "time_months": np.round(rng.exponential(20, n) + 1, 1), "event": rng.binomial(1, .65, n)})
    return store_dataset(d.to_csv(index=False).encode("utf-8"), "demo_cohort.csv", True)


def resolve_features(d, spec, metadata=None):
    if spec.all_numeric_features:
        if spec.chart != 'pca':
            raise ValueError('全部数值特征选项仅用于 PCA')
        spec = spec.model_copy(deep=True)
        excluded = {spec.columns.get('label'), spec.columns.get('group')} | set((metadata or {}).get('annotation_columns', []))
        spec.columns['predictors'] = [c for c in d.select_dtypes(include=['number']).columns if c not in excluded]
    return spec


def validate_spec(d, spec, metadata=None):
    spec = resolve_features(d, spec, metadata)
    if spec.chart == 'pca' and spec.matrix_orientation != 'samples':
        raise ValueError('PCA 需要先确认矩阵方向：每行一个样本、每列一个特征；基因在行时请先预览转置。')
    required = CATALOG[spec.chart]["fields"]
    for role, label in required.items():
        value = spec.columns.get(role)
        if not value:
            raise ValueError(f"请选择{label}")
        if role == "predictors" and not isinstance(value, list):
            raise ValueError(f"{label}必须是列名列表")
        if role != "predictors" and not isinstance(value, str):
            raise ValueError(f"{label}只能选择一列")
        for col in value if isinstance(value, list) else [value]:
            if col not in d.columns:
                raise ValueError(f"列 {col} 不存在")
            if "`" in col and spec.chart == "forest":
                raise ValueError("Cox 模型变量名中不能包含反引号，请先重命名该列")
    used = list(dict.fromkeys(c for role in required for c in (spec.columns[role] if isinstance(spec.columns[role], list) else [spec.columns[role]])))
    for role in CATALOG[spec.chart].get("optional", {}):
        col = spec.columns.get(role)
        if col:
            if not isinstance(col, str) or col not in d.columns:
                raise ValueError(f"可选列 {role} 不存在")
            used.append(col)
            if role == "count" and not pd.api.types.is_numeric_dtype(d[col]):
                raise ValueError("汇总计数必须为数值列")
    if spec.chart == "cor_heatmap" and len(spec.columns["predictors"]) < 2:
        raise ValueError("相关性热图至少需要两个数值指标")
    if spec.chart == "forest" and len(spec.columns["predictors"]) > 12:
        raise ValueError("第一版 Cox 模型最多选择 12 个变量")
    if spec.engine == "python" and spec.chart not in ("roc", "box", "rate_bar"):
        raise ValueError("这个模板目前只有 R 实现，请切换 R 引擎")
    for role in CATALOG[spec.chart]["numeric"]:
        for col in spec.columns[role] if isinstance(spec.columns[role], list) else [spec.columns[role]]:
            if not pd.api.types.is_numeric_dtype(d[col]):
                raise ValueError(f"{col} 应为数值列，请检查表头或数据类型")
            if not np.isfinite(d[col].dropna()).all():
                raise ValueError(f"{col} 包含无穷值，请先处理")
    report = {"input_rows": len(d), "excluded_rows": 0, "missing_rows": 0, "notes": []}
    if spec.subset_column:
        if spec.subset_column not in d.columns:
            raise ValueError("筛选列不存在")
        mask = d[spec.subset_column].map(preferences.group_key).eq(spec.subset_value) & d[spec.subset_column].notna()
        if not mask.any():
            raise ValueError("所选分群或比较不存在")
        report["filtered_rows"] = int((~mask).sum())
        report["subset"] = {"column": spec.subset_column, "value": spec.subset_value}
        d = d.loc[mask].copy()
        report["notes"].append(f"按明确选择筛选 {spec.subset_column} = {spec.subset_value}，移出其他比较 {report['filtered_rows']} 行；原始表格保留。")
    if spec.exvivo:
        mask = exclusion_mask(d)
        report["excluded_rows"] = int(mask.sum())
        report["excluded_samples"] = json.loads(d.loc[mask].to_json(orient="records"))
        _, source = exclusions()
        report["exclusion_source"] = str(source)
        d = d.loc[~mask].copy()
        report["notes"].append("按用户确认的清单在样本选择阶段排除异常样本；保留原始输入。此处没有进行 CPM/TPM 输入替换或混样归因。")
        if spec.chart == "cor_heatmap":
            raise ValueError("ex vivo 相关性分析须分别计算 SCC 和 PCC。当前单图热图入口尚未实现这套专用流程，请使用项目既有分析脚本。")
        if spec.chart in ("volcano", "ma", "marker_dot", "lr_dot", "enrichment_dot", "enrichment_bar", "gsea", "network", "custom"):
            raise ValueError("此入口读取预计算结果，不能在绘图阶段重新计算其全流程统计。ex vivo 请先用排除后样本完成对应分析，再核对结果来源。")
    elif exclusion_mask(d).any():
        raise ValueError("数据含 HNSCC3 已确认异常样本。若这是 ex vivo 共培养数据，请勾选 ex vivo 选项后重试；其他分析请先澄清样本用途。")
    missing = d[used].isna().any(axis=1)
    if spec.chart in ("paired", "paired_delta", "upset") and missing.any():
        raise ValueError("配对或集合成员数据存在缺失，请明确处理规则；不会自动删除或填补")
    if spec.chart in ("missingness", "expression_heatmap"):
        report["notes"].append("缺失单元格保留展示；未做缺失值插补。")
        missing[:] = False
    report["missing_rows"] = int(missing.sum())
    d = d.loc[~missing].copy()
    report["analyzed_rows"] = len(d)
    if len(d) < 3:
        raise ValueError("去除缺失值及排除样本后，有效数据不足 3 行")
    if report["missing_rows"]:
        report["notes"].append(f"对本图选定变量使用共同完整样本，去除 {report['missing_rows']} 行缺失数据。")
    if spec.chart in ("roc", "auc_bar", "rate_bar", "km", "forest"):
        col = spec.columns["event" if spec.chart in ("km", "forest") else "outcome"]
        vals = list(d[col].unique())
        if len(vals) != 2:
            raise ValueError(f"{col} 需恰好包含两类，当前有 {len(vals)} 类")
        if not spec.positive:
            raise ValueError(f"请选择 {col} 的阳性/事件类别，agent 不会替你猜测")
        matches = [v for v in vals if str(v) == spec.positive]
        if not matches:
            raise ValueError(f"阳性类别 {spec.positive} 不在 {col} 中")
        counts = d[col].value_counts()
        if spec.chart in ("roc", "auc_bar") and counts.min() < 2:
            raise ValueError("ROC 的阳性和阴性组都至少需要两个有效样本")
        report["positive"] = spec.positive
        report["outcome_column"] = col
    if spec.chart in ("box", "violin", "rate_bar", "km"):
        g = spec.columns["group"]
        ng = d[g].nunique()
        if not 2 <= ng <= 10:
            raise ValueError("分组变量需包含 2–10 组，请不要把样本 ID 当作分组")
        report["groups"] = {str(k): int(v) for k, v in d[g].value_counts().items()}
        report["notes"].append("分组顺序采用模板默认排序；HR/OR 的参考组请核对统计表和脚本。")
    if spec.chart in ("km", "forest") and (d[spec.columns["time"]] < 0).any():
        raise ValueError("生存时间不能为负数")
    if spec.chart in BIO_CATALOG:
        d, report = validate_bio(d, spec, report)
    return d, report


def rstr(value):
    # JSON strings are valid R strings; encoding also prevents code interpolation.
    return json.dumps(str(value), ensure_ascii=False)


def rvec(values):
    return "c(" + ", ".join(rstr(x) for x in values) + ")"


def compile_r(spec, default_size=None):
    if spec.chart in BIO_CATALOG:
        return compile_bio(spec, default_size)
    c = spec.columns
    q = lambda role: rstr(c[role])
    n = "TRUE" if spec.show_n else "FALSE"
    positive = rstr(spec.positive)
    comparisons = "NULL" if spec.comparisons == "default" else rstr(spec.comparisons)
    common = f", show_n = {n}"
    if spec.chart == "roc":
        call = f"lab_roc(d, outcome = {q('outcome')}, predictor = {q('predictor')}, positive = {positive}, direction = {rstr(spec.direction)}{common})"
    elif spec.chart in ("box", "violin"):
        call = f"lab_{spec.chart}(d, x = {q('group')}, y = {q('value')}, comparisons = {comparisons}{common})"
    elif spec.chart == "rate_bar":
        call = f"lab_rate_bar(d, group = {q('group')}, outcome = {q('outcome')}, positive = {positive}, show_counts = {n})"
    elif spec.chart == "km":
        extra = (f", xlab = {rstr(spec.x_label)}" if spec.x_label else "") + (f", ylab = {rstr(spec.y_label)}" if spec.y_label else "")
        call = f"lab_km(d, time = {q('time')}, event = {q('event')}, group = {q('group')}, event_value = {positive}{common}{extra})"
    elif spec.chart == "forest":
        extra = f", xlab = {rstr(spec.x_label)}" if spec.x_label else ""
        call = f"lab_forest(lab_cox_table(d, time = {q('time')}, event = {q('event')}, terms = {rvec(c['predictors'])}, event_value = {positive}){extra})"
    elif spec.chart == "auc_bar":
        call = f"lab_auc_bar(lab_auc_table(d, outcome = {q('outcome')}, predictors = {rvec(c['predictors'])}, positive = {positive}, direction = {rstr(spec.direction)}))"
    elif spec.chart == "cor_heatmap":
        call = f"lab_cor_heatmap(d, vars = {rvec(c['predictors'])}, method = {rstr(spec.method)}, cluster = FALSE, show_values = TRUE)"
    else:
        call = f"lab_pie(d, category = {q('group')})"
    labels = []
    for key, value in [("title", spec.title), ("x", spec.x_label), ("y", spec.y_label)]:
        if value:
            labels.append(f"{key} = {rstr(value)}")
    additions = ""
    if labels:
        if spec.chart in ("forest", "km"):
            if spec.title:
                additions = f"\np <- p + patchwork::plot_annotation(title = {rstr(spec.title)})"
        else:
            additions = "\np <- p + ggplot2::labs(" + ", ".join(labels) + ")"
    size = "attr(p, 'lab_size')" if spec.size == "template" else rstr(spec.size)
    if default_size:
        size = f'c({default_size[0]}, {default_size[1]})'
    return f'''# Generated by AISI-figure. Run from this directory with Rscript figure.R
# source_data.csv is the exact analyzed subset; see manifest.json for exclusions and missingness.
# ---- data ----
library(labstyle)
source("figure-style.R")
d <- if(file.exists("source-schema.json")) {{ source("wide-table.R"); ais_read_wide() }} else read.csv("source_data.csv", check.names = FALSE, encoding = "UTF-8", stringsAsFactors = FALSE)
set.seed(42)
# ---- plot ----
p <- {call}
computed_stats <- lab_stats(p)
p <- ais_apply_colors(p)
{additions}
wh <- {size}
if (is.null(wh)) wh <- "single"
if (is.character(wh)) wh <- lab_sizes()[[wh]]
wh <- ais_export_size(wh)
ais_write_style(wh)
save_fig(p, "figure", dir = ".", size = wh, formats = c("pdf", "png", "svg"))
# For Unicode labels, Cairo embeds fonts and uses Windows font fallback.
label_text <- c(names(d), unlist(d[vapply(d, is.character, logical(1))]), {rstr(spec.title)}, {rstr(spec.x_label)}, {rstr(spec.y_label)})
if (any(grepl("[^ -~]", label_text, perl = TRUE))) {{
  grDevices::cairo_pdf("figure.pdf", width = wh[1], height = wh[2], family = "Arial")
  print(p)
  grDevices::dev.off()
}}
s <- computed_stats
jsonlite::write_json(s, "stats.json", dataframe = "rows", auto_unbox = TRUE, na = "null", pretty = TRUE, digits = NA)
if (!is.null(s)) write.csv(s, "statistics.csv", row.names = FALSE)
writeLines(capture.output(sessionInfo()), "session-info.txt")
'''


def compile_python(spec, default_size=None):
    c = spec.columns
    n = str(spec.show_n)
    if spec.chart == "roc":
        call = f"lab_roc(d, outcome={c['outcome']!r}, predictor={c['predictor']!r}, positive={spec.positive!r}, direction={spec.direction!r}, show_n={n})"
    elif spec.chart == "box":
        cmp = None if spec.comparisons == "default" else spec.comparisons
        call = f"lab_box(d, x={c['group']!r}, y={c['value']!r}, comparisons={cmp!r}, show_n={n})"
    else:
        call = f"lab_rate_bar(d, group={c['group']!r}, outcome={c['outcome']!r}, positive={spec.positive!r}, show_counts={n})"
    mods = ""
    for key, value in [("title", spec.title), ("xlabel", spec.x_label), ("ylabel", spec.y_label)]:
        if value:
            mods += f"\nfig.axes[0].set_{key}({value!r})"
    size = "None" if spec.size == "template" else repr(spec.size)
    if default_size:
        size = repr(tuple(default_size))
    return f'''# Generated by AISI-figure. Run from this directory with Python.
# ---- data ----
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from labstyle_py import lab_roc, lab_box, lab_rate_bar, save_fig, lab_stats
from figure_style import configure_colors, export_size, write_style
plt.rcParams["font.sans-serif"] = ["Arial", "Microsoft YaHei", "DejaVu Sans"]
d = pd.read_csv("source_data.csv")
configure_colors(d)
# ---- plot ----
fig = {call}{mods}
wh = export_size({size}, fig)
write_style(wh)
save_fig(fig, "figure", dir=".", size=wh, formats=("pdf", "png", "svg"))
s = lab_stats(fig)
if s is not None:
    s.to_json("stats.json", orient="records", force_ascii=False, double_precision=15)
    s.to_csv("statistics.csv", index=False)
import importlib.metadata
from pathlib import Path
Path("session-info.txt").write_text("\\n".join(f"{{package}}=={{importlib.metadata.version(package)}}" for package in ["labstyle-py", "pandas", "numpy", "scipy", "scikit-learn", "matplotlib"]), encoding="utf-8")
'''


def run_process(command, cwd, timeout=120):
    result = task_control.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                            env={**os.environ, "PYTHONUTF8": "1", "LC_ALL": "C"},
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    return result.returncode, result.stdout + result.stderr


class CodeExecutionError(ValueError):
    def __init__(self, message, diagnostic):
        super().__init__(message)
        self.diagnostic = diagnostic


def code_diagnostic(engine, log, folder):
    diagnostic = {"line": None, "column": None, "exact": False, "message": log[-1500:]}
    if engine == "r" and (folder / "diagnostic.json").exists():
        diagnostic.update(read_json(folder / "diagnostic.json"))
    if engine == "python":
        locations = re.findall(r'File "[^"\n]*figure\.py", line (\d+)', log)
        if locations:
            diagnostic.update(line=int(locations[-1]), exact=True)
    text = diagnostic.get("message", "")
    if re.search(r"unexpected|SyntaxError|IndentationError|unterminated", text, re.I):
        hint = "语法错误：检查标出的行附近是否缺少括号、引号、逗号，或缩进是否正确。"
    elif re.search(r"there is no package|ModuleNotFoundError|No module named", text, re.I):
        hint = "缺少依赖包：检查 library() 或 import 中的包名与当前环境。"
    elif re.search(r"object .*not found|NameError|could not find function", text, re.I):
        hint = "变量或函数未找到：检查名称拼写、定义顺序，以及是否加载了对应的包。"
    elif re.search(r"column|undefined columns|subscript out of bounds|KeyError", text, re.I):
        hint = "列名或索引可能不匹配：核对代码使用的列名与输入数据。"
    else:
        hint = "运行未完成：检查标出的代码位置与原始错误。上一张成功图片已保留。"
    return {**diagnostic, "hint": hint}


R_EDITOR_RUNNER = r'''# Preserve source locations for editor diagnostics.
tryCatch(withCallingHandlers(
  source("figure.R", keep.source=TRUE, encoding="UTF-8"),
  error=function(e) {
    message <- conditionMessage(e)
    location <- list(line=NULL,column=NULL,exact=FALSE,message=message)
    matched <- regmatches(message,regexec("figure\\.R:([0-9]+):([0-9]+)",message))[[1]]
    if(length(matched)==3) {
      location$line <- as.integer(matched[2]); location$column <- as.integer(matched[3]); location$exact <- TRUE
    } else {
      for(frame in rev(sys.frames())) {
        if(exists("srcrefs",frame,inherits=FALSE) && exists("i",frame,inherits=FALSE)) {
          refs <- get("srcrefs",frame); index <- get("i",frame)
          if(is.numeric(index) && length(index)==1 && index>0 && index<=length(refs)) {
            ref <- refs[[index]]
            if(!is.null(ref)) { location$line <- as.integer(ref[1]); location$column <- as.integer(ref[5]); break }
          }
        }
      }
    }
    try(jsonlite::write_json(location,"diagnostic.json",auto_unbox=TRUE,null="null"),silent=TRUE)
  }
),error=function(e) { cat(conditionMessage(e),"\n",file=stderr()); quit(save="no",status=1) })
'''


def default_figure_size(data, spec):
    """Readable default canvases; explicit user sizes and matrix layouts win."""
    if spec.size != 'template' or spec.width_mm is not None:
        return None
    sizes = {'roc': (3.8, 3.8), 'scatter': (4.6, 4.6), 'volcano': (4.6, 4.6),
             'ma': (4.8, 4.0), 'pca': (4.6, 4.2), 'embedding': (4.6, 4.2),
             'feature': (4.6, 4.2), 'network': (4.6, 4.6), 'pie': (4.2, 4.2),
             'histogram': (4.6, 3.6), 'gsea': (5.0, 3.8), 'custom': (4.6, 4.0),
             'km': (5.0, 4.6), 'paired': (3.8, 4.2)}
    if spec.chart in ('box', 'violin', 'rate_bar', 'composition', 'paired_delta', 'auc_bar'):
        role = {'composition': 'sample', 'paired_delta': 'pair'}.get(spec.chart, 'group')
        count = len(spec.columns['predictors']) if spec.chart == 'auc_bar' else data[spec.columns[role]].nunique()
        height = 4.2 if spec.chart in ('box', 'violin', 'paired_delta') else 3.8
        return [round(min(16, max(3.8, 1.5 + .6*count)), 2), height]
    # Heatmaps, enrichment, UpSet and forest plots already size to their labels/rows.
    return list(sizes[spec.chart]) if spec.chart in sizes else None


def render(dataset_id, spec):
    task_control.stage('检查数据与样本选择', 'inspect')
    d, metadata = load_dataset(dataset_id)
    resolved = resolve_features(d, spec, metadata)
    d, report = validate_spec(d, spec, metadata)
    if metadata.get('provenance'):
        report['data_provenance'] = metadata['provenance']
        report['notes'].append('本次输入来自已保存的处理副本；操作、来源与参数记录在 data_provenance，原始文件保留。')
        provenance = metadata['provenance']
        if provenance.get('operation') == 'analysis_scatter':
            config = provenance.get('analysis_settings', {})
            report['notes'].append('单图使用批量分析的固定输入；计算方式：' + config.get('mode', 'raw') + '。配对方向及排除记录见来源分析。')
            for method, values in provenance.get('reference_statistics', {}).items():
                report['notes'].append(f"来源批量 {method}：n={values.get('n')}，r={values.get('r')}，P={values.get('p')}，BH q={values.get('q')}；q 属于完整批量检验族。")

    key = uuid.uuid4().hex[:12]
    folder = STORE / "runs" / key
    folder.mkdir(parents=True)
    context = {name: metadata[name] for name in ('sample_metadata', 'expression_profile', 'annotation_columns', 'id_columns', 'provenance') if name in metadata}
    write_json(folder / 'analysis-context.json', context)
    if context:
        report['analysis_context'] = context
    colors = {}
    if spec.use_group_colors and spec.chart in preferences.COLOR_CHARTS and spec.columns.get("group"):
        colors = preferences.allocate_colors(STORE, d[spec.columns["group"]].dropna().unique())
    plot_settings = {"width_mm": spec.width_mm, "height_mm": spec.height_mm, "group_colors": colors,
                     "chart": spec.chart, "group_column": spec.columns.get("group", ""),
                     "default_size_in": default_figure_size(d, spec)}
    write_json(folder / "plot-settings.json", plot_settings)
    if spec.engine == 'r' and len(d.columns) > 300:
        write_json(folder / 'source-schema.json', {'columns': list(d.columns), 'rows': len(d),
            'types': ['logical' if pd.api.types.is_bool_dtype(dtype) else 'numeric' if pd.api.types.is_numeric_dtype(dtype) else 'character' for dtype in d.dtypes]})
        shutil.copyfile(ROOT / 'wide-table.R', folder / 'wide-table.R')
    write_json(folder / "analysis-settings.json", resolved.model_dump())
    d.to_csv(folder / "source_data.csv", index=False, encoding="utf-8")
    filename = "figure.R" if spec.engine == "r" else "figure.py"
    code = compile_r(spec, plot_settings['default_size_in']) if spec.engine == "r" else compile_python(spec, plot_settings['default_size_in'])
    if spec.engine == "r":
        shutil.copyfile(ROOT / "figure-style.R", folder / "figure-style.R")
    else:
        shutil.copyfile(ROOT / "figure_style.py", folder / "figure_style.py")
    (folder / filename).write_text(code, encoding="utf-8", newline="")
    manifest = {"id": key, "dataset_id": dataset_id, "dataset_name": metadata["filename"], "demo": metadata["demo"],
                "original_sha256": metadata["sha256"], "sheet": metadata["sheet"], "header": metadata["header"],
                "spec": spec.model_dump(), "report": report, "created": time.time(), "status": "running"}
    write_json(folder / "manifest.json", manifest)
    return execute_render(folder, manifest, code, filename)


def render_code(parent_id, code, figure_edits=None):
    """Run a user's editor buffer against a fresh copy of its input snapshot."""
    if not code.strip() or len(code) > 200000:
        raise ValueError("代码不能为空，最多支持 200,000 个字符")
    parent_folder = located("runs", parent_id)
    parent = read_json(parent_folder / "manifest.json")
    if parent.get("status") != "complete":
        raise ValueError("请从一个已成功生成的版本开始修改")
    if figure_edits is not None:
        from figure_edit import FigureEdits, edit_code
        edits = FigureEdits.model_validate(figure_edits)
        code = edit_code(code, parent['spec']['engine'], parent['spec']['chart'], edits)
        figure_edits = edits.model_dump()
    key = uuid.uuid4().hex[:12]
    folder = STORE / "runs" / key
    folder.mkdir(parents=True)
    shutil.copyfile(parent_folder / "source_data.csv", folder / "source_data.csv")
    for name in ("figure-style.R", "figure_style.py", "plot-settings.json", "analysis-settings.json", "source-schema.json", "wide-table.R", "analysis-context.json", "figure-edit.R", "figure_edit_helpers.py"):
        if (parent_folder / name).exists():
            shutil.copyfile(parent_folder / name, folder / name)
    if figure_edits is not None:
        helper = 'figure-edit.R' if parent['spec']['engine'] == 'r' else 'figure_edit_helpers.py'
        shutil.copyfile(ROOT / helper, folder / helper)
    filename = parent["code_file"]
    (folder / filename).write_text(code, encoding="utf-8", newline="")
    manifest = {k: copy.deepcopy(parent[k]) for k in ("dataset_id", "dataset_name", "demo", "original_sha256", "sheet", "header", "spec", "report")}
    manifest.update(id=key, created=time.time(), status="running", parent_run_id=parent_id, execution_mode="edited",
                    code_sha256=hashlib.sha256(code.encode("utf-8")).hexdigest())
    if figure_edits is not None or parent.get('figure_edits'):
        manifest['figure_edits'] = figure_edits if figure_edits is not None else parent['figure_edits']
    manifest["report"]["notes"].append("手动代码版本：记录数表示传入脚本的样本快照；代码内额外筛选或分析须核对实际统计输出。界面参数表示来源版本，不反向解析手改代码。")
    write_json(folder / "manifest.json", manifest)
    return execute_render(folder, manifest, code, filename)


def pdf_page_mm(path):
    """Read the page box, including Cairo's compressed object streams."""
    import importlib.util
    name = "aisi_pdf_text_audit"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, REPO / "skill/lab-figure/scripts/qa/audit_pdf_text.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    data = path.read_bytes()
    streams, _ = sys.modules[name].decoded_streams(data)
    for stream in [data, *streams]:
        box = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", stream)
        if box:
            x0,y0,x1,y1 = map(float, box.groups())
            return [(x1-x0)*25.4/72, (y1-y0)*25.4/72]
    return None


def execute_render(folder, manifest, code, filename):
    spec = PlotSpec.model_validate(manifest["spec"])
    command = [RSCRIPT, "--vanilla", filename] if spec.engine == "r" else [sys.executable, "-B", filename]
    if manifest.get("execution_mode") == "edited" and spec.engine == "r":
        (folder / "runner.R").write_text(R_EDITOR_RUNNER, encoding="utf-8", newline="")
        command = [RSCRIPT, "--vanilla", "runner.R"]
    try:
        task_control.stage('运行作图代码', 'render')
        rc, log = run_process(command, folder)
        (folder / "render.log").write_text(log, encoding="utf-8")
        if rc:
            raise CodeExecutionError("作图失败：" + log[-3500:], code_diagnostic(spec.engine, log, folder))
        missing = [name for name in ("figure.png", "figure.pdf", "figure.svg") if not (folder / name).exists() or (folder / name).stat().st_size < 20]
        if missing:
            raise ValueError("代码未生成所需文件：" + "、".join(missing) + "。请保留脚本中的导出语句。")
        qa = []
        task_control.stage('检查导出图片、字号与布局', 'audit')
        scripts = REPO / "skill/lab-figure/scripts/qa"
        for label, script, args in [("字号", "audit_pdf_text.py", ["--min-pt", "5"]),
                                     ("碰撞", "audit_figure_collisions.py", ["--json-out", "collision-audit.json"])]:
            qrc, qlog = run_process([sys.executable, "-I", str(scripts / script), "figure.pdf", *args], folder, 45)
            verdict = re.findall(r"^verdict:\s*(.+)$", qlog, re.M)
            qa.append({"name": label, "verdict": verdict[-1].strip() if verdict else "ERROR", "code": qrc, "log": qlog})
        if (folder / "plot-settings.json").exists():
            settings = read_json(folder / "plot-settings.json")
            dimensions = pdf_page_mm(folder / "figure.pdf")
            if dimensions:
                mismatch = (settings.get("width_mm") is not None and abs(dimensions[0]-settings["width_mm"])>.36) or (settings.get("height_mm") is not None and abs(dimensions[1]-settings["height_mm"])>.36)
                qa.append({"name":"尺寸", "verdict":"REVIEW REQUIRED" if mismatch else "PASS", "code":int(mismatch), "log":f"最终 PDF：{dimensions[0]:.2f} × {dimensions[1]:.2f} mm。\n目标宽度：{settings.get('width_mm') or '随模板 / 代码'} mm；高度：{settings.get('height_mm') or '保持比例 / 随模板'}。\nPDF 设备可能按整点取整，尺寸检查容许 0.36 mm 差异。字号与碰撞检查基于最终 PDF，不缩小字体来适配画布。"})
            else:
                qa.append({"name":"尺寸", "verdict":"ERROR", "code":1, "log":"未能读取 PDF 页面尺寸，请检查最终文件。"})
        task_control.check()
        manifest.update({"status": "complete", "stats": read_json(folder / "stats.json") if (folder / "stats.json").exists() else [], "qa": qa,
                         "code": code, "code_file": filename, "runtime_seconds": round(time.time() - manifest["created"], 2)})
        if (folder / "figure-style.json").exists():
            manifest["figure_style"] = read_json(folder / "figure-style.json")
        if (folder / 'figure-edit-info.json').exists():
            manifest['figure_edit_info'] = read_json(folder / 'figure-edit-info.json')
        if (folder / "plot-settings.json").exists():
            manifest["plot_settings"] = read_json(folder / "plot-settings.json")
        write_json(folder / "manifest.json", manifest)
        build_bundle(folder)
        return manifest
    except Exception as exc:
        manifest.update(status="cancelled" if isinstance(exc, task_control.Cancelled) else "error", error=str(exc))
        if isinstance(exc, CodeExecutionError):
            manifest["diagnostic"] = exc.diagnostic
        write_json(folder / "manifest.json", manifest)
        raise


def list_records(kind):
    root = STORE / kind
    results = []
    if root.exists():
        for path in root.glob("*/" + ("metadata.json" if kind == "datasets" else "manifest.json")):
            try:
                m = read_json(path)
                if kind == "datasets":
                    results.append(m)
                elif m["status"] == "complete":
                    results.append({**{k: m[k] for k in ("id", "dataset_id", "dataset_name", "created", "spec", "demo")}, "execution_mode": m.get("execution_mode", "template")})
            except (ValueError, OSError, KeyError):
                continue
    return sorted(results, key=lambda m: m["created"], reverse=True)[:100]
