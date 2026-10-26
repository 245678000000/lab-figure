import json
import zipfile
import pytest
from fastapi.testclient import TestClient
import core
import main
from bio import demo_recipe


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(core,'STORE',tmp_path)
    monkeypatch.setattr(main,'STORE',tmp_path)
    main.jobs.clear()
    main.job_cancels.clear()


def test_pca_outputs_in_new_and_historical_downloads():
    d,columns,options=demo_recipe('pca')
    meta=core.store_dataset(d.to_csv(index=False).encode(),'pca.csv',True)
    result=core.render(meta['id'],core.PlotSpec(chart='pca',columns=columns,**options))
    folder=core.located('runs',result['id'])
    client=TestClient(main.app)
    for name in ['pca_coordinates.csv','pca_loadings.csv']:
        response=client.get(f"/api/runs/{result['id']}/files/{name}")
        assert response.status_code==200
        assert response.content==(folder/name).read_bytes()
    with zipfile.ZipFile(folder/'reproduce.zip') as z:
        assert {'pca_coordinates.csv','pca_loadings.csv'} <= set(z.namelist())
    original=(folder/'figure.png').read_bytes()
    manifest=(folder/'manifest.json').read_bytes()
    # Simulate the old bundle, keeping genuine existing output files.
    with zipfile.ZipFile(folder/'reproduce.zip','w') as z:
        z.writestr('figure.png',original)
    response=client.get(f"/api/runs/{result['id']}/files/reproduce.zip")
    import io
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert z.read('pca_loadings.csv')==(folder/'pca_loadings.csv').read_bytes()
    assert (folder/'figure.png').read_bytes()==original
    assert (folder/'manifest.json').read_bytes()==manifest


def test_dataset_lookup_for_history_outside_recent_list():
    meta=core.demo_dataset()
    response=TestClient(main.app).get('/api/datasets/'+meta['id'])
    assert response.status_code==200
    assert response.json()['id']==meta['id']


def test_job_retains_origin_context(monkeypatch):
    import threading
    monkeypatch.setattr(threading.Thread,'start',lambda self:None)
    d=core.demo_dataset()
    req=main.ChatRequest(dataset_id=d['id'],text='generate',spec=core.PlotSpec(),direct=True)
    key=main.start_job(main.execute_job,req)['job_id']
    assert main.jobs[key]['context']['dataset_id']==d['id']
