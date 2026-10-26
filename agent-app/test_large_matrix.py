import io
import json
import zipfile
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
import core
import main
import matrix_input
import agent


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(core,'STORE',tmp_path)
    monkeypatch.setattr(main,'STORE',tmp_path)
    main.jobs.clear()


def test_20000_gene_transpose_bounded_preview_and_exact_pca():
    rng=np.random.default_rng(192)
    matrix=rng.normal(size=(20000,8))
    frame=pd.DataFrame(matrix,columns=[f'S{i}' for i in range(8)])
    frame.insert(0,'gene',[f'GENE_{i}' for i in range(20000)])
    meta=core.store_dataset(frame.to_csv(index=False).encode(),'large.csv',True)
    args=(meta['id'],'gene',list(frame.columns[1:]))
    preview=matrix_input.preview(*args)
    assert preview['features']==20000
    assert len(preview['preview'][0])<=7
    new=matrix_input.create(*args)
    assert new['summary']['column_count']==20001
    assert len(new['summary']['preview'][0])<=24
    assert new['demo_spec']['all_numeric_features'] is True
    assert len(new['demo_spec']['columns'].get('predictors',[]))<300
    compact=agent.safe_summary(new)
    assert len(compact['columns'])<=200 and compact['column_count']==20001
    actual,_=core.load_dataset(new['id'])
    np.testing.assert_allclose(actual.iloc[:,1:].to_numpy(),matrix.T,rtol=1e-12,atol=1e-12)
    result=core.render(new['id'],core.PlotSpec(**new['demo_spec']))
    assert result['report']['analyzed_rows']==8
    assert result['report']['feature_count']==20000
    assert len(result['code'])<20000
    _,singular,_=np.linalg.svd(matrix.T-matrix.T.mean(axis=0),full_matrices=False)
    expected=singular**2/(singular**2).sum()
    np.testing.assert_allclose([r['variance_explained'] for r in result['stats']],expected,atol=1e-10)
    folder=core.located('runs',result['id'])
    loadings=pd.read_csv(folder/'pca_loadings.csv')
    assert len(loadings)==20000
    rerun=core.render_code(result['id'],result['code'])
    np.testing.assert_allclose([r['variance_explained'] for r in rerun['stats']],expected,atol=1e-10)
    with zipfile.ZipFile(folder/'reproduce.zip') as z:
        assert 'pca_loadings.csv' in z.namelist()


def test_resource_limits_and_wide_table_preview(tmp_path):
    wide=pd.DataFrame(np.ones((3,400)),columns=[f'F{i}' for i in range(400)])
    path=tmp_path/'wide.csv';wide.to_csv(path,index=False)
    data,_,_=core.read_table(path)
    assert data.shape==(3,400)
    assert len(core.summarize(data)['preview'][0])<=24
    core.check_table_size(100,50001)
    core.check_table_size(1000,50000)                 # 50 million cells is the limit
    with pytest.raises(ValueError,match='单元格'):
        core.check_table_size(1001,50000)
    with pytest.raises(ValueError,match='列'):
        core.check_table_size(2,50002)


def test_all_numeric_selection_excludes_id_and_group_before_scaling():
    frame=pd.DataFrame({'sample_id':['HNSCC3_HD','HNSCC3_T','HNSCC3_LD','A','B'], 'group':[1,1,2,2,1], 'G1':[99,98,1,3,5], 'G2':[99,98,4,5,9]})
    spec=core.PlotSpec(chart='pca',columns={'label':'sample_id','group':'group'},all_numeric_features=True,matrix_orientation='samples',scaling='column_z',exvivo=True)
    data,report=core.validate_spec(frame,spec)
    assert report['feature_count']==2 and report['excluded_rows']==2
    assert data.sample_id.tolist()==['HNSCC3_LD','A','B']
    assert 'predictors' not in spec.columns


def test_upload_over_old_25mb_limit():
    content=b'gene,A,B,C\nG1,1,2,3\nG2,4,5,6\nG3,7,9,4\n'+b'\n'*(26*1024*1024)
    response=TestClient(main.app).post('/api/datasets',files={'file':('padded.csv',content)})
    assert response.status_code==200

def test_explicit_large_feature_selection_stays_compact_and_reproducible():
    rng=np.random.default_rng(912)
    frame=pd.DataFrame(rng.normal(size=(5,350)),columns=[f'G{i}' for i in range(350)])
    frame.insert(0,'sample_id',[f'S{i}' for i in range(5)])
    meta=core.store_dataset(frame.to_csv(index=False).encode(),'explicit.csv',True)
    spec=core.PlotSpec(chart='pca',columns={'label':'sample_id','predictors':list(frame.columns[1:])},matrix_orientation='samples')
    compact=agent.compact_spec(spec)
    assert len(compact['columns']['predictors'])==200
    proposed=spec.model_copy(deep=True);proposed.columns['predictors']=['G0','G1']
    agent.preserve_features(proposed,spec)
    assert proposed.columns['predictors']==spec.columns['predictors']
    result=core.render(meta['id'],spec)
    assert 'read_features()' in result['code']
    folder=core.located('runs',result['id'])
    with zipfile.ZipFile(folder/'reproduce.zip') as z:
        assert len(json.loads(z.read('analysis-settings.json'))['columns']['predictors'])==350
    rerun=core.render_code(result['id'],result['code'])
    assert rerun['stats']==result['stats']


def test_pca_resource_and_zero_variance_guards():
    frame=pd.DataFrame(np.ones((3,3)),columns=['G1','G2','G3']);frame.insert(0,'sample',['A','B','C'])
    spec=core.PlotSpec(chart='pca',columns={'label':'sample'},all_numeric_features=True,matrix_orientation='samples')
    with pytest.raises(ValueError,match='方差'):
        core.validate_spec(frame,spec)
    large=pd.DataFrame(np.ones((1001,1001)));large.columns=[str(c) for c in large.columns];large.insert(0,'sample',[f'S{i}' for i in range(1001)])
    with pytest.raises(ValueError,match='1,000'):
        core.validate_spec(large,spec)


def test_all_numeric_feature_names_frozen_before_exclusion():
    frame=pd.DataFrame({'sample_id':['HNSCC3_HD','S1','S2','S3','S4'],
                        'G1':[99,1,3,5,7],'G2':[99,4,5,9,8],
                        'annotation':['not_measured','10','20','40','80']})
    meta=core.store_dataset(frame.to_csv(index=False).encode(),'numeric_annotation.csv',True)
    spec=core.PlotSpec(chart='pca',columns={'label':'sample_id'},all_numeric_features=True,matrix_orientation='samples',exvivo=True)
    result=core.render(meta['id'],spec)
    folder=core.located('runs',result['id'])
    loadings=pd.read_csv(folder/'pca_loadings.csv',index_col=0)
    assert loadings.index.tolist()==['G1','G2']
    assert result['report']['feature_count']==len(loadings)
    assert core.read_json(folder/'analysis-settings.json')['columns']['predictors']==['G1','G2']

def test_wide_numeric_outcome_and_reference_keep_category_values():
    frame=pd.DataFrame(np.zeros((4,301)),columns=[f'G{i}' for i in range(301)])
    frame['response']=[0,1,0,1];frame['condition']=[1,2,1,2]
    summary=core.summarize(frame)
    columns={c['name']:c for c in summary['columns']}
    assert columns['response']['values']==['0','1']
    assert columns['condition']['values']==['1','2']


def test_transpose_preserves_lexical_gene_and_sample_identifiers():
    source = b'gene,001,01,NA\n001,1,2,3\n01,3,4,5\nNA,5,6,7\n'
    metadata = core.store_dataset(source, 'lexical.csv')
    transposed = matrix_input.create(metadata['id'], 'gene', ['001', '01', 'NA'])
    data, _ = core.load_dataset(transposed['id'])
    assert list(data.columns) == ['sample_id', '001', '01', 'NA']
    assert data['sample_id'].tolist() == ['001', '01', 'NA']
    assert transposed['summary']['columns'][0]['values'] == ['001', '01', 'NA']
    assert (core.located('datasets', metadata['id'])/metadata['original']).read_bytes() == source


@pytest.mark.parametrize('extension', ['csv', 'tsv', 'xlsx'])
def test_duplicate_headers_are_rejected_before_pandas_renames_them(tmp_path, extension):
    path = tmp_path/('duplicate.'+extension)
    frame = pd.DataFrame([[1, 2], [3, 4]], columns=['GENE', 'GENE'])
    if extension == 'xlsx':
        frame.to_excel(path, index=False)
    else:
        frame.to_csv(path, sep='\t' if extension == 'tsv' else ',', index=False)
    with pytest.raises(ValueError, match='重复列名'):
        core.read_table(path)

def test_wide_reader_preserves_quotes_newlines_names_and_types(tmp_path):
    frame=pd.DataFrame({'sample':['one,quote"','two\nlines','三'], 'gene,"\n名':[1.25,np.nan,-3.5], 'flag':[True,False,True]})
    frame.to_csv(tmp_path/'source_data.csv',index=False)
    core.write_json(tmp_path/'source-schema.json',{'columns':list(frame.columns),'types':['character','numeric','logical'],'rows':3})
    import shutil
    shutil.copyfile(core.ROOT/'wide-table.R',tmp_path/'wide-table.R')
    (tmp_path/'read.R').write_text('source("wide-table.R"); d <- ais_read_wide(); jsonlite::write_json(d,"roundtrip.json",dataframe="columns",na="null",digits=NA)',encoding='utf-8')
    rc,log=core.run_process([core.RSCRIPT,'--vanilla','read.R'],tmp_path)
    assert rc==0,log
    data=core.read_json(tmp_path/'roundtrip.json')
    assert data['sample']==frame['sample'].tolist()
    assert data['gene,"\n名']==[1.25,None,-3.5]
    assert data['flag']==[True,False,True]
