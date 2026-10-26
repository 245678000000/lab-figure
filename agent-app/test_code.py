"""Editor integration: real code execution, immutable history, and draft-only model edits."""
import json
import re
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
import agent
import core
import main


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'STORE', tmp_path)
    monkeypatch.setattr(main, 'STORE', tmp_path)
    main.jobs.clear()
    agent.SETTINGS = agent.ModelSettings()


def original(engine='r'):
    d = core.demo_dataset()
    return core.render(d['id'], core.PlotSpec(engine=engine, columns={'outcome':'response','predictor':'score'}, positive='1'))


@pytest.mark.parametrize('engine', ['r','python'])
def test_editor_reexecutes_and_keeps_parent(engine):
    parent = original(engine)
    folder = core.located('runs', parent['id'])
    files = {p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
    if engine == 'r':
        code = parent['code'].replace('finish(p', 'p <- p + ggplot2::labs(title="Edited code preview")\nfinish(p', 1)
    else:
        code = parent['code'].replace('finish(fig', 'fig.axes[0].set_title("Edited code preview")\nfinish(fig', 1)
    revised = core.render_code(parent['id'], code)
    assert revised['parent_run_id'] == parent['id']
    assert revised['execution_mode'] == 'edited'
    assert revised['code'] == code
    assert revised['stats'][0]['auc'] == parent['stats'][0]['auc']
    output = core.located('runs', revised['id'])
    assert (output/'figure.png').read_bytes() != files['figure.png']
    assert (output/'source_data.csv').read_bytes() == files['source_data.csv']
    assert all((folder/name).read_bytes() == data for name,data in files.items())
    with zipfile.ZipFile(output/'reproduce.zip') as bundle:
        assert bundle.read(revised['code_file']).decode('utf-8') == code
        assert json.loads(bundle.read('manifest.json'))['code_sha256'] == revised['code_sha256']


def test_editor_error_missing_exports_and_no_stale_stats():
    parent = original()
    with pytest.raises(ValueError, match='作图失败'):
        core.render_code(parent['id'], 'stop("Deliberate editor error")')
    with pytest.raises(ValueError, match='未生成所需文件'):
        core.render_code(parent['id'], 'print("No exports")')
    # A hand-written script that omits stats must not inherit its parent's numbers.
    code = re.sub(r'^finish\(p.*$', 'save_fig(p, "figure", dir = ".", formats = c("pdf", "png", "svg"))', parent['code'], flags=re.M)
    result = core.render_code(parent['id'], code)
    assert result['stats'] == []
    assert core.read_json(core.located('runs',parent['id'])/'manifest.json')['status'] == 'complete'


def test_editor_uses_prior_selection_snapshot():
    d = core.store_dataset(b'sample_id,response,score\nHNSCC3_HD,1,99\nHNSCC3_tumor,0,99\nHNSCC3_LD,1,8\nA,0,2\nB,1,6\nC,0,3\n','exvivo.csv')
    parent = core.render(d['id'], core.PlotSpec(columns={'outcome':'response','predictor':'score'}, positive='1', exvivo=True))
    dataset_folder = core.located('datasets', d['id'])
    meta = core.read_json(dataset_folder/'metadata.json')
    # A later reload/input revision must not silently replace the parent's selected input.
    (dataset_folder/meta['original']).write_text('other\nchanged\n',encoding='utf-8')
    result = core.render_code(parent['id'], parent['code'])
    csv = (core.located('runs',result['id'])/'source_data.csv').read_text()
    assert 'HNSCC3_LD' in csv and 'HNSCC3_HD' not in csv and 'HNSCC3_tumor' not in csv
    assert result['report']['excluded_rows'] == 2
    assert result['stats'][0]['n'] == 4


def job_result(client, key):
    until = time.monotonic()+25
    while time.monotonic()<until:
        value = client.get('/api/jobs/'+key).json()
        if value['status']!='running':
            return value
        time.sleep(.05)
    pytest.fail('Job did not finish')


def test_code_api_and_model_draft_does_not_execute(monkeypatch):
    parent = original()
    client = TestClient(main.app)
    body = {'parent_run_id':parent['id'], 'code':parent['code']}
    assert client.post('/api/code/run',json=body,headers={'Origin':'https://other.example'}).status_code == 403
    assert client.post('/api/code/run',json={**body,'code':''}).status_code == 422
    response = client.post('/api/code/run',json=body)
    main.jobs['held']={'status':'running','events':[]}
    assert client.post('/api/code/run',json=body).status_code == 400
    main.jobs.pop('held')
    assert job_result(client,response.json()['job_id'])['status']=='complete'
    agent.SETTINGS = agent.ModelSettings(enabled=True,connection='account',provider='openai')
    monkeypatch.setattr(agent.accounts,'planner',lambda *args:{'action':'render','message':'修改了标题','spec_json':'stop("Not executed")'})
    before = len(core.list_records('runs'))
    r = client.post('/api/code/revise',json={**body,'text':'修改标题'})
    result = job_result(client,r.json()['job_id'])
    assert result['status']=='complete'
    assert result['result']['draft_code']=='stop("Not executed")'
    assert len(core.list_records('runs')) == before

@pytest.mark.parametrize('engine,code,line,exact,hint', [
    ('r', 'x <- 1\ny <- )\n', 2, True, '语法错误'),
    ('r', 'x <- 1\ny <- does_not_exist\n', 2, False, '变量或函数'),
    ('python', 'x = 1\ny = )\n', 2, True, '语法错误'),
    ('python', 'x = 1\ny = does_not_exist\n', 2, True, '变量或函数'),
])
def test_editor_diagnostics(engine, code, line, exact, hint):
    parent = original(engine)
    client = TestClient(main.app)
    response = client.post('/api/code/run', json={'parent_run_id':parent['id'], 'code':code})
    result = job_result(client, response.json()['job_id'])
    assert result['status'] == 'error'
    assert result['diagnostic']['line'] == line
    assert result['diagnostic']['exact'] == exact
    assert hint in result['diagnostic']['hint']
    assert core.read_json(core.located('runs',parent['id'])/'manifest.json')['status'] == 'complete'
