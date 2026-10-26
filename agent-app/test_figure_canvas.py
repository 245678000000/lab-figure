"""Read actual exported typography and preserve statistics through direct edits."""
import base64

import pymupdf
import pytest
from fastapi.testclient import TestClient

import core
import main
from bio import demo_recipe
from figure_inspect import inspect_figure


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'STORE', tmp_path / 'store')
    monkeypatch.setattr(main, 'STORE', core.STORE)


def scatter():
    frame, columns, options = demo_recipe('scatter')
    data = core.store_dataset(frame.to_csv(index=False).encode(), 'scatter.csv', True)
    return core.render(data['id'], core.PlotSpec(chart='scatter', columns=columns, title='Measured title', **options))


def test_actual_pdf_font_and_selectable_statistics_without_mutating_history():
    run = scatter()
    folder = core.located('runs', run['id'])
    before = {p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
    response = TestClient(main.app).get('/api/runs/'+run['id']+'/editable-figure')
    assert response.status_code == 200, response.text
    data = response.json()
    objects = {o['role']:o for o in data['objects']}
    assert {'note','x','y','title'} <= objects.keys()
    note = objects['note']
    assert 'spearman' in note['text'] and 'pearson' in note['text']
    assert len(note['lines']) == 2
    with pymupdf.open(folder/'figure.pdf') as pdf:
        actual = next(s['size'] for b in pdf[0].get_text('dict')['blocks'] for l in b.get('lines',[]) for s in l['spans'] if 'spearman' in s['text'])
    assert abs(note['size']-actual) < .01
    assert 'Arial' in note['font'] or 'Helvetica' in note['font']
    assert base64.b64decode(data['background'].split(',',1)[1]).startswith(b'\x89PNG')
    assert before == {p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}


@pytest.mark.parametrize('engine',['r','python'])
def test_selected_font_and_center_position_reach_export(engine):
    data = core.demo_dataset()
    parent = core.render(data['id'], core.PlotSpec(engine=engine, columns={'outcome':'response','predictor':'score'},positive='1'))
    edits = dict(title='Font family test', title_family='Times New Roman', axis_title_family='Times New Roman', x_label_size=17,
                 note_family='Times New Roman', note_size=13, note_position='manual',note_x=.4,note_y=.7,note_hjust=.5,note_vjust=.5)
    updated = core.render_code(parent['id'], parent['code'], figure_edits=edits)
    figure = inspect_figure(core.located('runs',updated['id']),updated)
    assert abs(figure['styles']['x']['size']-17)<.1
    assert abs(figure['styles']['y']['size']-17)>1
    note = next(o for o in figure['objects'] if o['role']=='note')
    assert abs(note['size']-13)<.1
    assert 'Times' in note['font'], note
    center = [(note['bbox'][0]+note['bbox'][2])/2,(note['bbox'][1]+note['bbox'][3])/2]
    assert abs(center[0]-figure['width']*.4)<4
    assert abs(center[1]-figure['height']*.3)<4
    assert updated['stats']==parent['stats']
    again=core.render_code(updated['id'],updated['code'])
    assert again['stats']==parent['stats']


def test_moving_caption_preserves_its_original_custom_font_size():
    parent=scatter()
    code=parent['code'].replace('save_fig(p,','p <- p + ggplot2::theme(plot.caption=ggplot2::element_text(size=14, family="Times New Roman"))\nsave_fig(p,')
    updated=core.render_code(parent['id'],code,figure_edits=dict(note_position='manual',note_x=.5,note_y=.7))
    figure=inspect_figure(core.located('runs',updated['id']),updated)
    note=next(o for o in figure['objects'] if o['role']=='note')
    assert abs(note['size']-14)<.1
    assert 'Times' in note['font']
    assert len(note['lines'])==2
