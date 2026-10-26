"""Local preparation and batch-statistics API; shares the app's cancellable jobs."""
import json
from typing import Literal
import numpy as np
import pandas as pd
from fastapi import HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
import core
import task_control


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class MetadataRequest(StrictRequest):
    metadata_id: str = Field(pattern=r'^[a-f0-9]{12}$')
    sample_column: str = Field(min_length=1, max_length=1000)
    metadata_sample_column: str = Field(min_length=1, max_length=1000)
    prefix: str = Field(default='', max_length=100)
    allow_extra: bool = False
    rows_are_samples: bool = False
    text_columns: list[str] | None = Field(default=None, max_length=50001)


class ExpressionRequest(StrictRequest):
    label: str = Field(min_length=1, max_length=1000)
    units: Literal['unknown', 'counts', 'cpm', 'tpm', 'log_expression'] = 'unknown'
    feature_columns: list[str] = Field(default_factory=list, max_length=50000)
    all_numeric: bool = True
    exvivo: bool = False
    rows_are_samples: bool = False
    transform: Literal['none', 'log2p1'] = 'none'
    drop_zero_variance: bool = False
    filter_low: bool = False
    min_expression: float = Field(default=0, ge=0)
    min_samples: int = Field(default=2, ge=1, le=100000)


class CorrelationRequest(StrictRequest):
    dataset_id: str = Field(pattern=r'^[a-f0-9]{12}$')
    label: str = Field(min_length=1, max_length=1000)
    target: str = Field(min_length=1, max_length=1000)
    features: list[str] = Field(default_factory=list, max_length=50000)
    all_numeric: bool = True
    rows_are_samples: bool = False
    exvivo: bool = False
    mode: Literal['raw', 'centered', 'paired_delta'] = 'raw'
    center_by: str = ''
    pair: str = ''
    condition: str = ''
    reference: str = ''
    comparison: str = ''
    drop_incomplete_pairs: bool = False
    missing_policy: Literal['error', 'pairwise'] = 'error'


def install(app, start_job, jobs):
    import analysis_data
    import correlation_analysis

    @app.get('/api/datasets/{key}/metadata-columns')
    def metadata_columns(key: str):
        return analysis_data.metadata_columns(key)

    @app.post('/api/datasets/{key}/metadata-preview')
    def metadata_preview(key: str, request: MetadataRequest):
        return analysis_data.preview_metadata(key, **request.model_dump())

    @app.post('/api/datasets/{key}/metadata')
    def metadata_attach(key: str, request: MetadataRequest):
        return analysis_data.attach_metadata(key, **request.model_dump())

    @app.post('/api/datasets/{key}/expression-check')
    def expression_check(key: str, request: ExpressionRequest):
        return analysis_data.inspect_expression(key, request.model_dump())

    @app.post('/api/datasets/{key}/expression-prepare')
    def expression_prepare(key: str, request: ExpressionRequest):
        return analysis_data.prepare_expression(key, request.model_dump())

    def execute_analysis(key, request):
        try:
            settings = request.model_dump(exclude={'dataset_id'})
            result = correlation_analysis.run(request.dataset_id, settings)
            task_control.check()
            jobs[key].update(status='complete', result={'analysis': result, 'mode': 'analysis',
                'message': '批量计算已完成；SCC、PCC 与多重检验结果已分别保存。点击基因可生成单张散点图。'})
        except task_control.Cancelled:
            raise
        except Exception as exc:
            jobs[key].update(status='error', error=str(exc)[:4000])

    @app.post('/api/analyses/correlation')
    def correlate(request: CorrelationRequest):
        core.located('datasets', request.dataset_id)
        return start_job(execute_analysis, request)

    @app.get('/api/analyses')
    def analyses():
        records = []
        for path in (core.STORE/'analyses').glob('*/manifest.json'):
            try:
                record = core.read_json(path)
                if record.get('status') == 'complete':
                    records.append({k: record.get(k) for k in ('id', 'dataset_id', 'created', 'feature_count', 'settings', 'report')})
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda item: item.get('created') or 0, reverse=True)[:100]

    @app.get('/api/analyses/{key}')
    def analysis_record(key: str):
        return core.read_json(core.located('analyses', key)/'manifest.json')

    @app.get('/api/analyses/{key}/results')
    def analysis_results(key: str, method: Literal['spearman', 'pearson', 'paired'] = 'spearman',
                         query: str = Query(default='', max_length=1000),
                         offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=200)):
        return correlation_analysis.get_results(key, method, query, offset, limit)

    @app.post('/api/analyses/{key}/plot')
    def analysis_plot(key: str, request: dict):
        if set(request) != {'gene'} or not isinstance(request['gene'], str):
            raise ValueError('请选择一个基因')
        return correlation_analysis.plot_dataset(key, request['gene'])

    @app.get('/api/analyses/{key}/files/{name}')
    def analysis_artifact(key: str, name: str):
        allowed = {'spearman.csv', 'pearson.csv', 'paired_statistics.csv', 'analysis_input.csv',
                   'analysis-settings.json', 'manifest.json', 'reproduce.zip', 'reproduce.py', 'statistics.py'}
        if name not in allowed:
            raise HTTPException(404, '文件不存在')
        folder = core.located('analyses', key)
        if core.read_json(folder/'manifest.json').get('status') != 'complete':
            raise ValueError('统计分析尚未完成')
        path = folder/name
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, '文件不存在')
        return FileResponse(path, filename=name)

    @app.post('/api/analysis-demo')
    def analysis_demo():
        rng = np.random.default_rng(419)
        rows, annotations = [], []
        for i in range(8):
            baseline = rng.poisson(15, 40)
            for j, condition in enumerate(['Before', 'After']):
                sample = 'HNSCC3_LD' if i == 0 and j == 0 else f'DEMO_{i+1}_{condition}'
                values = baseline + j*rng.poisson(4+i, 40)
                rows.append([sample, *values.tolist()])
                annotations.append([sample, f'Donor_{i+1}', condition, 'B1' if i < 4 else 'B2', 20+i*2+j*(i+1.5)])
        frame = pd.DataFrame(rows, columns=['sample_id', *[f'GENE_{i+1}' for i in range(40)]])
        ann = pd.DataFrame(annotations, columns=['sample_id', 'donor', 'condition', 'batch', 'function_value'])
        matrix = core.store_dataset(frame.to_csv(index=False).encode(), 'synthetic_expression_counts.csv', True)
        metadata = core.store_dataset(ann.to_csv(index=False).encode(), 'synthetic_sample_metadata.csv', True)
        joined = analysis_data.attach_metadata(matrix['id'], metadata['id'], 'sample_id', 'sample_id', rows_are_samples=True)
        joined['demo_spec'] = {'chart': 'scatter', 'engine': 'r', 'columns': {'x': 'GENE_1', 'y': 'function_value'}}
        joined['expression_profile'] = {'units': 'counts', 'label': 'sample_id', 'feature_columns': list(frame.columns[1:]), 'rows_are_samples': True}
        joined['analysis_demo'] = {'label': 'sample_id', 'target': 'function_value', 'pair': 'donor', 'condition': 'condition', 'reference': 'Before', 'comparison': 'After'}
        core.write_json(core.located('datasets', joined['id'])/'metadata.json', joined)
        return joined
