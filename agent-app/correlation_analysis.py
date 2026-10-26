"""Auditable batch SCC/PCC and paired signed-rank analyses on sample rows.

Input datasets are immutable. Exclusions precede every transformation. The bundle
recomputes statistics from the exact frozen processed matrix, without app services.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
import time
import uuid
import warnings
import zipfile

import numpy as np
import pandas as pd
import scipy
from scipy import stats

import core
import task_control


DEFAULTS = dict(label='', target='', features=[], all_numeric=False,
                rows_are_samples=False, mode='raw', center_by='', pair='',
                condition='', reference='', comparison='', drop_incomplete_pairs=False,
                missing_policy='error', exvivo=False)


def _bh(values):
    """BH within one method's finite-P family, retaining invalid rows as null."""
    p = np.asarray(values, dtype=float)
    result = np.full(len(p), np.nan)
    indices = np.flatnonzero(np.isfinite(p))
    order = indices[np.argsort(p[indices], kind='stable')]
    if len(order):
        adjusted = p[order] * len(order) / np.arange(1, len(order)+1)
        result[order] = np.minimum(1, np.minimum.accumulate(adjusted[::-1])[::-1])
    return result


def _correlations(frame, features, target, method, check=None):
    rows = []
    y_all = frame[target].to_numpy(dtype=float)
    function = stats.spearmanr if method == 'spearman' else stats.pearsonr
    for i, feature in enumerate(features):
        if check and i % 100 == 0:
            check()
        x_all = frame[feature].to_numpy(dtype=float)
        valid = np.isfinite(x_all) & np.isfinite(y_all)
        x, y = x_all[valid], y_all[valid]
        row = dict(feature=feature, n=int(valid.sum()), r=None, p=None, q=None, status='ok')
        if len(x) < 3:
            row['status'] = 'insufficient_n'
        elif np.ptp(x) == 0:
            row['status'] = 'constant_feature'
        elif np.ptp(y) == 0:
            row['status'] = 'constant_target'
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', stats.NearConstantInputWarning)
                result = function(x, y)
            if np.isfinite(result.statistic) and np.isfinite(result.pvalue):
                row.update(r=float(result.statistic), p=float(result.pvalue))
            else:
                row['status'] = 'nonfinite_result'
        rows.append(row)
    result = pd.DataFrame(rows)
    result['q'] = _bh(result['p'])
    result = result.sort_values(['p', 'feature'], kind='stable', na_position='last').reset_index(drop=True)
    result.insert(0, 'rank', [i+1 if row.status == 'ok' else None for i, row in result.iterrows()])
    return result


def _paired_statistics(frame, features, check=None):
    rows = []
    for i, feature in enumerate(features):
        if check and i % 100 == 0:
            check()
        values = frame[feature].dropna().to_numpy(dtype=float)
        n = len(values)
        row = dict(feature=feature, n=n, statistic=None, p=None, q=None,
                   mean_delta=float(np.mean(values)) if n else None,
                   median_delta=float(np.median(values)) if n else None,
                   rank_biserial=None, status='ok')
        if n < 1:
            row['status'] = 'insufficient_n'
        elif np.all(values == 0):
            row.update(statistic=0., p=1., rank_biserial=0., status='all_zero')
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                result = stats.wilcoxon(values, zero_method='wilcox', correction=False,
                                        alternative='two-sided', method='approx')
            nonzero = values[values != 0]
            ranks = stats.rankdata(np.abs(nonzero))
            effect = float(np.sum(ranks*np.sign(nonzero))/np.sum(ranks))
            if np.isfinite(result.pvalue):
                row.update(statistic=float(result.statistic), p=float(result.pvalue), rank_biserial=effect)
            else:
                row['status'] = 'nonfinite_result'
        rows.append(row)
    result = pd.DataFrame(rows)
    result['q'] = _bh(result['p'])
    result = result.sort_values(['p', 'feature'], kind='stable', na_position='last').reset_index(drop=True)
    result.insert(0, 'rank', [i+1 if pd.notna(row.p) else None for i, row in result.iterrows()])
    return result


def _records(frame):
    return json.loads(frame.to_json(orient='records'))


def _read_results(path):
    numeric = ['rank','n','r','p','q','statistic','mean_delta','median_delta','rank_biserial']
    return pd.read_csv(path, keep_default_na=False, dtype={'feature':str},
                       na_values={name:[''] for name in numeric})


def _identifier(frame, column, *, unique=False):
    if not column or column not in frame:
        raise ValueError('请选择存在的样本标识/分组/配对列')
    values = frame[column]
    if values.isna().any() or values.astype(str).str.strip().eq('').any():
        raise ValueError(f'{column} 标识存在缺失或空值')
    if unique and values.astype(str).duplicated().any():
        raise ValueError(f'{column} 样本标识重复')


def _features(frame, metadata, settings):
    protected = {settings[k] for k in ('label', 'target', 'pair', 'condition', 'center_by') if settings[k]}
    explicit = settings['features']
    if settings['all_numeric']:
        excluded = protected | set(metadata.get('annotation_columns', [])) | set(metadata.get('id_columns', []))
        profile = metadata.get('expression_profile') or {}
        declared = profile.get('feature_columns') or profile.get('features')
        features = [c for c in frame.select_dtypes(include='number').columns
                    if c not in excluded and (not declared or c in declared)]
    else:
        features = list(explicit)
    if not features or len(set(features)) != len(features):
        raise ValueError('至少选择一个唯一的数值特征')
    if protected.intersection(features) or any(c not in frame for c in features):
        raise ValueError('特征必须存在，且不能包含样本、目标、分组或配对标识列')
    if any(not pd.api.types.is_numeric_dtype(frame[c]) or pd.api.types.is_bool_dtype(frame[c]) for c in features):
        raise ValueError('特征必须为数值列')
    return features


def _validate_values(frame, numeric, missing_policy):
    matrix = frame[numeric].to_numpy(dtype=float)
    if np.isinf(matrix).any():
        raise ValueError('分析数值含无穷值，请明确处理')
    if missing_policy == 'error' and np.isnan(matrix).any():
        raise ValueError('分析数值含缺失值；仅明确选择 pairwise 才按特征删除缺失观测')


def _prepare(data, metadata, settings):
    _identifier(data, settings['label'], unique=True)
    target = settings['target']
    if target == settings['label']:
        raise ValueError('目标数值列和样本标识列须不同')
    if target not in data or not pd.api.types.is_numeric_dtype(data[target]) or pd.api.types.is_bool_dtype(data[target]):
        raise ValueError('目标必须为数值列')
    excluded = core.exclusion_mask(data)
    if excluded.any() and not settings['exvivo']:
        raise ValueError('检测到已确认排除的 ex vivo 样本，请启用 ex vivo 排除')
    frame = data.loc[~excluded].copy() if settings['exvivo'] else data.copy()
    if not len(frame):
        raise ValueError('排除后没有可分析样本')
    features = _features(frame, metadata, settings)
    numeric = [target] + features
    if settings['mode'] != 'paired_delta':
        _validate_values(frame, numeric, settings['missing_policy'])
    report = dict(input_samples=len(data), excluded_samples=int(excluded.sum()) if settings['exvivo'] else 0,
                  retained_samples=len(frame), analysis_samples=len(frame), pair_count=None,
                  pairs_discarded=0, filtered_condition_rows=0, missing_policy=settings['missing_policy'],
                  notes=[], exclusion_before_preprocessing=True,
                  exclusion_provenance=copy.deepcopy(metadata.get('exclusion_provenance',
                    metadata.get('exclusion', {'parent_provenance':metadata.get('provenance', {}),
                                             'expression_qc':metadata.get('expression_profile', {}).get('qc', {})}))))
    if settings['exvivo']:
        _, exclusion_source = core.exclusions()
        report['exclusion_source'] = str(exclusion_source)
        report['exclusion_sha256'] = hashlib.sha256(exclusion_source.read_bytes()).hexdigest()
        report['excluded_labels'] = data.loc[excluded, settings['label']].astype(str).tolist()
        report['notes'].append('按用户确认的排除清单先排除样本，再计算中心化、配对差值及全部统计；保留 LD。')
    if settings['mode'] == 'centered':
        group = settings['center_by']
        _identifier(frame, group)
        frame[numeric] = frame[numeric] - frame.groupby(group, sort=False)[numeric].transform('mean')
        report['group_count'] = int(frame[group].nunique())
        report['notes'].append('特征和目标均在排除后按组减去各自有效观测均值；中心化相关性仅为探索性，未拟合重复测量模型。')
    elif settings['mode'] == 'paired_delta':
        pair, condition = settings['pair'], settings['condition']
        _identifier(frame, pair)
        _identifier(frame, condition)
        if pair == condition or pair in numeric or condition in numeric:
            raise ValueError('配对 ID、条件列和数值列须不同')
        reference, comparison = str(settings['reference']), str(settings['comparison'])
        if not reference or not comparison or reference == comparison:
            raise ValueError('请明确两个不同的参考及比较条件')
        frame[condition] = frame[condition].astype(str)
        selected = frame[condition].isin([reference, comparison])
        report['filtered_condition_rows'] = int((~selected).sum())
        frame = frame.loc[selected].copy()
        if frame.duplicated([pair, condition]).any():
            raise ValueError('存在重复的配对 ID × 条件记录')
        counts = frame.groupby(pair, sort=False)[condition].nunique()
        complete = counts[counts == 2].index
        incomplete = counts[counts != 2].index
        if len(incomplete) and not settings['drop_incomplete_pairs']:
            raise ValueError('存在不完整配对；请明确选择删除不完整配对')
        if not len(complete):
            raise ValueError('没有完整配对')
        report['pairs_discarded'] = len(incomplete)
        report['discarded_pair_ids'] = [str(v) for v in incomplete]
        frame = frame.loc[frame[pair].isin(complete)].copy()
        _validate_values(frame, numeric, settings['missing_policy'])
        before = frame.loc[frame[condition] == reference].set_index(pair).reindex(complete)
        after = frame.loc[frame[condition] == comparison].set_index(pair).reindex(complete)
        frame = (after[numeric] - before[numeric]).reset_index()
        # A collision-free snapshot ID column makes the paired unit explicit.
        snapshot_label = settings['label']
        if snapshot_label != pair:
            frame.insert(0, snapshot_label, frame[pair].astype(str))
        report.update(pair_count=len(complete), analysis_samples=len(complete),
                      pair_direction=f'{comparison} - {reference}', reference=reference, comparison=comparison)
        report['notes'].append(f'配对差值为 {comparison} − {reference}；以配对 ID 为统计单位；仅使用指定两条件，其他条件行数已记录。')
        report['wilcoxon'] = dict(method='approx', zero_method='wilcox', correction=False, alternative='two-sided',
                                 effect='rank_biserial = sum(sign(delta) * rank(abs(nonzero delta))) / sum(ranks)',
                                 all_zero_p=1, minimum_n=1)
    if np.isinf(frame[numeric].to_numpy(dtype=float)).any():
        raise ValueError('预处理产生无穷值，请检查数值范围')
    report['notes'].append('结果按原始 P 升序、特征名排序；无效特征排在末尾。')
    report['notes'].append('SCC 与 PCC 各自对有限 P 值独立作 BH 校正；所有所选特征均导出状态和有效 n。相关性在 n < 3 时不计算检验；配对 Wilcoxon 独立记录有效配对数。')
    report['notes'].append('输入单位按原声明保留；未把 CPM 视为 TPM，未推断混样、样本交换或责任来源。')
    keep = list(dict.fromkeys([settings['label']] + ([settings['pair']] if settings['mode']=='paired_delta' else []) + numeric))
    return frame[keep].reset_index(drop=True), features, report


def _reproduction_script():
    imports = 'from pathlib import Path\nimport json\nimport warnings\nimport numpy as np\nimport pandas as pd\nfrom scipy import stats\n\n'
    kernels = '\n\n'.join(inspect.getsource(f) for f in (_bh, _correlations, _paired_statistics))
    execute = '''
folder = Path(__file__).resolve().parent
settings = json.loads((folder/'analysis-settings.json').read_text(encoding='utf-8'))
frame = pd.read_csv(folder/'analysis_input.csv', keep_default_na=False,
                    na_values={c:[''] for c in [settings['target']]+settings['features']})
for method in ('spearman', 'pearson'):
    _correlations(frame, settings['features'], settings['target'], method).to_csv(folder/(method+'.csv'), index=False)
if settings['mode'] == 'paired_delta':
    _paired_statistics(frame, settings['features']).to_csv(folder/'paired_statistics.csv', index=False)
'''
    return '# Recompute statistics from frozen, already processed input.\n# See manifest.json for original sources, exclusions, units and transformation.\n' + imports + kernels + execute


def run(dataset_id, settings):
    task_control.stage('核查样本、特征与统计规则', 'analysis_validate')
    settings = dict(DEFAULTS, **copy.deepcopy(settings))
    if not settings['rows_are_samples']:
        raise ValueError('请确认每行为样本；基因行矩阵须先转置')
    if settings['mode'] not in ('raw', 'centered', 'paired_delta'):
        raise ValueError('无效分析模式')
    if settings['missing_policy'] not in ('error', 'pairwise'):
        raise ValueError('缺失值规则必须为 error 或 pairwise')
    if settings['mode'] != 'centered':
        settings['center_by'] = ''
    if settings['mode'] != 'paired_delta':
        for key in ('pair', 'condition', 'reference', 'comparison'):
            settings[key] = ''
        settings['drop_incomplete_pairs'] = False
    data, metadata = core.load_dataset(dataset_id)
    # Raw uploads have no declared id_columns yet. Preserve the request's lexical
    # identifiers before validating uniqueness, grouping or constructing pairs.
    identifiers = list(dict.fromkeys(list(metadata.get('id_columns', [])) +
                        [settings[key] for key in ('label','pair','condition','center_by') if settings[key]]))
    numeric_roles = {settings['target']} | set(settings['features'])
    if numeric_roles.intersection(identifiers):
        raise ValueError('目标/特征数值列不能同时作为样本、分组或配对标识列')
    source = core.located('datasets', dataset_id)/metadata['original']
    data, _, _ = core.read_table(source, metadata.get('sheet'), metadata.get('header', 1),
                                 string_columns=identifiers)
    frame, features, report = _prepare(data, metadata, settings)
    settings['features'] = features
    task_control.stage(f'计算 {len(features)} 个特征的 SCC / PCC', 'analysis_statistics')
    tables = {method: _correlations(frame, features, settings['target'], method, task_control.check)
              for method in ('spearman', 'pearson')}
    if settings['mode'] == 'paired_delta':
        tables['paired_statistics'] = _paired_statistics(frame, features, task_control.check)
    task_control.check()
    key = uuid.uuid4().hex[:12]
    folder = core.STORE/'analyses'/key
    folder.mkdir(parents=True)
    try:
        frame.to_csv(folder/'analysis_input.csv', index=False)
        core.write_json(folder/'analysis-settings.json', settings)
        for name, table in tables.items():
            task_control.check()
            table.to_csv(folder/(name+'.csv'), index=False)
        report.update(parent_sha256=metadata.get('sha256'), parent_dataset_id=dataset_id,
                      parent_filename=metadata.get('filename'), parent_provenance=copy.deepcopy(metadata.get('provenance', {})),
                      expression_profile=copy.deepcopy(metadata.get('expression_profile', {'units':'unknown'})),
                      feature_count=len(features), correction='Benjamini-Hochberg; separate finite-P family for each method',
                      valid_tests={name:int(table['p'].notna().sum()) for name, table in tables.items()},
                      input_sha256=hashlib.sha256((folder/'analysis_input.csv').read_bytes()).hexdigest(),
                      reproduction_scope='Statistics rerun on frozen processed analysis_input.csv; original sources and preprocessing recorded, original files unchanged.',
                      versions=dict(numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__))
        (folder/'reproduce.py').write_text(_reproduction_script(), encoding='utf-8')
        files = ['analysis_input.csv','analysis-settings.json','reproduce.py','manifest.json','reproduce.zip'] + [name+'.csv' for name in tables]
        result = dict(id=key, dataset_id=dataset_id, status='complete', created=time.time(), settings=settings,
                      feature_count=len(features), result_count=len(features), demo=bool(metadata.get('demo')), report=report, files=files,
                      previews={name:_records(table.head(20)) for name, table in tables.items()})
        core.write_json(folder/'manifest.json', result)
        task_control.stage('保存完整结果与复现文件', 'analysis_save')
        with zipfile.ZipFile(folder/'reproduce.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
            for name in files:
                if name != 'reproduce.zip':
                    task_control.check()
                    bundle.write(folder/name, name)
        task_control.check()
        return result
    except BaseException:
        # An unfinished analysis must never appear as a successful historical run.
        (folder/'manifest.json').unlink(missing_ok=True)
        raise


def get_results(analysis_id, method, query='', offset=0, limit=100):
    if method == 'paired':
        method = 'paired_statistics'
    if method not in ('spearman', 'pearson', 'paired_statistics'):
        raise ValueError('无效统计方法')
    if not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError('分页参数无效')
    folder = core.located('analyses', analysis_id)
    core.read_json(folder/'manifest.json')
    path = folder/(method+'.csv')
    if not path.exists():
        raise ValueError('此分析没有所选统计结果')
    table = _read_results(path)
    if query:
        table = table.loc[table['feature'].str.contains(str(query), case=False, regex=False, na=False)]
    return dict(rows=_records(table.iloc[offset:offset+limit]), total=len(table), columns=list(table.columns),
                offset=offset, limit=limit, method=method, analysis_id=analysis_id)


def plot_dataset(analysis_id, gene):
    folder = core.located('analyses', analysis_id)
    manifest = core.read_json(folder/'manifest.json')
    settings = manifest['settings']
    if gene not in settings['features']:
        raise ValueError('所选基因不在此分析的完整特征列表')
    frame = pd.read_csv(folder/'analysis_input.csv', keep_default_na=False, dtype={settings['label']:str},
                        na_values={c:[''] for c in [settings['target']]+settings['features']})
    label, target = settings['label'], settings['target']
    selected = frame[[label, target, gene]].dropna(subset=[target, gene]).copy()
    if len(selected) < 3 or selected[gene].nunique() < 2 or selected[target].nunique() < 2:
        raise ValueError('此基因有效观测不足或为常数，无法生成相关散点图')
    metadata = core.store_dataset(selected.to_csv(index=False).encode('utf-8'), f'analysis_{analysis_id}_scatter.csv', manifest.get('demo', False))
    metadata['id_columns'] = [label]
    metadata['demo_spec'] = dict(chart='scatter', engine='r', columns={'x':gene,'y':target},
                                 exvivo=settings['exvivo'], title=f'{gene} / {target}'[:120])
    if settings['mode'] == 'paired_delta':
        metadata['demo_spec'].update(x_label=f'Delta {gene}'[:120], y_label=f'Delta {target}'[:120],
            title=f"{settings['comparison']} - {settings['reference']}: {gene} / {target}"[:120])
    elif settings['mode'] == 'centered':
        metadata['demo_spec'].update(x_label=f'Centered {gene}'[:120], y_label=f'Centered {target}'[:120],
            title=f'Centered within {settings["center_by"]}: {gene} / {target}'[:120])

    metadata['expression_profile'] = copy.deepcopy(manifest['report']['expression_profile'])
    metadata['expression_profile'].update(label=label, feature_columns=[gene], feature_count=1, sample_count=len(selected), value_state=settings['mode'], rows_are_samples=True)
    metadata['expression_profile'].pop('qc', None)
    metadata['annotation_columns'] = [target]
    metadata['summary'] = core.summarize(selected)
    metadata['exclusion_provenance'] = dict(analysis_id=analysis_id, already_applied=settings['exvivo'],
                                            excluded_samples=manifest['report']['excluded_samples'],
                                            source=manifest['report'].get('exclusion_source'),
                                            inherited=manifest['report'].get('exclusion_provenance', {}))
    metadata['provenance'] = dict(operation='analysis_scatter', analysis_id=analysis_id,
                                  parent_dataset_id=manifest['dataset_id'], parent_sha256=manifest['report']['parent_sha256'],
                                  analysis_input_sha256=manifest['report']['input_sha256'], feature=gene,
                                  analysis_settings=settings, report=manifest['report'],
                                  reference_statistics={})
    # Exact feature matching must work even if a short name matches >1000 genes.
    for method in ('spearman','pearson'):
        table = _read_results(folder/(method+'.csv'))
        metadata['provenance']['reference_statistics'][method] = _records(table.loc[table.feature==gene])[0]
    core.write_json(core.located('datasets', metadata['id'])/'metadata.json', metadata)
    return metadata
