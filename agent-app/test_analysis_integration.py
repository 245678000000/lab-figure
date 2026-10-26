import json
import time
import zipfile
import pandas as pd
import pytest
from fastapi.testclient import TestClient
import core
import main


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'STORE', tmp_path)
    monkeypatch.setattr(main, 'STORE', tmp_path)
    main.jobs.clear()


def dataset(frame, name='synthetic.csv'):
    return core.store_dataset(frame.to_csv(index=False).encode(), name, True)


def test_declared_identifier_columns_keep_leading_zeroes():
    meta = dataset(pd.DataFrame({'sample': ['001', '002', '003'], 'G1': [1, 2, 4]}))
    meta['id_columns'] = ['sample']
    core.write_json(core.located('datasets', meta['id'])/'metadata.json', meta)
    data, _ = core.load_dataset(meta['id'])
    assert data['sample'].tolist() == ['001', '002', '003']


def test_reload_preserves_declared_identifiers_and_fixed_preparation_header():
    matrix = dataset(pd.DataFrame({'sample': ['001', '01', '002'], 'G1': [1, 2, 4]}))
    annotations = dataset(pd.DataFrame({'sample': ['001', '01', '002'], 'group': ['01', '001', '01']}))
    client = TestClient(main.app)
    joined = client.post('/api/datasets/'+matrix['id']+'/metadata', json={
        'metadata_id': annotations['id'], 'sample_column': 'sample', 'metadata_sample_column': 'sample',
        'rows_are_samples': True}).json()
    folder = core.located('datasets', joined['id'])
    original = (folder/joined['original']).read_bytes()
    response = client.post('/api/datasets/'+joined['id']+'/reload', json={'header': 1})
    assert response.status_code == 200, response.text
    columns = {c['name']: c for c in response.json()['summary']['columns']}
    assert columns['sample']['values'] == ['001', '01', '002']
    assert columns['group']['values'] == ['01', '001']
    saved = (folder/'metadata.json').read_bytes()
    rejected = client.post('/api/datasets/'+joined['id']+'/reload', json={'header': 2})
    assert rejected.status_code == 400
    assert (folder/'metadata.json').read_bytes() == saved
    assert (folder/joined['original']).read_bytes() == original


def test_metadata_routes_align_and_numeric_annotations_do_not_enter_pca():
    matrix = dataset(pd.DataFrame({'sample': ['A', 'B', 'C', 'D'], 'G1': [1, 3, 4, 8], 'G2': [3, 2, 8, 9]}))
    annotations = dataset(pd.DataFrame({'sample': ['D', 'B', 'A', 'C'], 'age': [40, 20, 10, 30], 'group': ['Y', 'X', 'X', 'Y']}), 'annotations.csv')
    request = {'metadata_id': annotations['id'], 'sample_column': 'sample', 'metadata_sample_column': 'sample', 'rows_are_samples': True}
    client = TestClient(main.app)
    preview = client.post('/api/datasets/'+matrix['id']+'/metadata-preview', json=request)
    assert preview.status_code == 200
    response = client.post('/api/datasets/'+matrix['id']+'/metadata', json=request)
    assert response.status_code == 200, response.text
    joined = response.json()
    frame, meta = core.load_dataset(joined['id'])
    assert frame.age.tolist() == [10, 20, 30, 40]
    spec = core.PlotSpec(chart='pca', columns={'label': 'sample', 'group': 'group'}, all_numeric_features=True, matrix_orientation='samples')
    result = core.render(joined['id'], spec)
    assert result['report']['feature_count'] == 2
    folder = core.located('runs', result['id'])
    with zipfile.ZipFile(folder/'reproduce.zip') as z:
        context = json.loads(z.read('analysis-context.json'))
        assert context['sample_metadata']
        assert json.loads(z.read('analysis-settings.json'))['columns']['predictors'] == ['G1', 'G2']


def test_analysis_job_context_and_strict_request(monkeypatch):
    meta = dataset(pd.DataFrame({'sample': ['A', 'B', 'C', 'D'], 'G1': [1, 3, 4, 8], 'target': [3, 2, 8, 9]}))
    client = TestClient(main.app)
    request = {'dataset_id': meta['id'], 'label': 'sample', 'target': 'target', 'features': ['G1'], 'rows_are_samples': True}
    started = client.post('/api/analyses/correlation', json=request)
    assert started.status_code == 200, started.text
    job = client.get('/api/jobs/'+started.json()['job_id']).json()
    assert job['context'] == {'dataset_id': meta['id'], 'kind': 'analysis'}
    for _ in range(100):
        if job['status'] != 'running': break
        time.sleep(.02)
        job = client.get('/api/jobs/'+started.json()['job_id']).json()
    assert job['status'] == 'complete', job
    main.jobs.clear()
    assert client.post('/api/analyses/correlation', json={**request, 'unexpected': True}).status_code == 422


def test_demo_preparation_batch_download_and_selected_gene_plot():
    client = TestClient(main.app)
    data = client.post('/api/analysis-demo', json={}).json()
    assert data['demo'] is True and data['sample_metadata']
    settings = {'label': 'sample_id', 'units': 'counts', 'all_numeric': True, 'rows_are_samples': True, 'drop_zero_variance': True}
    checked = client.post('/api/datasets/'+data['id']+'/expression-check', json=settings)
    assert checked.status_code == 200, checked.text
    assert checked.json()['feature_count'] == 40
    prepared = client.post('/api/datasets/'+data['id']+'/expression-prepare', json=settings).json()
    request = {'dataset_id': prepared['id'], 'label': 'sample_id', 'target': 'function_value', 'all_numeric': True,
               'rows_are_samples': True, 'mode': 'paired_delta', 'pair': 'donor', 'condition': 'condition',
               'reference': 'Before', 'comparison': 'After'}
    response = client.post('/api/analyses/correlation', json=request)
    assert response.status_code == 200, response.text
    for _ in range(300):
        job = client.get('/api/jobs/'+response.json()['job_id']).json()
        if job['status'] != 'running': break
        time.sleep(.02)
    assert job['status'] == 'complete', job
    result = job['result']['analysis']
    assert result['report']['pair_count'] == 8 and result['feature_count'] == 40
    for method in ['spearman', 'pearson', 'paired']:
        page = client.get('/api/analyses/'+result['id']+'/results', params={'method': method, 'limit': 5}).json()
        assert page['total'] == 40 and len(page['rows']) == 5
    downloaded = client.get('/api/analyses/'+result['id']+'/files/reproduce.zip')
    assert downloaded.status_code == 200
    assert client.get('/api/analyses/'+result['id']+'/files/unknown.txt').status_code == 404
    plotted = client.post('/api/analyses/'+result['id']+'/plot', json={'gene': 'GENE_1'})
    assert plotted.status_code == 200, plotted.text
    plot_data = plotted.json()
    assert plot_data['demo'] is True
    assert plot_data['demo_spec']['x_label'].startswith('Delta ')
    assert plot_data['demo_spec']['y_label'].startswith('Delta ')
    assert 'After' in plot_data['demo_spec']['title'] and 'Before' in plot_data['demo_spec']['title']
    assert plot_data['provenance']['reference_statistics']['spearman']['feature'] == 'GENE_1'
    figure = core.render(plot_data['id'], core.PlotSpec(**plot_data['demo_spec']))
    assert figure['report']['analyzed_rows'] == 8
    assert next(q for q in figure['qa'] if q['name']=='碰撞')['verdict']=='PASS'
    assert figure['report']['analysis_context']['provenance']['analysis_id'] == result['id']
