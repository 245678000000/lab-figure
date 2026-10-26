"""Scientific preparation contracts, using immutable real uploaded datasets."""
import hashlib
import importlib
import importlib.util
import json

import numpy as np
import pandas as pd
import pytest

import core


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'STORE', tmp_path)


@pytest.fixture
def api():
    assert importlib.util.find_spec('analysis_data'), 'metadata and expression preparation module is missing'
    return importlib.import_module('analysis_data')


def upload(frame, name='expression.csv'):
    content = frame if isinstance(frame, bytes) else frame.to_csv(index=False).encode()
    return core.store_dataset(content, name)


def settings(**updates):
    return {'label':'sample', 'units':'counts', 'all_numeric':True,
            'rows_are_samples':True, **updates}


def test_join_matches_exact_ids_in_expression_order_and_preserves_sources(api):
    data = upload(b'sample,G1\n001,1\n01,2\nA,3\n')
    annotation = upload(b'id,group,age\nA,tumor,50\n01,normal,30\n001,tumor,40\n', 'clinical.csv')
    before = core.located('datasets', data['id']).joinpath(data['original']).read_bytes()
    args = (data['id'], annotation['id'], 'sample', 'id')
    preview = api.preview_metadata(*args, rows_are_samples=True)
    assert preview['valid'] and preview['missing_count'] == preview['extra_count'] == 0
    assert preview['annotation_columns'] == ['group', 'age']
    assert [row['sample'] for row in preview['preview']] == ['001', '01', 'A']
    result = api.attach_metadata(*args, rows_are_samples=True)
    frame, persisted = core.load_dataset(result['id'])
    assert frame['group'].tolist() == ['tumor', 'normal', 'tumor']
    assert frame.age.tolist() == [40, 30, 50]
    assert persisted['annotation_columns'] == ['group', 'age']
    assert persisted['id_columns'] == ['sample','group']
    assert frame['sample'].tolist() == ['001', '01', 'A']
    assert result['sample_metadata']['metadata_dataset_id'] == annotation['id']
    assert result['provenance']['parent_sha256'] == hashlib.sha256(before).hexdigest()
    assert core.located('datasets', data['id']).joinpath(data['original']).read_bytes() == before


@pytest.mark.parametrize('content', [b'id,group\nA,x\nA,y\nB,z\n', b'id,group\nA,x\n,y\nB,z\n'])
def test_join_rejects_duplicate_or_blank_ids(api, content):
    data = upload(b'sample,G1\nA,1\nB,2\n')
    annotation = upload(content)
    args = (data['id'], annotation['id'], 'sample', 'id')
    assert not api.preview_metadata(*args, rows_are_samples=True)['valid']
    with pytest.raises(ValueError):
        api.attach_metadata(*args, rows_are_samples=True)


def test_missing_extra_collision_and_orientation_require_explicit_resolution(api):
    data = upload(b'sample,group,G1\nA,old,1\nB,old,2\n')
    missing = upload(b'id,group\nA,new\nC,new\n')
    args = (data['id'], missing['id'], 'sample', 'id')
    report = api.preview_metadata(*args, rows_are_samples=True, allow_extra=True, prefix='meta_')
    assert not report['valid'] and report['missing_ids'] == ['B'] and report['extra_ids'] == ['C']
    extra = upload(b'id,group\nB,y\nA,x\nC,z\n')
    args = (data['id'], extra['id'], 'sample', 'id')
    assert not api.preview_metadata(*args)['valid']
    assert not api.preview_metadata(*args, rows_are_samples=True, prefix='meta_')['valid']
    assert not api.preview_metadata(*args, rows_are_samples=True, allow_extra=True)['valid']
    good = api.attach_metadata(*args, rows_are_samples=True, allow_extra=True, prefix='meta_')
    joined, _ = core.load_dataset(good['id'])
    assert joined.meta_group.tolist() == ['x', 'y']


def test_join_does_not_casefold_or_strip_sample_ids(api):
    data = upload(b'sample,G1\nA,1\n B,2\n')
    annotation = upload(b'id,group\na,x\nB,y\n')
    report = api.preview_metadata(data['id'], annotation['id'], 'sample', 'id', rows_are_samples=True)
    assert report['missing_ids'] == ['A', ' B']


def test_qc_excludes_aliases_before_variance_and_range_but_keeps_ld(api):
    data = upload(pd.DataFrame({'sample':['HNSCC3_HD','GSM9266346_HNSCC3_T','HNSCC3_LD','A','B'],
                                'G1':[1000,2000,1,1,1], 'G2':[999,888,0,2,4]}))
    with pytest.raises(ValueError, match='ex vivo'):
        api.inspect_expression(data['id'], settings())
    report = api.inspect_expression(data['id'], settings(exvivo=True))
    assert report['sample_count'] == 3 and report['excluded_rows'] == 2
    assert report['zero_variance_count'] == 1
    assert report['max'] == 4 and report['min'] == 0
    result = api.prepare_expression(data['id'], settings(exvivo=True, drop_zero_variance=True))
    frame, _ = core.load_dataset(result['id'])
    assert frame['sample'].tolist() == ['HNSCC3_LD','A','B'] and frame.columns.tolist() == ['sample','G2']


def test_numeric_annotations_never_enter_all_numeric_features(api):
    data = upload(b'sample,G1,G2\nA,1,0\nB,3,0\nC,7,1\n')
    annotation = upload(b'id,age,group\nA,40,x\nB,50,x\nC,60,y\n')
    joined = api.attach_metadata(data['id'], annotation['id'], 'sample', 'id', rows_are_samples=True)
    report = api.inspect_expression(joined['id'], settings())
    assert report['feature_count'] == 2 and report['max'] == 7
    prepared = api.prepare_expression(joined['id'], settings(transform='log2p1'))
    frame, _ = core.load_dataset(prepared['id'])
    np.testing.assert_allclose(frame.G1, [1,2,3])
    assert frame.age.tolist() == [40,50,60] and frame.group.tolist() == ['x','x','y']
    assert prepared['annotation_columns'] == ['age','group']
    assert prepared['sample_metadata'] == joined['sample_metadata']
    assert prepared['expression_profile']['units'] == 'log_expression'
    assert prepared['expression_profile']['source_units'] == 'counts'
    assert prepared['expression_profile']['rows_are_samples'] is True
    with pytest.raises(ValueError):
        api.prepare_expression(prepared['id'], settings(transform='log2p1'))


def test_filtering_is_explicit_and_unselected_genes_are_not_annotations(api):
    data = upload(b'sample,group,G1,G2,G3,G4\nA,x,0,2,5,9\nB,x,0,2,0,8\nC,y,0,2,1,7\n')
    chosen = dict(label='sample', units='counts', feature_columns=['G1','G2','G3'], rows_are_samples=True)
    report = api.inspect_expression(data['id'], {**chosen, 'min_expression':1, 'min_samples':2})
    assert report['zero_variance_count'] == 2 and report['low_expression_count'] == 2
    result = api.prepare_expression(data['id'], chosen)
    frame, _ = core.load_dataset(result['id'])
    assert frame.columns.tolist() == ['sample','group','G1','G2','G3']
    result = api.prepare_expression(data['id'], {**chosen,'filter_low':True,'min_expression':1,'min_samples':2})
    frame, _ = core.load_dataset(result['id'])
    assert frame.columns.tolist() == ['sample','group','G2']


@pytest.mark.parametrize('units,values,valid', [('counts',[0,1,2],True),('counts',[0,.5,2],False),
                                           ('counts',[-1,1,2],False),('unknown',[-1,.5,2],None)])
def test_declared_units_counts_validation_and_unknown_qc(api, units, values, valid):
    data = upload(pd.DataFrame({'sample':['A','B','C'],'G':values}))
    config = settings(); config['units'] = units
    report = api.inspect_expression(data['id'], config)
    assert report['counts_valid'] is valid
    if valid is False:
        with pytest.raises(ValueError):
            api.prepare_expression(data['id'],config)


@pytest.mark.parametrize('units,values', [('unknown',[0,1,2]),('log_expression',[0,1,2]),
                                       ('tpm',[-1,1,2]),('cpm',[0,float('inf'),2])])
def test_invalid_log_transforms_are_rejected(api, units, values):
    data = upload(pd.DataFrame({'sample':['A','B','C'],'G':values}))
    config = settings(transform='log2p1'); config['units'] = units
    with pytest.raises(ValueError):
        api.prepare_expression(data['id'],config)


def test_missing_is_reported_and_preserved_without_imputation(api):
    data = upload(b'sample,G1,G2\nA,1,0\nB,,1\nC,3,2\n')
    report = api.inspect_expression(data['id'],settings())
    assert report['missing'] == 1 and report['nonfinite'] == 0
    result = api.prepare_expression(data['id'],settings())
    frame, _ = core.load_dataset(result['id'])
    assert len(frame) == 3 and pd.isna(frame.G1.iloc[1])
    assert frame.G1.iloc[0] == 1 and frame.G1.iloc[2] == 3
    with pytest.raises(ValueError):
        api.prepare_expression(data['id'],settings(transform='log2p1'))


def test_explicit_orientation_and_numeric_features_are_required(api):
    data = upload(b'sample,G1,text\nA,1,no\nB,2,yes\nC,3,no\n')
    with pytest.raises(ValueError):
        api.inspect_expression(data['id'], {'label':'sample','units':'counts','all_numeric':True})
    with pytest.raises(ValueError):
        api.inspect_expression(data['id'], settings(feature_columns=['text'],all_numeric=False))


def test_qc_and_join_previews_stay_bounded_for_large_inputs(api):
    frame = pd.DataFrame(np.zeros((8,20000)),columns=[f'G{i}' for i in range(20000)])
    frame.insert(0,'sample',[f'S{i}' for i in range(8)])
    data = upload(frame)
    report = api.inspect_expression(data['id'],settings())
    assert report['feature_count'] == report['zero_variance_count'] == 20000
    assert len(report['zero_variance_features']) <= 30 and len(report['preview'][0]) <= 24
    assert len(json.dumps(report)) < 20000


def test_log_transform_keeps_fractional_values_and_original_matrix(api):
    data = upload(b'sample,G1\n001,2\n002,5\n003,8\n')
    result = api.prepare_expression(data['id'], settings(transform='log2p1'))
    frame, persisted = core.load_dataset(result['id'])
    np.testing.assert_allclose(frame.G1, [1.584962500721156, 2.584962500721156, 3.169925001442312])
    assert frame['sample'].tolist() == ['001','002','003']
    assert persisted['provenance']['settings']['transform'] == 'log2p1'
    assert persisted['provenance']['parent_dataset_id'] == data['id']
    original = core.located('datasets', data['id']) / data['original']
    assert original.read_bytes() == b'sample,G1\n001,2\n002,5\n003,8\n'


def test_preparation_cannot_relabel_cpm_as_tpm(api):
    data = upload(b'sample,G1\nA,1\nB,2\nC,3\n')
    prepared = api.prepare_expression(data['id'], settings(units='cpm'))
    with pytest.raises(ValueError):
        api.prepare_expression(prepared['id'], settings(units='tpm'))


def test_literal_na_sample_ids_remain_exact_strings(api):
    data = upload(b'sample,G1\nNA,1\nnull,2\nA,3\n')
    annotation = upload(b'id,group\nA,z\nNA,x\nnull,y\n')
    result = api.attach_metadata(data['id'],annotation['id'],'sample','id',rows_are_samples=True)
    frame, _ = core.load_dataset(result['id'])
    assert frame['sample'].tolist() == ['NA','null','A']
    assert frame.group.tolist() == ['x','y','z']


@pytest.mark.parametrize('units', ['cpm', 'tpm'])
@pytest.mark.parametrize('values', [[-1,1,2], [0,float('inf'),2]])
def test_declared_abundance_rejects_negative_or_infinite_without_log(api, units, values):
    data = upload(pd.DataFrame({'sample':['A','B','C'], 'G1':values}))
    config = settings(units=units)
    report = api.inspect_expression(data['id'], config)
    assert report['unit_valid'] is False
    assert any(units.upper() in note and ('非负' in note or '无穷' in note) for note in report['notes'])
    before = {p.name for p in (core.STORE / 'datasets').iterdir()}
    with pytest.raises(ValueError, match=units.upper()):
        api.prepare_expression(data['id'], config)
    assert {p.name for p in (core.STORE / 'datasets').iterdir()} == before


@pytest.mark.parametrize('units', ['unknown','log_expression'])
def test_negative_unknown_or_log_values_are_preserved_without_transform(api, units):
    data = upload(b'sample,G1\nA,-1\nB,0\nC,2\n')
    prepared = api.prepare_expression(data['id'], settings(units=units))
    frame, _ = core.load_dataset(prepared['id'])
    assert frame.G1.tolist() == [-1,0,2]


def test_invalid_counts_get_explicit_qc_unit_note(api):
    data = upload(b'sample,G1\nA,0\nB,0.5\nC,2\n')
    report = api.inspect_expression(data['id'], settings())
    assert report['unit_valid'] is False
    assert any('counts' in note and '非负整数' in note for note in report['notes'])


def test_annotation_group_codes_survive_attachment_and_centering(api):
    import correlation_analysis as ca
    data = upload(b'sample,G1\nA,2\nB,4\nC,20\nD,24\n')
    raw = b'id,group,condition,pair,age,function_value\nA,001,NA,01,20,1\nB,001,null,02,30,3\nC,01,1,03,40,10\nD,01,2,04,50,14\n'
    annotation = upload(raw)
    schema = api.metadata_columns(annotation['id'])
    assert {'id','group','condition','pair'} <= set(schema['text_columns'])
    assert not {'age','function_value'} & set(schema['text_columns'])
    group = next(c for c in schema['columns'] if c['name']=='group')
    assert group['type'] == 'categorical' and group['values'] == ['001','01']
    result = api.attach_metadata(data['id'],annotation['id'],'sample','id',rows_are_samples=True)
    joined, _ = core.load_dataset(result['id'])
    assert joined.group.tolist() == ['001','001','01','01']
    assert joined.condition.tolist() == ['NA','null','1','2']
    assert joined.pair.tolist() == ['01','02','03','04']
    assert pd.api.types.is_numeric_dtype(joined.function_value)
    assert pd.api.types.is_numeric_dtype(joined.age)
    assert {'sample','group','condition','pair'} <= set(result['id_columns'])
    analysis = ca.run(result['id'], {'label':'sample','target':'function_value','features':['G1'],
                      'rows_are_samples':True,'mode':'centered','center_by':'group'})
    centered = pd.read_csv(core.located('analyses',analysis['id']) / 'analysis_input.csv')
    assert analysis['report']['group_count'] == 2
    np.testing.assert_allclose(centered.G1, [-1,1,-2,2])
    np.testing.assert_allclose(centered.function_value, [-1,1,-2,2])
    assert (core.located('datasets',annotation['id']) / annotation['original']).read_bytes() == raw


def test_text_column_override_is_explicit_and_preserves_prefixed_ids(api):
    data = upload(b'sample,G1\nA,1\nB,2\n')
    annotation = upload(b'id,group,code,age\nA,1,001,20\nB,2,01,30\n')
    args = (data['id'],annotation['id'],'sample','id')
    result = api.attach_metadata(*args,prefix='meta_',rows_are_samples=True,text_columns=['code'])
    joined, _ = core.load_dataset(result['id'])
    assert joined.meta_code.tolist() == ['001','01']
    assert joined.meta_group.tolist() == [1,2]
    assert result['id_columns'] == ['sample','meta_code']
    assert result['provenance']['settings']['text_columns'] == ['code']
    auto = api.metadata_columns(annotation['id'])
    assert {'group','code'} <= set(auto['text_columns'])
    with pytest.raises(ValueError):
        api.preview_metadata(*args,rows_are_samples=True,text_columns=['missing'])


def test_role_like_chinese_and_numeric_condition_annotations_remain_text(api):
    data = upload(b'sample,G1\nA,1\nB,2\n')
    annotation = upload(pd.DataFrame({'id':['A','B'],'患者编号':['001','01'],
                                     'condition':[1,2],'function_value':[0.1,0.2]}))
    result = api.attach_metadata(data['id'],annotation['id'],'sample','id',rows_are_samples=True)
    joined, _ = core.load_dataset(result['id'])
    assert joined['患者编号'].tolist() == ['001','01']
    assert joined.condition.tolist() == ['1','2']
    assert joined.function_value.tolist() == [0.1,0.2]
