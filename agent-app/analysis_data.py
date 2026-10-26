"""Exact sample annotation joins and explicitly configured expression preparation.

Every write creates a new immutable dataset. QC never imputes, normalizes, or
attributes sample anomalies; CPM and TPM remain distinct declared inputs.
"""
from __future__ import annotations

import copy
import json
import re

import numpy as np
import pandas as pd

import core
import task_control


PREVIEW_NAMES = 30
UNITS = {'unknown', 'counts', 'cpm', 'tpm', 'log_expression'}


def _load_ids(key, column):
    data, meta = core.load_dataset(key, string_columns=[column])
    if column not in data.columns:
        raise ValueError(f'样本标识列 {column} 不存在')
    return data, meta


def _preview(data):
    return json.loads(data.iloc[:8, :24].to_json(orient='records'))


def _id_issues(ids, name):
    issues = []
    if ids.isna().any() or ids.astype(str).str.strip().eq('').any():
        issues.append(f'{name}的样本标识有空值；请明确补全后重试')
    if ids.duplicated().any():
        issues.append(f'{name}的样本标识重复；每个样本必须唯一')
    return issues


def _metadata_source(metadata_id):
    """Inspect lexical tokens before choosing any annotation column's dtype."""
    normal, meta = core.load_dataset(metadata_id)
    folder = core.located('datasets', metadata_id)
    raw, _, _ = core.read_table(folder / meta['original'], meta.get('sheet'), meta.get('header', 1),
                                 string_columns=list(normal.columns))
    roles = {'sample','patient','donor','pair','condition','group','batch','cluster','id',
             'subject','individual','participant'}
    chinese_roles = ('样本','患者','病人','供者','供体','配对','条件','组','批次','聚类','簇','编号','标识','受试者','个体')
    suggested = []
    for column in normal:
        name = re.sub(r'([a-z])([A-Z])', r'\1_\2', column).casefold()
        tokens = set(re.findall(r'[a-z]+', name))
        compact = re.sub(r'[^a-z]', '', name)
        role_like = bool(tokens & roles) or any(term in column for term in chinese_roles)
        role_like |= any(compact == role + 'id' for role in roles)
        leading_zero = raw[column].astype(str).str.strip().str.fullmatch(r'[+-]?0\d+', na=False).any()
        if not pd.api.types.is_numeric_dtype(normal[column]) or role_like or leading_zero:
            suggested.append(column)
    return normal, raw, meta, suggested


def metadata_columns(metadata_id):
    normal, raw, _, suggested = _metadata_source(metadata_id)
    columns = core.summarize(normal)['columns']
    for descriptor in columns:
        name = descriptor['name']
        lexical = raw[name].drop_duplicates().astype(str).tolist()[:16]
        descriptor['lexical_values'] = lexical
        descriptor['values'] = lexical
        if name in suggested:
            descriptor.update(type='categorical', min=None, max=None)
    return {'columns':columns, 'text_columns':suggested}


def _metadata_alignment(dataset_id, metadata_id, sample_column, metadata_sample_column,
                        prefix='', allow_extra=False, rows_are_samples=False, text_columns=None):
    task_control.check()
    data, parent = _load_ids(dataset_id, sample_column)
    normal, _, source, suggested = _metadata_source(metadata_id)
    selected_text = suggested if text_columns is None else text_columns
    if (not isinstance(selected_text, list) or any(not isinstance(c, str) or c not in normal for c in selected_text)
            or len(set(selected_text)) != len(selected_text)):
        raise ValueError('文本注释列必须是存在且不重复的列名列表')
    if metadata_sample_column not in normal:
        raise ValueError(f'样本标识列 {metadata_sample_column} 不存在')
    source_folder = core.located('datasets', metadata_id)
    annotation, _, _ = core.read_table(source_folder / source['original'], source.get('sheet'), source.get('header', 1),
                                      string_columns=list(dict.fromkeys([metadata_sample_column, *selected_text])))
    issues = []
    if not rows_are_samples:
        issues.append('请先确认矩阵方向：每行一个样本；基因在行时先转置')
    issues.extend(_id_issues(data[sample_column], '表达表'))
    issues.extend(_id_issues(annotation[metadata_sample_column], '注释表'))
    ids, annotation_ids = data[sample_column], annotation[metadata_sample_column]
    missing = list(dict.fromkeys(ids.loc[~ids.isin(annotation_ids)].dropna().tolist()))
    extra = list(dict.fromkeys(annotation_ids.loc[~annotation_ids.isin(ids)].dropna().tolist()))
    if missing:
        issues.append(f'有 {len(missing)} 个样本缺少注释；不会删除或填补')
    if extra and not allow_extra:
        issues.append(f'注释表多出 {len(extra)} 个样本；需要明确允许额外样本')
    names = [c for c in annotation.columns if c != metadata_sample_column]
    columns = [prefix + c for c in names]
    collisions = [c for c in columns if c in data.columns]
    if collisions:
        issues.append('注释列名冲突，请明确设置不同前缀：' + '、'.join(collisions[:PREVIEW_NAMES]))
    core.check_table_size(len(data), len(data.columns) + len(columns))
    joined = None
    if not issues:
        # Reindex preserves expression order; no fuzzy/case-insensitive ID matching.
        aligned = annotation.set_index(metadata_sample_column).reindex(ids)[names].reset_index(drop=True)
        aligned.columns = columns
        joined = pd.concat([data.reset_index(drop=True), aligned], axis=1)
    report = {'valid':not issues, 'issues':issues, 'sample_count':len(data),
              'metadata_sample_count':len(annotation), 'matched_count':int(ids.isin(annotation_ids).sum()),
              'missing_count':len(missing), 'extra_count':len(extra),
              'missing_ids':missing[:PREVIEW_NAMES], 'extra_ids':extra[:PREVIEW_NAMES],
              'annotation_count':len(columns), 'annotation_columns':columns[:200],
              'text_columns':list(selected_text),
              'preview':_preview(joined) if joined is not None else [],
              'preview_limit':PREVIEW_NAMES}
    return report, joined, parent, source, columns


def preview_metadata(dataset_id, metadata_id, sample_column, metadata_sample_column,
                     prefix='', allow_extra=False, rows_are_samples=False, text_columns=None):
    return _metadata_alignment(dataset_id, metadata_id, sample_column, metadata_sample_column,
                               prefix, allow_extra, rows_are_samples, text_columns)[0]


def _save_copy(data, parent, prefix, updates):
    task_control.check()
    result = core.store_dataset(data.to_csv(index=False).encode('utf-8'),
                                prefix + parent['filename'].rsplit('.', 1)[0] + '.csv', parent.get('demo', False))
    for key in ('annotation_columns', 'sample_metadata', 'expression_profile', 'id_columns'):
        if key in parent:
            result[key] = copy.deepcopy(parent[key])
    result.update(updates)
    result['summary'] = core.summarize(data)
    result['recognition'] = core.recognize_frame(data)
    core.write_json(core.located('datasets', result['id']) / 'metadata.json', result)
    return result


def attach_metadata(dataset_id, metadata_id, sample_column, metadata_sample_column,
                    prefix='', allow_extra=False, rows_are_samples=False, text_columns=None):
    report, joined, parent, source, columns = _metadata_alignment(
        dataset_id, metadata_id, sample_column, metadata_sample_column, prefix, allow_extra, rows_are_samples, text_columns)
    if not report['valid']:
        raise ValueError('；'.join(report['issues']))
    settings = {'sample_column':sample_column, 'metadata_sample_column':metadata_sample_column,
                'prefix':prefix, 'allow_extra':allow_extra, 'rows_are_samples':rows_are_samples,
                'text_columns':report['text_columns']}
    provenance = {'operation':'attach_metadata', 'parent_dataset_id':dataset_id,
                  'parent_sha256':parent['sha256'], 'metadata_dataset_id':metadata_id,
                  'metadata_sha256':source['sha256'], 'settings':settings,
                  'parent_provenance':copy.deepcopy(parent.get('provenance'))}
    return _save_copy(joined, parent, 'annotated_', {
        'annotation_columns':list(dict.fromkeys([*parent.get('annotation_columns', []), *columns])),
        'id_columns':list(dict.fromkeys([*parent.get('id_columns', []), sample_column,
                           *[prefix+c for c in report['text_columns'] if c != metadata_sample_column]])),
        'sample_metadata':{**provenance, **settings,
                           'previous':copy.deepcopy(parent.get('sample_metadata'))},
        'provenance':provenance})


def _settings(settings):
    if not isinstance(settings, dict):
        raise ValueError('表达检查设置必须为对象')
    out = {'label':'', 'units':'unknown', 'feature_columns':[], 'all_numeric':False,
           'exvivo':False, 'transform':'none', 'drop_zero_variance':False,
           'filter_low':False, 'min_expression':0.0, 'min_samples':1, 'rows_are_samples':False,
           **copy.deepcopy(settings)}
    if out['units'] not in UNITS or out['transform'] not in {'none', 'log2p1'}:
        raise ValueError('请选择已支持的表达单位及变换')
    if not out['rows_are_samples']:
        raise ValueError('请先确认矩阵方向：每行一个样本、每列一个特征')
    if not isinstance(out['feature_columns'], list) or any(not isinstance(c, str) for c in out['feature_columns']):
        raise ValueError('特征列必须为列名列表')
    if len(set(out['feature_columns'])) != len(out['feature_columns']):
        raise ValueError('特征列不能重复')
    try:
        threshold = float(out['min_expression'])
    except (TypeError, ValueError):
        raise ValueError('低表达阈值必须为有限数值') from None
    if not np.isfinite(threshold):
        raise ValueError('低表达阈值必须为有限数值')
    n = out['min_samples']
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError('低表达最小样本数必须为正整数')
    out['min_expression'] = threshold
    return out


def _expression(dataset_id, settings):
    task_control.check()
    config = _settings(settings)
    label = config['label']
    data, parent = _load_ids(dataset_id, label)
    problems = _id_issues(data[label], '表达表')
    if problems:
        raise ValueError('；'.join(problems))
    mask = core.exclusion_mask(data)
    if mask.any() and not config['exvivo']:
        raise ValueError('数据含 HNSCC3 已确认异常样本。ex vivo 共培养分析请明确启用 ex vivo 排除')
    excluded = data.loc[mask, label].astype(str).tolist() if config['exvivo'] else []
    if config['exvivo']:
        data = data.loc[~mask].reset_index(drop=True)
    if not len(data):
        raise ValueError('排除后没有可用样本')
    numeric = list(data.select_dtypes(include=['number']).columns)
    annotation = set(parent.get('annotation_columns', []))
    features = ([c for c in numeric if c != label and c not in annotation]
                if config['all_numeric'] else config['feature_columns'])
    if not features or label in features or any(c not in numeric or c in annotation for c in features):
        raise ValueError('请选择表达数值特征；样本标识和已连接的注释列不能作为表达特征')
    values = data[features].to_numpy(dtype=float)
    finite = np.isfinite(values)
    count = finite.sum(axis=0)
    minima = np.where(finite, values, np.inf).min(axis=0)
    maxima = np.where(finite, values, -np.inf).max(axis=0)
    zero = (count > 0) & (minima == maxima)
    low = (finite & (values > config['min_expression'])).sum(axis=0) < config['min_samples']
    observed = values[finite]
    counts_valid = (bool(np.all(observed >= 0) and np.all(observed == np.floor(observed)) and not np.isinf(values).any())
                    if config['units'] == 'counts' else None)
    unit_valid = counts_valid
    if config['units'] in {'cpm', 'tpm'}:
        unit_valid = bool(np.all(observed >= 0) and not np.isinf(values).any())
    elif config['units'] == 'log_expression':
        # Log expression may legitimately contain negative values; it is not raw abundance.
        unit_valid = None
    notes = ['仅检查明确选择的特征；未自动标准化、筛选或插补。',
             '低表达定义：表达值严格大于阈值的样本数小于最小样本数。']
    if config['exvivo']:
        notes.append('按用户确认的清单先排除样本，再选择特征及计算 QC；保留 HNSCC3_LD。未进行 CPM/TPM 替换或混样归因。')
    if np.isnan(values).any():
        notes.append('缺失值仅报告并保留，不删除样本或填补；过滤时缺失值不计为超过阈值。')
    if config['units'] == 'unknown':
        notes.append('表达单位未知；不能执行 log2(x+1) 变换。')
    if counts_valid is False:
        notes.append('counts 单位验证失败：观测表达必须是非负整数，且不能包含无穷值；缺失值单独报告。')
    elif unit_valid is False:
        notes.append(f"{config['units'].upper()} 单位验证失败：观测表达必须为非负数，且不能包含无穷值；缺失值单独报告。")
    report = {'sample_count':len(data), 'samples':len(data), 'feature_count':len(features),
              'units':config['units'], 'label':label,
              'zero_variance_count':int(zero.sum()), 'low_expression_count':int(low.sum()),
              'zero_variance_features':[c for c, yes in zip(features, zero) if yes][:PREVIEW_NAMES],
              'low_expression_features':[c for c, yes in zip(features, low) if yes][:PREVIEW_NAMES],
              'missing':int(np.isnan(values).sum()), 'nonfinite':int(np.isinf(values).sum()),
              'negative':int((values < 0).sum()), 'counts_valid':counts_valid, 'unit_valid':unit_valid,
              'min':float(observed.min()) if observed.size else None,
              'max':float(observed.max()) if observed.size else None,
              'excluded_rows':len(excluded), 'excluded_samples':excluded[:PREVIEW_NAMES],
              'notes':notes, 'feature_preview':features[:PREVIEW_NAMES],
              'preview':_preview(data.loc[:, [label, *features[:23]]]),
              'min_expression':config['min_expression'], 'min_samples':config['min_samples']}
    if config['exvivo']:
        _, source = core.exclusions()
        report['exclusion_source'] = str(source)
    return data, parent, config, features, values, zero, low, report


def inspect_expression(dataset_id, settings):
    return _expression(dataset_id, settings)[-1]


def prepare_expression(dataset_id, settings):
    data, parent, config, features, values, zero, low, report = _expression(dataset_id, settings)
    previous = parent.get('expression_profile', {})
    if previous.get('units', 'unknown') != 'unknown' and config['units'] != previous['units']:
        raise ValueError('输入已记录表达单位；不能通过重新声明将 CPM、TPM 或 log 表达互换')
    if report['counts_valid'] is False:
        raise ValueError('声明为 counts 的表达必须是非负整数，且不能包含无穷值')
    if config['units'] in {'cpm', 'tpm'} and report['unit_valid'] is False:
        raise ValueError(f"声明为 {config['units'].upper()} 的表达必须为非负数，且不能包含无穷值")
    if config['transform'] == 'log2p1':
        if config['units'] not in {'counts', 'cpm', 'tpm'} or previous.get('units') == 'log_expression':
            raise ValueError('log2(x+1) 仅用于明确声明的原始 counts/CPM/TPM；不能重复变换 log 表达')
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError('log2(x+1) 需要非负且全部有限的表达值；不会删除或插补缺失值')
    keep = np.ones(len(features), dtype=bool)
    if config['drop_zero_variance']:
        keep &= ~zero
    if config['filter_low']:
        keep &= ~low
    retained = [c for c, yes in zip(features, keep) if yes]
    if not retained:
        raise ValueError('明确筛选后没有剩余表达特征，请调整设置')
    numeric = set(data.select_dtypes(include=['number']).columns)
    annotations = set(parent.get('annotation_columns', []))
    label = config['label']
    # Unselected numeric genes must not quietly survive as apparent annotations.
    columns = [c for c in data if c == label or c in retained or c in annotations or c not in numeric]
    result = data.loc[:, columns].copy()
    if config['transform'] == 'log2p1':
        transformed = pd.DataFrame(np.log2(values[:, keep] + 1), columns=retained, index=result.index)
        result = pd.concat([result.drop(columns=retained), transformed], axis=1).loc[:, columns]
    profile = {**copy.deepcopy(previous), 'label':label,
               'rows_are_samples':config['rows_are_samples'],
               'units':'log_expression' if config['transform'] == 'log2p1' else config['units'],
               'source_units':previous.get('source_units', config['units']),
               'feature_columns':retained, 'settings':config, 'qc':report,
               'sample_count':len(result), 'feature_count':len(retained)}
    provenance = {'operation':'prepare_expression', 'parent_dataset_id':dataset_id,
                  'parent_sha256':parent['sha256'], 'settings':config,
                  'parent_provenance':copy.deepcopy(parent.get('provenance')),
                  'excluded_rows':report['excluded_rows'],
                  'excluded_samples':report['excluded_samples'],
                  'filtered_feature_count':len(features)-len(retained)}
    return _save_copy(result, parent, 'prepared_', {'expression_profile':profile,
                      'id_columns':list(dict.fromkeys([*parent.get('id_columns', []), label])),
                      'provenance':provenance})
