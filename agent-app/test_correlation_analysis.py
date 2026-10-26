"""Independent scientific checks for frozen batch-analysis outputs."""
import json
import subprocess
import sys
import threading
import zipfile

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import core
import correlation_analysis as ca
import task_control


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'STORE', tmp_path)


def dataset(frame, **metadata):
    result = core.store_dataset(frame.to_csv(index=False).encode(), 'source.csv')
    result.update(metadata)
    core.write_json(core.located('datasets', result['id'])/'metadata.json', result)
    return result


def settings(**overrides):
    return dict(label='sample', target='target', features=['g1', 'g2'],
                rows_are_samples=True, **overrides)


def table(result, method):
    return pd.read_csv(core.located('analyses', result['id'])/(method+'.csv')).set_index('feature')


def test_correlations_separate_bh_full_outputs_and_reproduction(tmp_path):
    frame = pd.DataFrame({'sample':list('abcdef'), 'target':[2,3,3,8,5,9],
                          'g1':[-4,-2,-2,1,0,3], 'g2':[4,7,1,3,8,2]})
    meta = dataset(frame)
    result = ca.run(meta['id'], settings())
    assert result['status']=='complete' and result['feature_count']==2
    for method, function in [('spearman',stats.spearmanr), ('pearson',stats.pearsonr)]:
        output=table(result,method)
        p=[]
        for gene in ['g1','g2']:
            expected=function(frame[gene],frame.target)
            assert output.loc[gene,'r']==pytest.approx(expected.statistic)
            assert output.loc[gene,'p']==pytest.approx(expected.pvalue)
            assert output.loc[gene,'n']==6
            p.append(expected.pvalue)
        assert output.loc[['g1','g2'],'q'].to_numpy()==pytest.approx(stats.false_discovery_control(p))
    folder=core.located('analyses',result['id'])
    assert core.read_json(folder/'manifest.json')['report']['parent_sha256']==meta['sha256']
    with zipfile.ZipFile(folder/'reproduce.zip') as bundle:
        assert {'analysis_input.csv','analysis-settings.json','reproduce.py','manifest.json','spearman.csv'}<=set(bundle.namelist())
        target=tmp_path/'reproduction'
        bundle.extractall(target)
    subprocess.run([sys.executable,'reproduce.py'],cwd=target,check=True,capture_output=True)
    pd.testing.assert_frame_equal(pd.read_csv(folder/'pearson.csv'),pd.read_csv(target/'pearson.csv'))
    page=ca.get_results(result['id'],'pearson',query='g1',limit=1)
    assert page['total']==1 and page['rows'][0]['feature']=='g1'
    with pytest.raises(ValueError):ca.get_results(result['id'],'../../source')


@pytest.mark.parametrize('alias',['HNSCC3_HD','hnscc3.hd','GSM9266338_HNSCC3_HD','HNSCC3_tumor','HNSCC3_T','hnscc3.t','GSM9266346_HNSCC3_T'])
def test_exclusion_precedes_centering_and_keeps_ld(alias):
    frame=pd.DataFrame({'sample':[alias,'HNSCC3_LD','a','b','c','d'],
                        'group':['A','A','A','B','B','B'],
                        'target':[1000,1,4,3,5,8], 'g1':[2000,5,7,2,7,10], 'g2':[7000,8,1,2,9,8]})
    meta=dataset(frame)
    with pytest.raises(ValueError,match='ex vivo'):ca.run(meta['id'],settings(mode='centered',center_by='group'))
    result=ca.run(meta['id'],settings(mode='centered',center_by='group',exvivo=True))
    actual=pd.read_csv(core.located('analyses',result['id'])/'analysis_input.csv')
    expected=frame.iloc[1:].copy()
    expected[['target','g1','g2']]-=expected.groupby('group')[['target','g1','g2']].transform('mean')
    assert 'HNSCC3_LD' in actual['sample'].values
    assert np.allclose(actual[['target','g1','g2']],expected[['target','g1','g2']])
    assert table(result,'pearson').loc['g1','r']==pytest.approx(stats.pearsonr(expected.g1,expected.target).statistic)
    assert result['report']['excluded_samples']==1


def test_missing_constants_orientation_and_infinite():
    frame=pd.DataFrame({'sample':list('abcde'),'target':[1,2,3,4,5], 'g1':[1,np.nan,3,2,6], 'g2':[4]*5,'short':[np.nan,np.nan,np.nan,1,2]})
    meta=dataset(frame)
    with pytest.raises(ValueError,match='缺失'):ca.run(meta['id'],settings())
    result=ca.run(meta['id'],dict(settings(missing_policy='pairwise'),features=['g1','g2','short']))
    output=table(result,'spearman')
    assert output.loc['g1','n']==4
    assert output.loc['g1','r']==pytest.approx(stats.spearmanr([1,3,2,6],[1,3,4,5]).statistic)
    assert output.loc['g2','status']=='constant_feature' and np.isnan(output.loc['g2','q'])
    assert output.loc['short','status']=='insufficient_n' and output.loc['short','n']==2
    with pytest.raises(ValueError,match='样本'):ca.run(meta['id'],dict(settings(),rows_are_samples=False))
    frame.loc[0,'g1']=np.inf
    with pytest.raises(ValueError,match='无穷'):ca.run(dataset(frame)['id'],settings(missing_policy='pairwise'))


def test_pairing_direction_drop_duplicates_and_wilcoxon():
    frame=pd.DataFrame({'sample':[f's{i}' for i in range(9)],'pair':['a','a','b','b','c','c','d','d','e'],
                        'condition':['before','after']*4+['before'],
                        'target':[1,3,2,5,4,5,1,6,3], 'g1':[4,5,3,6,5,3,1,8,2],'g2':[4]*9})
    meta=dataset(frame)
    config=settings(mode='paired_delta',pair='pair',condition='condition',reference='before',comparison='after')
    with pytest.raises(ValueError,match='不完整'):ca.run(meta['id'],config)
    result=ca.run(meta['id'],dict(config,drop_incomplete_pairs=True))
    assert result['report']['pair_count']==4 and result['report']['pairs_discarded']==1
    output=table(result,'paired_statistics')
    expected=stats.wilcoxon([1,3,-2,7],method='approx')
    assert output.loc['g1','p']==pytest.approx(expected.pvalue)
    assert output.loc['g1','mean_delta']==pytest.approx(2.25)
    assert output.loc['g2','p']==1 and output.loc['g2','status']=='all_zero'
    assert table(result,'pearson').loc['g1','r']==pytest.approx(stats.pearsonr([1,3,-2,7],[2,3,1,5]).statistic)
    duplicate=pd.concat([frame,frame.iloc[[0]]],ignore_index=True)
    duplicate.loc[9,'sample']='extra'
    with pytest.raises(ValueError,match='重复'):ca.run(dataset(duplicate)['id'],dict(config,drop_incomplete_pairs=True))


def test_all_numeric_ignores_annotations_and_plot_snapshot_provenance():
    frame=pd.DataFrame({'sample':list('abcde'),'target':[1,5,2,4,7],'g1':[4,3,2,6,7], 'g2':[2,1,4,5,3], 'age':[1,2,3,4,5]})
    meta=dataset(frame,annotation_columns=['age'],expression_profile={'units':'TPM','feature_columns':['g1','g2']},provenance={'operation':'attach_metadata','parent_dataset_id':'123456abcdef'})
    result=ca.run(meta['id'],dict(settings(),features=[],all_numeric=True))
    assert set(table(result,'spearman').index)=={'g1','g2'}
    plot=ca.plot_dataset(result['id'],'g1')
    actual, saved=core.load_dataset(plot['id'])
    assert len(actual)==5 and plot['demo_spec']['chart']=='scatter'
    assert saved['provenance']['analysis_id']==result['id']
    assert saved['expression_profile']['units']=='TPM'
    with pytest.raises(ValueError):ca.plot_dataset(result['id'],'age')
    event=threading.Event(); event.set()
    with pytest.raises(task_control.Cancelled):
        with task_control.scope(event):
            ca.run(meta['id'],settings())


def test_small_paired_family_records_invalid_rows_and_constant_target():
    frame=pd.DataFrame({'sample':list('abcd'),'pair':['x','x','y','y'],'condition':['A','B']*2,
                        'target':[1,2,3,4],'g1':[1,2,5,7],'g2':[2,2,4,4]})
    config=settings(mode='paired_delta',pair='pair',condition='condition',reference='A',comparison='B')
    frame['g1']=np.nan
    result=ca.run(dataset(frame)['id'],dict(config,missing_policy='pairwise'))
    paired=table(result,'paired_statistics')
    assert paired.loc['g1','status']=='insufficient_n'
    assert np.isnan(paired.loc['g1','q'])
    assert paired.loc['g2','status']=='all_zero' and paired.loc['g2','p']==1
    frame['g1']=[1,2,5,7]
    frame=pd.concat([frame,pd.DataFrame({'sample':['e','f'],'pair':['z','z'],'condition':['A','B'],
                                         'target':[5,6],'g1':[6,10],'g2':[1,1]})],ignore_index=True)
    result=ca.run(dataset(frame)['id'],config)
    output=table(result,'pearson')
    assert output.loc['g1','status']=='constant_target'


def test_cancellation_during_statistics_never_publishes_manifest(monkeypatch):
    frame=pd.DataFrame({'sample':list('abcde'),'target':[1,4,2,3,7],'g1':[3,4,5,1,2],'g2':[4,1,2,5,9]})
    meta=dataset(frame)
    source=core.located('datasets',meta['id'])/'original.csv'
    original=source.read_bytes()
    event=threading.Event()
    def emit(message,name):
        if name=='analysis_statistics':event.set()
    with pytest.raises(task_control.Cancelled):
        with task_control.scope(event,emit):ca.run(meta['id'],settings())
    assert not list(core.STORE.glob('analyses/*/manifest.json'))
    assert source.read_bytes()==original


def test_pairwise_paired_uses_feature_specific_complete_pairs_and_alias_before_pairing():
    frame=pd.DataFrame({'sample':['HNSCC3_HD','s1','s2','s3','s4','s5','s6','s7','s8','HNSCC3_LD'],
                        'pair':['bad','bad','b','b','c','c','d','d','e','e'], 'condition':['A','B']*5,
                        'target':[900,3,1,3,4,7,2,6,1,6],
                        'g1':[1000,4,1,2,2,5,np.nan,5,2,9], 'g2':[8,3,2,3,4,2,3,8,3,4]})
    result=ca.run(dataset(frame)['id'],settings(mode='paired_delta',pair='pair',condition='condition',
                   reference='A',comparison='B',exvivo=True,drop_incomplete_pairs=True,missing_policy='pairwise'))
    assert result['report']['excluded_samples']==1 and result['report']['pairs_discarded']==1
    assert table(result,'spearman').loc['g1','n']==3
    assert table(result,'paired_statistics').loc['g1','n']==3
    assert table(result,'pearson').loc['g1','r']==pytest.approx(stats.pearsonr([1,3,7],[2,3,5]).statistic)


def test_feature_names_that_are_na_tokens_and_exact_snapshot_lookup():
    frame=pd.DataFrame({'sample':['s0','001','002','003'],'target':[1,2,4,3],
                        'NA':[2,4,3,6], 'g':[3,5,2,6], 'g1':[6,2,4,7]})
    meta=dataset(frame)
    # Mark lexical IDs, as prepared data does.
    meta['id_columns']=['sample']
    core.write_json(core.located('datasets',meta['id'])/'metadata.json',meta)
    # "NA" feature names must survive CSV paging without becoming NaN.
    result=ca.run(meta['id'],dict(settings(),features=['NA','g','g1']))
    page=ca.get_results(result['id'],'pearson',query='NA')
    assert page['total']==1 and page['rows'][0]['feature']=='NA'
    saved=ca.plot_dataset(result['id'],'g')
    assert saved['provenance']['reference_statistics']['pearson']['feature']=='g'


def test_requested_sample_ids_preserve_lexical_tokens_without_metadata():
    frame=pd.DataFrame({'sample':['001','01','1','NA','null'], 'target':[1,2,3,4,5],
                        'g1':[2,4,1,5,7], 'g2':[7,3,2,5,4]})
    result=ca.run(dataset(frame)['id'],settings())
    frozen=pd.read_csv(core.located('analyses',result['id'])/'analysis_input.csv',keep_default_na=False,dtype={'sample':str})
    assert frozen['sample'].tolist()==frame['sample'].tolist()
    assert table(result,'pearson').loc['g1','n']==5


def test_requested_group_pair_and_condition_ids_preserve_distinct_lexical_values():
    frame=pd.DataFrame({'sample':[f's{i}' for i in range(6)], 'group':['001']*3+['01']*3,
                        'pair':['001','001','01','01','1','1'], 'condition':['01','1']*3,
                        'target':[1,2,6,12,15,20], 'g1':[2,4,1,15,14,17], 'g2':[5,3,6,1,4,7]})
    meta=dataset(frame)
    centered=ca.run(meta['id'],settings(mode='centered',center_by='group'))
    expected=frame[['target','g1','g2']]-frame.groupby('group')[['target','g1','g2']].transform('mean')
    frozen=pd.read_csv(core.located('analyses',centered['id'])/'analysis_input.csv')
    assert np.allclose(frozen[['target','g1','g2']],expected)
    paired=ca.run(meta['id'],settings(mode='paired_delta',pair='pair',condition='condition',reference='01',comparison='1'))
    frozen=pd.read_csv(core.located('analyses',paired['id'])/'analysis_input.csv',dtype={'pair':str,'sample':str},keep_default_na=False)
    assert frozen['pair'].tolist()==['001','01','1']
    assert frozen['g1'].tolist()==[2,14,3]
    assert paired['report']['pair_count']==3


def test_identifier_roles_cannot_convert_numeric_target_to_text():
    frame=pd.DataFrame({'sample':list('abcde'), 'target':[1,2,3,4,5], 'g1':[2,4,1,5,7], 'g2':[7,3,2,5,4]})
    with pytest.raises(ValueError,match='标识|数值|目标'):
        ca.run(dataset(frame)['id'],settings(mode='centered',center_by='target'))


@pytest.mark.parametrize('unused_value',[np.nan,np.inf,-np.inf])
def test_paired_unused_condition_values_do_not_block_explicit_selected_conditions(unused_value):
    frame=pd.DataFrame({'sample':[f's{i}' for i in range(9)],
                        'pair':['x','x','y','y','z','z','x','y','z'],
                        'condition':['A','B']*3+['C']*3,
                        'target':[1,2,2,6,3,8,unused_value,unused_value,unused_value],
                        'g1':[1,3,4,9,2,9,unused_value,unused_value,unused_value],
                        'g2':[5,6,2,6,4,3,unused_value,unused_value,unused_value]})
    config=settings(mode='paired_delta',pair='pair',condition='condition',reference='A',comparison='B')
    result=ca.run(dataset(frame)['id'],config)
    assert result['settings']['missing_policy']=='error'
    assert result['report']['filtered_condition_rows']==3 and result['report']['pair_count']==3
    assert table(result,'pearson').loc['g1','r']==pytest.approx(stats.pearsonr([2,5,7],[1,4,5]).statistic)
    frame.loc[0,'g1']=unused_value
    with pytest.raises(ValueError,match='缺失|无穷'):
        ca.run(dataset(frame)['id'],config)


@pytest.mark.parametrize('discarded_value',[np.nan,np.inf,-np.inf])
def test_explicitly_dropped_incomplete_pair_values_do_not_block_complete_pairs(discarded_value):
    frame=pd.DataFrame({'sample':[f's{i}' for i in range(7)], 'pair':['a','a','b','b','c','c','incomplete'],
                        'condition':['A','B']*3+['A'],
                        'target':[1,2,2,6,3,8,discarded_value],
                        'g1':[1,3,4,9,2,9,discarded_value], 'g2':[5,6,2,6,4,3,discarded_value]})
    config=settings(mode='paired_delta',pair='pair',condition='condition',reference='A',comparison='B',drop_incomplete_pairs=True)
    result=ca.run(dataset(frame)['id'],config)
    assert result['report']['pair_count']==3 and result['report']['pairs_discarded']==1
    assert result['report']['discarded_pair_ids']==['incomplete']
    assert result['settings']['missing_policy']=='error'
    assert table(result,'pearson').loc['g1','n']==3
    frame.loc[0,'g1']=discarded_value
    with pytest.raises(ValueError,match='缺失|无穷'):
        ca.run(dataset(frame)['id'],config)


def test_inactive_mode_fields_do_not_change_raw_feature_selection():
    frame=pd.DataFrame({'sample':list('abcd'),'target':[1,2,4,5],'g1':[1,3,2,6],'g2':[2,3,5,9]})
    config=settings(all_numeric=True,mode='raw',center_by='g1',pair='g2',condition='target');config['features']=[]
    result=ca.run(dataset(frame)['id'],config)
    assert result['settings']['features']==['g1','g2']
    assert result['settings']['center_by']==result['settings']['pair']==result['settings']['condition']==''
