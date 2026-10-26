"""Cross-chart colours, physical export dimensions and conservative result recognition."""
import io
import json
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
import core
import main
import preferences
from recognition import recognize_frame

@pytest.fixture(autouse=True)
def storage(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'STORE',tmp_path)
    monkeypatch.setattr(main,'STORE',tmp_path)
    main.jobs.clear()


def make_data():
    frame=pd.DataFrame({'group':['A']*4+['B']*4+['C']*4,'value':[1,2,3,4,3,4,5,6,5,6,7,8],'response':[0,1]*6})
    return core.store_dataset(frame.to_csv(index=False).encode(),'groups.csv',True)

@pytest.mark.parametrize('engine',['r','python'])
def test_group_colors_survive_subset_and_registry_changes(engine):
    colors={'A':'#123456','B':'#654321','C':'#245678'}
    preferences.update_colors(core.STORE,colors)
    dataset=make_data()
    spec=core.PlotSpec(chart='box',engine=engine,columns={'group':'group','value':'value'})
    full=core.render(dataset['id'],spec)
    full_folder=core.located('runs',full['id'])
    svg=(full_folder/'figure.svg').read_text(encoding='utf-8').lower()
    assert all(c.lower() in svg for c in colors.values())
    frame=core.load_dataset(dataset['id'])[0]
    smaller=core.store_dataset(frame[frame.group!='A'].iloc[::-1].to_csv(index=False).encode(),'smaller.csv',True)
    reduced=core.render(smaller['id'],spec)
    assert reduced['plot_settings']['group_colors']=={'B':colors['B'],'C':colors['C']}
    preferences.update_colors(core.STORE,{'B':'#FF8800'})
    revised=core.render_code(full['id'],full['code'])
    assert revised['plot_settings']['group_colors']==colors
    svg=(core.located('runs',revised['id'])/'figure.svg').read_text(encoding='utf-8').lower()
    assert '#654321' in svg and '#ff8800' not in svg
    assert (full_folder/'plot-settings.json').read_text()==(core.located('runs',revised['id'])/'plot-settings.json').read_text()


def test_km_curve_and_risk_table_use_same_colors():
    dataset=core.demo_dataset()
    colors={'Control':'#123456','Treatment':'#654321'}
    preferences.update_colors(core.STORE,colors)
    r=core.render(dataset['id'],core.PlotSpec(chart='km',columns={'group':'group','time':'time_months','event':'event'},positive='1'))
    svg=(core.located('runs',r['id'])/'figure.svg').read_text(encoding='utf-8').lower()
    assert all(svg.count(c.lower())>=4 for c in colors.values())
    assert r['figure_style']['width_in']==5.0

@pytest.mark.parametrize('engine',['r','python'])
def test_custom_mm_matches_final_pdf_without_scaling_fonts(engine):
    dataset=core.demo_dataset()
    r=core.render(dataset['id'],core.PlotSpec(engine=engine,columns={'outcome':'response','predictor':'score'},positive='1',width_mm=85,height_mm=65))
    folder=core.located('runs',r['id'])
    width,height=core.pdf_page_mm(folder/'figure.pdf')
    assert width==pytest.approx(85,abs=.36)
    assert height==pytest.approx(65,abs=.36)
    assert next(q for q in r['qa'] if q['name']=='尺寸')['verdict']=='PASS'
    assert r['figure_style']['base_size_pt']==12
    assert r['figure_style']['width_in']*25.4==pytest.approx(85,abs=.01)


def test_width_only_preserves_preset_aspect_and_validates_inputs():
    dataset=core.demo_dataset()
    r=core.render(dataset['id'],core.PlotSpec(columns={'outcome':'response','predictor':'score'},positive='1',width_mm=85))
    st=r['figure_style']
    assert st['height_in']/st['width_in']==pytest.approx(2.2/2.7,rel=1e-4)
    for kwargs in ({'height_mm':80},{'width_mm':0},{'width_mm':900}):
        with pytest.raises(ValidationError): core.PlotSpec(**kwargs)


def test_color_api_persists_and_rejects_invalid_colors():
    client=TestClient(main.app)
    assert client.post('/api/colors',json={'colors':{'T cell':'#123456'}}).status_code==200
    assert preferences.read_colors(core.STORE)['T cell']=='#123456'
    assert client.get('/api/colors').json()['colors']['T cell']=='#123456'
    assert client.post('/api/colors',json={'colors':{'T cell':'red;system()'}}).status_code==400
    assert client.post('/api/colors',json={'colors':{'T cell':'#ff0000'}},headers={'Origin':'https://evil.example'}).status_code==403


def test_deseq2_recognition_does_not_mutate_data_or_use_raw_p():
    frame=pd.DataFrame({'gene':['G1','G2','G3'],'baseMean':[1,3,5],'log2FoldChange':[1,2,-3],'padj':[.01,.2,.4],'pvalue':[.001,.1,.2]})
    before=frame.copy(deep=True)
    rec=recognize_frame(frame)['candidates'][0]
    assert rec['name'].startswith('DESeq2')
    assert rec['suggestions'][0]['columns']['padj']=='padj'
    pd.testing.assert_frame_equal(frame,before)
    assert not recognize_frame(frame.drop(columns='padj'))['candidates']
    no_gene=recognize_frame(frame.drop(columns='gene'))['candidates'][0]
    assert 'label' not in no_gene['suggestions'][0]['columns']


def test_seurat_multi_cluster_requires_explicit_subset_and_recomputes_selection():
    frame=pd.DataFrame({'gene':['A','B','C']*2,'avg_log2FC':[1,2,-1,4,5,-6],'p_val_adj':[.01,.02,.03]*2,'cluster':['0']*3+['1']*3,'pct.1':[.1,.2,.3]*2})
    rec=recognize_frame(frame)['candidates'][0]
    assert rec['subset']=={'column':'cluster','values':['0','1']}
    assert not any(s['chart']=='marker_dot' for s in rec['suggestions'])
    dataset=core.store_dataset(frame.to_csv(index=False).encode(),'seurat.csv',True)
    mapping=rec['suggestions'][0]['columns']
    spec=core.PlotSpec(chart='volcano',columns=mapping,subset_column='cluster',subset_value='1')
    r=core.render(dataset['id'],spec)
    selected=pd.read_csv(core.located('runs',r['id'])/'source_data.csv')
    assert len(selected)==3 and selected.cluster.eq(1).all()
    assert sum(s['genes'] for s in r['stats'])==3
    assert r['report']['filtered_rows']==3
    legacy=recognize_frame(frame.rename(columns={'avg_log2FC':'avg_logFC'}))['candidates'][0]
    assert 'effect' not in legacy['suggestions'][0]['columns']


def test_enrichment_and_gsea_signatures_are_distinct():
    frame=pd.DataFrame({'Description':['P1','P2','P3'],'GeneRatio':['1/10','2/10','3/10'],'p.adjust':[.1,.2,.3],'Count':[1,2,3]})
    rec=recognize_frame(frame)['candidates'][0]
    assert {s['chart'] for s in rec['suggestions']}=={'enrichment_dot','enrichment_bar'}
    summary=frame.drop(columns=['GeneRatio','Count']).assign(NES=[1.,2.,3.])
    rec=recognize_frame(summary)['candidates'][0]
    assert not rec['suggestions'] and 'running ES' in rec['notes'][0]
    assert not recognize_frame(pd.DataFrame({'x':[1,2,3],'y':[1,3,4]}))['candidates']


def test_recognition_updates_after_xlsx_sheet_reload():
    book=io.BytesIO()
    with pd.ExcelWriter(book,engine='openpyxl') as writer:
        pd.DataFrame({'x':[1,2,3]}).to_excel(writer,sheet_name='Other',index=False)
        pd.DataFrame({'gene':['A','B','C'],'baseMean':[1,2,3],'log2FoldChange':[1,2,3],'padj':[.1,.2,.3]}).to_excel(writer,sheet_name='DESeq2',index=False)
    client=TestClient(main.app)
    d=client.post('/api/datasets',files={'file':('table.xlsx',book.getvalue())}).json()
    assert not d['recognition']['candidates']
    r=client.post('/api/datasets/'+d['id']+'/reload',json={'sheet':'DESeq2','header':1})
    assert r.status_code==200
    assert r.json()['recognition']['candidates'][0]['name'].startswith('DESeq2')
