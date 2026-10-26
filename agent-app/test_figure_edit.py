"""Presentation edits must preserve source data, statistics, and editor changes."""
import zipfile

import pytest
import core
from bio import demo_recipe


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'STORE', tmp_path / 'store')


def test_scatter_text_and_note_edit_keeps_statistics_and_history():
    frame, columns, options = demo_recipe('scatter')
    data = core.store_dataset(frame.to_csv(index=False).encode(), 'scatter.csv', True)
    parent = core.render(data['id'], core.PlotSpec(chart='scatter', columns=columns, **options))
    folder = core.located('runs', parent['id'])
    before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
    code = parent['code'].replace('set.seed(42)', '# Keep my code\nset.seed(42)')
    edits = dict(title='Updated title', x_label='Before', y_label='After', note_position='manual', note_x=.25, note_y=.85)
    revised = core.render_code(parent['id'], code, figure_edits=edits)
    assert revised['stats'] == parent['stats']
    assert '# Keep my code' in revised['code']
    assert revised['figure_edit_info']['title'] == 'Updated title'
    assert revised['figure_edit_info']['x_label'] == 'Before'
    assert revised['figure_edit_info']['note_moved'] is True
    assert all((folder / name).read_bytes() == content for name, content in before.items())
    out = core.located('runs', revised['id'])
    assert (out / 'source_data.csv').read_bytes() == before['source_data.csv']
    with zipfile.ZipFile(out / 'reproduce.zip') as bundle:
        assert 'figure-edit.R' in bundle.namelist()
    again = core.render_code(revised['id'], revised['code'], figure_edits={**edits, 'title': 'Second title'})
    assert again['code'].count('# BEGIN AISI FIGURE EDIT') == 1
    assert again['figure_edit_info']['title'] == 'Second title'
    assert again['stats'] == parent['stats']


@pytest.mark.parametrize('engine', ['r', 'python'])
def test_roc_annotations_move_and_code_can_rerun(engine):
    data = core.demo_dataset()
    parent = core.render(data['id'], core.PlotSpec(engine=engine, columns={'outcome':'response', 'predictor':'score'}, positive='1'))
    revised = core.render_code(parent['id'], parent['code'], figure_edits=dict(title='ROC edited', x_label='False positive', y_label='Sensitivity', note_position='manual', note_x=.3, note_y=.8))
    assert revised['stats'] == parent['stats']
    assert revised['figure_edit_info']['note_moved'] is True
    rerun = core.render_code(revised['id'], revised['code'])
    assert rerun['stats'] == revised['stats']
    assert rerun['figure_edit_info'] == revised['figure_edit_info']


def test_edit_validation_and_unsupported_code():
    from figure_edit import FigureEdits, edit_code
    with pytest.raises(ValueError):
        FigureEdits(note_x=float('nan'))
    with pytest.raises(ValueError):
        FigureEdits(legend_y=1.5)
    with pytest.raises(ValueError, match='导出'):
        edit_code('print(1)', 'r', 'scatter', FigureEdits(title='hello'))


@pytest.mark.parametrize('chart', ['km', 'forest', 'upset', 'cor_heatmap', 'volcano'])
def test_labels_on_composite_and_bio_charts(chart):
    from fastapi.testclient import TestClient
    import main
    client = TestClient(main.app)
    data = client.post('/api/demo/'+chart, json={}).json()
    spec = core.PlotSpec.model_validate(data['demo_spec'])
    parent = core.render(data['id'], spec)
    edits = dict(title='研究结果', x_label='Horizontal', y_label='Vertical')
    if chart in ('km', 'volcano'):
        edits.update(legend_position='manual', legend_x=.8, legend_y=.6)
    if chart == 'km':
        edits.update(note_position='manual', note_x=.3, note_y=.5)
    result = core.render_code(parent['id'], parent['code'], figure_edits=edits)
    assert result['stats'] == parent['stats']
    assert result['figure_edit_info']['title'] == '研究结果'
    assert result['figure_edit_info']['x_label'] == 'Horizontal'
    if chart in ('km', 'volcano'):
        assert result['figure_edit_info']['legend_moved'] is True


def test_edit_api_validates_positions_and_runs_current_buffer(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    from test_code import job_result
    main.jobs.clear()
    monkeypatch.setattr(main, 'STORE', core.STORE)
    data = core.demo_dataset()
    parent = core.render(data['id'], core.PlotSpec(columns={'outcome':'response','predictor':'score'}, positive='1'))
    client = TestClient(main.app)
    request = dict(parent_run_id=parent['id'], code=parent['code'], edits={'title':'API title'})
    assert client.post('/api/figure/edit', json=request, headers={'Origin':'https://other.example'}).status_code == 403
    assert client.post('/api/figure/edit', json={**request,'edits':{'legend_x':2}}).status_code == 422
    job = client.post('/api/figure/edit', json=request)
    assert job.status_code == 200
    result = job_result(client, job.json()['job_id'])
    assert result['status'] == 'complete', result
    assert result['result']['run']['figure_edit_info']['title'] == 'API title'


@pytest.mark.parametrize('engine', ['r','python'])
@pytest.mark.parametrize('move_note', [False, True])
def test_edit_font_sizes_reach_export_and_preserve_stats(engine, move_note):
    from test_style import font_sizes
    data=core.demo_dataset()
    parent=core.render(data['id'],core.PlotSpec(engine=engine,columns={'outcome':'response','predictor':'score'},positive='1'))
    edits=dict(title='Sized title',title_size=18,axis_title_size=14,tick_size=11,legend_size=10,note_size=8)
    if move_note: edits.update(note_position='manual',note_x=.65,note_y=.3)
    updated=core.render_code(parent['id'],parent['code'],figure_edits=edits)
    sizes=font_sizes(updated)
    for wanted in (18,14,11,8):
        assert any(abs(s-wanted)<.3 for s in sizes),(engine,wanted,sizes)
    assert updated['stats']==parent['stats']
    assert updated['figure_edit_info']['note_moved'] is move_note
    assert updated['figure_edit_info']['font_sizes']['title_size']==18


@pytest.mark.parametrize('chart',['scatter','km'])
def test_legend_and_composite_title_font_sizes(chart):
    from test_style import font_sizes
    from fastapi.testclient import TestClient
    import main
    data=TestClient(main.app).post('/api/demo/'+chart,json={}).json()
    parent=core.render(data['id'],core.PlotSpec.model_validate(data['demo_spec']))
    result=core.render_code(parent['id'],parent['code'],figure_edits=dict(title='Font check',title_size=17,legend_size=13.5,note_size=7))
    sizes=font_sizes(result)
    for wanted in (17,13.5,7):
        assert any(abs(s-wanted)<.3 for s in sizes),(wanted,sizes)
    assert result['stats']==parent['stats']
