"""Image payloads, real cancellation, persisted preferences and scientific orientation."""
import asyncio
import base64
import json
import sys
import threading
import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import agent
import core
import main
import matrix_input
import model_preferences
import task_control


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'STORE', tmp_path)
    monkeypatch.setattr(main, 'STORE', tmp_path)
    main.jobs.clear()
    main.job_cancels.clear()
    main.API_KEYS.clear()
    agent.SETTINGS = agent.ModelSettings()


def wait(client, key):
    until = time.monotonic()+15
    while time.monotonic()<until:
        result=client.get('/api/jobs/'+key).json()
        if result['status'] != 'running':
            return result
        time.sleep(.05)
    pytest.fail('job did not finish')


def test_preferences_restore_without_keys(tmp_path):
    settings=agent.ModelSettings(provider='custom',base_url='https://example.com/v1',model='vision-model',api_key='SECRET',enabled=True)
    model_preferences.save(tmp_path,settings)
    assert 'SECRET' not in (tmp_path/'preferences/model-settings.json').read_text()
    restored=model_preferences.load(tmp_path,agent.ModelSettings)
    assert restored.model=='vision-model' and not restored.api_key and not restored.enabled
    settings.connection='account'
    settings.provider='openai'
    model_preferences.save(tmp_path,settings)
    assert model_preferences.load(tmp_path,agent.ModelSettings).enabled
    settings.base_url='https://example.com/v1?key=SECRET'
    with pytest.raises(ValueError,match='地址'):
        model_preferences.save(tmp_path,settings)


@pytest.mark.parametrize('style',['responses','chat','anthropic'])
def test_visual_revision_sends_image_and_returns_diff_without_execution(style,monkeypatch,tmp_path):
    folder=tmp_path/'runs/123456abcdef'
    folder.mkdir(parents=True)
    png=b'PNG-test-contents'
    (folder/'figure.png').write_bytes(png)
    core.write_json(folder/'manifest.json',{'figure_style':{'base_size_pt':12},'plot_settings':{'width_mm':85}})
    (folder/'figure-style.R').write_text('# frozen style helper',encoding='utf-8')
    agent.SETTINGS=agent.ModelSettings(enabled=True,api_style=style,model='vision-test')
    seen=[]
    def fake(body):
        seen.append(body)
        result=json.dumps({'action':'render','message':'改标题','spec_json':'x <- 1\n# new title'})
        return {'output':[{'type':'message','content':[{'type':'output_text','text':result}]}]} if style=='responses' else {'choices':[{'message':{'content':result}}]}
    monkeypatch.setattr(agent,'http_request',fake)
    r=agent.revise_code('x <- 1\n# old title','改标题','r','123456abcdef',True)
    assert base64.b64encode(png).decode() in json.dumps(seen)
    assert 'frozen style helper' in json.dumps(seen)
    assert r['base_code']=='x <- 1\n# old title' and r['run'] is None and r['image_reviewed']
    assert r['changes']==[{'old_start':2,'new_start':2,'removed':['# old title'],'added':['# new title']}]
    assert not (folder/'figure.R').exists()


def test_anthropic_image_conversion(monkeypatch):
    captured=[]
    class Response:
        is_error=False
        def json(self):return {'content':[{'type':'text','text':'ok'}]}
    def post(url,**kwargs):
        captured.append(kwargs['json'])
        return Response()
    monkeypatch.setattr(task_control,'post',post)
    agent.SETTINGS=agent.ModelSettings(provider='claude',api_style='anthropic',base_url='https://api.anthropic.com/v1',model='test')
    agent.http_request({'messages':[{'role':'user','content':[{'type':'text','text':'look'},{'type':'image_url','image_url':{'url':'data:image/png;base64,AAAA'}}]}]})
    assert captured[0]['messages'][0]['content'][1]=={'type':'image','source':{'type':'base64','media_type':'image/png','data':'AAAA'}}


def test_cancel_real_owned_subprocess_and_accept_next_job(tmp_path):
    client=TestClient(main.app)
    ready=tmp_path/'ready'
    late=tmp_path/'must-not-exist'
    code="from pathlib import Path; import time; Path('ready').write_text('ready'); time.sleep(30); Path('must-not-exist').write_text('bad')"
    def execute(key,request):
        task_control.run([sys.executable,'-c',code],cwd=tmp_path,text=True,timeout=40)
        main.jobs[key].update(status='complete')
    key=main.start_job(execute,None)['job_id']
    deadline=time.monotonic()+5
    while not ready.exists() and time.monotonic()<deadline:time.sleep(.05)
    assert ready.exists()
    assert client.post('/api/jobs/'+key+'/cancel',json={}).status_code==200
    assert wait(client,key)['status']=='cancelled'
    assert not late.exists()
    assert main.jobs[key]['finished_at']>=main.jobs[key]['created_at']
    def complete(key,request):main.jobs[key].update(status='complete')
    next_key=main.start_job(complete,None)['job_id']
    assert wait(client,next_key)['status']=='complete'


def test_cancel_pending_http_closes_request(monkeypatch):
    started=threading.Event();closed=threading.Event();cancel=threading.Event()
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):closed.set()
        async def post(self,*args,**kwargs):
            started.set()
            await asyncio.sleep(30)
    monkeypatch.setattr(task_control.httpx,'AsyncClient',Client)
    errors=[]
    def worker():
        try:
            with task_control.scope(cancel):task_control.post('https://example.com')
        except task_control.Cancelled:errors.append('cancelled')
    thread=threading.Thread(target=worker);thread.start()
    assert started.wait(3)
    cancel.set();thread.join(3)
    assert not thread.is_alive() and closed.is_set() and errors==['cancelled']


def test_transpose_preview_rejects_duplicates_preserves_original_and_pca():
    client=TestClient(main.app)
    frame=pd.DataFrame({'gene':['G1','G2','G3'],'A':[1,2,8],'B':[4,3,9],'C':[6,9,5],'D':[9,5,7]})
    raw=frame.to_csv(index=False).encode()
    meta=core.store_dataset(raw,'genes.csv',True)
    body={'label':'gene','columns':['A','B','C','D']}
    response=client.post('/api/datasets/'+meta['id']+'/transpose-preview',json=body)
    assert response.status_code==200 and response.json()['rows']==4 and response.json()['features']==3
    assert len(core.list_records('datasets'))==1
    new=client.post('/api/datasets/'+meta['id']+'/transpose',json=body).json()
    data,_=core.load_dataset(new['id'])
    assert data['sample_id'].tolist()==['A','B','C','D']
    assert np.array_equal(data.iloc[:,1:].values,frame.iloc[:,1:].values.T)
    assert new['provenance']['parent_sha256']==meta['sha256']
    assert client.get('/api/datasets/'+meta['id']+'/original').content==raw
    spec=core.PlotSpec(**new['demo_spec'])
    with pytest.raises(ValueError,match='矩阵方向'):
        core.validate_spec(data,spec.model_copy(update={'matrix_orientation':''}))
    result=core.render(new['id'],spec)
    assert result['report']['analyzed_rows']==4
    assert result['report']['data_provenance']['parent_dataset_id']==meta['id']
    frame.loc[1,'gene']='G1'
    duplicate=core.store_dataset(frame.to_csv(index=False).encode(),'duplicate.csv')
    with pytest.raises(ValueError,match='重复'):
        matrix_input.preview(duplicate['id'],'gene',body['columns'])


def test_transpose_exclusions_applied_after_sample_orientation():
    frame=pd.DataFrame({'gene':['G1','G2','G3'],'HNSCC3_HD':[99,99,99],'HNSCC3_T':[98,98,98],'HNSCC3_LD':[1,3,5],'A':[3,5,1],'B':[9,4,5]})
    meta=core.store_dataset(frame.to_csv(index=False).encode(),'exvivo-matrix.csv')
    new=matrix_input.create(meta['id'],'gene',list(frame.columns[1:]))
    data,_=core.load_dataset(new['id'])
    spec=core.PlotSpec(**new['demo_spec'],exvivo=True)
    selected,report=core.validate_spec(data,spec)
    assert report['excluded_rows']==2 and 'HNSCC3_LD' in selected.sample_id.tolist()
    assert len(core.load_dataset(meta['id'])[0].columns)==6
