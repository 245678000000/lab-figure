"""Check the rendered typography against an original template, and style snapshots."""
import sys
from pathlib import Path
import zipfile
import pytest
from fastapi.testclient import TestClient
import core
import main
from bio import demo_recipe

sys.path.insert(0, str(core.REPO/'skill/lab-figure/scripts/qa'))
import audit_pdf_text as pdf_text

@pytest.fixture(autouse=True)
def storage(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'STORE',tmp_path/'store')
    monkeypatch.setattr(main,'STORE',tmp_path/'store')
    main.jobs.clear()


def new_plot(chart):
    frame,columns,options=demo_recipe(chart)
    d=core.store_dataset(frame.to_csv(index=False).encode('utf-8'),'style_demo.csv',True)
    return core.render(d['id'],core.PlotSpec(chart=chart,columns=columns,**options))


def font_sizes(run):
    streams,_=pdf_text.decoded_streams((core.located('runs',run['id'])/'figure.pdf').read_bytes())
    return {round(r.size_pt,1) for i,stream in enumerate(streams) for r in pdf_text.scan_text_runs(stream,i)}


def test_new_figure_fonts_match_original_template():
    dataset=core.demo_dataset()
    original=core.render(dataset['id'],core.PlotSpec(columns={'outcome':'response','predictor':'score'},positive='1'))
    updated=new_plot('volcano')
    before,after=font_sizes(original),font_sizes(updated)
    assert any(abs(s-12)<.2 for s in before & after), (before,after)
    assert any(abs(s-10)<.6 for s in before & after), (before,after)
    assert updated['figure_style']['annotation_mm']==3
    assert updated['figure_style']['colors']==['#00305d','#9c1915']
    assert updated['figure_style']['dpi']==300


def test_manual_revision_keeps_style_snapshot(tmp_path,monkeypatch):
    original=new_plot('histogram')
    parent=core.located('runs',original['id'])
    snapshot=(parent/'figure-style.R').read_bytes()
    # A later application style update must not change an existing manual revision.
    future=tmp_path/'future_app';future.mkdir()
    (future/'figure-style.R').write_text('stop("Future style must not be read")',encoding='utf-8')
    monkeypatch.setattr(core,'ROOT',future)
    revised=core.render_code(original['id'],original['code'])
    out=core.located('runs',revised['id'])
    assert (out/'figure-style.R').read_bytes()==snapshot
    assert revised['figure_style']==original['figure_style']
    with zipfile.ZipFile(out/'reproduce.zip') as bundle:
        assert bundle.read('figure-style.R')==snapshot
        assert 'figure-style.json' in bundle.namelist()


def test_display_name_and_style_download():
    client=TestClient(main.app)
    assert main.app.title=='AISI-figure'
    page=client.get('/').text
    assert '<title>AISI-figure</title>' in page
    result=new_plot('histogram')
    r=client.get('/api/runs/'+result['id']+'/files/figure-style.R')
    assert r.status_code==200
    assert 'ais_house' in r.text


def test_balanced_scatter_export_preserves_stats_and_remains_code_editable():
    frame, columns, options = demo_recipe('scatter')
    data = core.store_dataset(frame.to_csv(index=False).encode(), 'scatter.csv', True)
    spec = core.PlotSpec(chart='scatter', columns=columns, **options)
    old = core.render(data['id'], spec.model_copy(update={'size': 'wide'}))
    new = core.render(data['id'], spec)
    assert new['stats'] == old['stats']
    assert new['figure_style']['width_in'] == new['figure_style']['height_in'] == 4.6
    assert new['figure_style']['axis_text_pt'] == old['figure_style']['axis_text_pt']
    assert all(q['verdict'] == 'PASS' for q in new['qa']), new['qa']
    code = new['code'].replace('wh <- c(4.6, 4.6)', 'wh <- c(4.6, 4.0)')
    edited = core.render_code(new['id'], code)
    assert edited['figure_style']['height_in'] == 4.0
    assert core.read_json(core.located('runs', new['id'])/'manifest.json')['figure_style']['height_in'] == 4.6


@pytest.mark.parametrize('engine', ['r', 'python'])
def test_group_canvas_grows_with_categories_and_respects_explicit_size(engine):
    import pandas as pd
    spec = core.PlotSpec(chart='box', engine=engine, columns={'group':'group','value':'value'})
    small = pd.DataFrame({'group':['A','B'], 'value':[1,2]})
    large = pd.DataFrame({'group':list('ABCDEFGHIJ'), 'value':range(10)})
    assert core.default_figure_size(small, spec) == [3.8, 4.2]
    assert core.default_figure_size(large, spec)[0] > 3.8
    assert core.default_figure_size(small, spec.model_copy(update={'width_mm':85})) is None
    assert core.default_figure_size(small, spec.model_copy(update={'size':'single'})) is None
