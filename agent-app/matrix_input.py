"""Explicit matrix transposition with provenance; no imputation or normalization."""
import numpy as np
import json
import pandas as pd
import core


def transpose(key, label, columns):
    data, meta = core.load_dataset(key, string_columns=[label])
    if label not in data or not columns or len(set(columns)) != len(columns):
        raise ValueError('请选择唯一的基因标识列及样本数值列')
    if label in columns or any(c not in data for c in columns):
        raise ValueError('样本数值列不能包含标识列，且必须存在')
    ids = data[label]
    if ids.isna().any() or ids.astype(str).str.strip().eq('').any() or ids.astype(str).duplicated().any():
        raise ValueError('基因标识有缺失或重复，请明确处理后再转置；不会自动合并')
    core.check_table_size(len(columns), len(data) + 1)
    matrix = data[columns]
    if any(not pd.api.types.is_numeric_dtype(matrix[c]) for c in columns):
        raise ValueError('所选样本列必须全部为数值，不能混入分组注释')
    if np.isinf(matrix.to_numpy(dtype=float)).any():
        raise ValueError('表达值含无穷值，请先明确处理规则')
    output = matrix.T.copy()
    output.columns = ids.astype(str)
    id_name = 'sample_id'
    while id_name in output.columns:
        id_name = '_' + id_name
    output.insert(0, id_name, output.index)
    output = output.reset_index(drop=True)
    provenance = {'operation': 'transpose', 'parent_dataset_id': key, 'parent_sha256': meta['sha256'],
                  'label_column': label, 'sample_columns': columns, 'orientation': 'rows_are_samples',
                  'note': '只转置选定数值矩阵；未标准化、未补值、未汇总。样本排除在后续分析选择阶段执行。'}
    return output, meta, id_name, provenance


def preview(key, label, columns):
    data, _, id_name, provenance = transpose(key, label, columns)
    return {'rows': len(data), 'features': len(data.columns)-1, 'label': id_name,
            'preview': json.loads(data.iloc[:5, :7].to_json(orient='records')),
            'provenance': provenance}


def create(key, label, columns):
    data, parent, id_name, provenance = transpose(key, label, columns)
    meta = core.store_dataset(data.to_csv(index=False).encode('utf-8'), 'transposed_' + parent['filename'].rsplit('.', 1)[0] + '.csv', parent['demo'])
    meta['provenance'] = provenance
    meta['id_columns'] = [id_name]
    meta['summary'] = core.summarize(data)
    meta['recognition'] = core.recognize_frame(data)
    meta['demo_spec'] = {'chart': 'pca', 'engine': 'r', 'columns': {'label': id_name, 'predictors': []}, 'matrix_orientation': 'samples', 'scaling': 'none', 'all_numeric_features': True}
    core.write_json(core.located('datasets', meta['id']) / 'metadata.json', meta)
    return meta
