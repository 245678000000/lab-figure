"""Integration tests use real R/Python renderers and mocked model HTTP responses."""
import io
import json
from pathlib import Path
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import agent
import core
import main


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "STORE", tmp_path)
    monkeypatch.setattr(main, "STORE", tmp_path)
    main.jobs.clear()
    agent.HISTORY.clear()
    agent.SETTINGS = agent.ModelSettings()


def specs():
    common = {"group": "group", "value": "score", "outcome": "response", "predictor": "score", "time": "time_months", "event": "event", "predictors": ["score", "marker_b"]}
    return [core.PlotSpec(chart=chart, columns=common, positive="1") for chart in list(core.CATALOG)[:9]]


@pytest.mark.parametrize("spec", specs(), ids=list(core.CATALOG)[:9])
def test_all_nine_r_templates(spec):
    d = core.demo_dataset()
    result = core.render(d["id"], spec)
    assert result["status"] == "complete"
    assert result["report"]["analyzed_rows"] == 72
    folder = core.located("runs", result["id"])
    for name in ("figure.pdf", "figure.png", "figure.svg", "figure.R", "source_data.csv", "manifest.json", "reproduce.zip"):
        assert (folder / name).stat().st_size > 50
    assert len(result["qa"]) == 3
    if spec.chart == "roc":
        assert 0 < result["stats"][0]["auc"] < 1


def test_python_r_roc_same_statistics():
    dataset = core.demo_dataset()
    spec = specs()[0]
    r = core.render(dataset["id"], spec)
    py = core.render(dataset["id"], spec.model_copy(update={"engine": "python"}))
    assert r["stats"][0]["auc"] == pytest.approx(py["stats"][0]["auc"], abs=1e-10)


def test_title_revision_preserves_stats_and_pdfs():
    dataset = core.demo_dataset()
    original = core.render(dataset["id"], specs()[0])
    revised = core.render(dataset["id"], specs()[0].model_copy(update={"title": "预测能力验证", "size": "wide", "show_n": False}))
    assert revised["stats"][0]["auc"] == original["stats"][0]["auc"]
    assert (core.located("runs", revised["id"]) / "session-info.txt").exists()
    assert all(q["verdict"] == "PASS" for q in original["qa"])


def test_exclusions_exact_and_recomputed():
    frame = pd.DataFrame({"sample_id": ["HNSCC3_HD", "hnscc3.hd", "GSM9266346_HNSCC3_T", "HNSCC3_tumor", "HNSCC3_LD", "A", "B", "C"],
                          "response": [1, 0, 1, 0, 1, 0, 1, 0], "score": [9, 9, 9, 9, 5, 2, 3, 4]})
    d = core.store_dataset(frame.to_csv(index=False).encode(), "exvivo.csv")
    spec = core.PlotSpec(columns={"outcome": "response", "predictor": "score"}, positive="1", exvivo=True)
    result = core.render(d["id"], spec)
    assert result["report"]["excluded_rows"] == 4
    assert result["report"]["analyzed_rows"] == 4
    assert result["stats"][0]["n"] == 4
    analyzed = pd.read_csv(core.located("runs", result["id"]) / "source_data.csv")
    assert "HNSCC3_LD" in analyzed.sample_id.to_list()
    assert len(core.load_dataset(d["id"])[0]) == 8


def test_ambiguous_positive_and_invalid_numeric_blocked():
    d = core.demo_dataset()
    with pytest.raises(ValueError, match="阳性"):
        core.render(d["id"], core.PlotSpec(columns={"outcome": "response", "predictor": "score"}))
    with pytest.raises(ValueError, match="数值"):
        core.render(d["id"], core.PlotSpec(columns={"outcome": "response", "predictor": "group"}, positive="1"))


def test_xlsx_sheet_header_and_api_file_isolation():
    content = io.BytesIO()
    with pd.ExcelWriter(content, engine="openpyxl") as writer:
        pd.DataFrame({"group": ["A", "B", "A"], "score": [1, 2, 3]}).to_excel(writer, sheet_name="Cohort", startrow=1, index=False)
    client = TestClient(main.app)
    d = client.post("/api/datasets", files={"file": ("data.xlsx", content.getvalue())}).json()
    response = client.post(f"/api/datasets/{d['id']}/reload", json={"sheet": "Cohort", "header": 2})
    assert response.status_code == 200
    assert response.json()["summary"]["rows"] == 3
    assert response.json()["summary"]["columns"][0]["name"] == "group"
    assert client.get(f"/api/datasets/{d['id']}/original").content == content.getvalue()
    assert client.get("/api/runs/../../files/settings.json").status_code == 404
    assert client.post("/api/demo", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/state", headers={"Host": "evil.example"}).status_code == 403


def test_model_responses_tool_loop(monkeypatch):
    d = core.demo_dataset()
    spec = specs()[0]
    requests = []
    def fake(body):
        requests.append(json.loads(json.dumps(body)))
        if len(requests) == 1:
            return {"output": [{"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "render_figure", "arguments": spec.model_dump_json()}]}
        return {"output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "已计算 ROC，见统计表。"}]}]}
    monkeypatch.setattr(agent, "http_request", fake)
    agent.SETTINGS = agent.ModelSettings(enabled=True, model="test-model")
    result = agent.model_turn(d["id"], "画 ROC", spec, lambda *args, **kwargs: None)
    assert result["run"]["status"] == "complete"
    assert requests[1]["input"][-1]["type"] == "function_call_output"
    assert "preview" not in requests[0]["input"][0]["content"]


def test_model_chat_tool_loop(monkeypatch):
    d = core.demo_dataset()
    spec = specs()[0]
    requests = []
    def fake(body):
        requests.append(json.loads(json.dumps(body)))
        if len(requests) == 1:
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "inspect_dataset", "arguments": "{}"}}]}}]}
        return {"choices": [{"message": {"role": "assistant", "content": "请明确你的阳性类别。"}}]}
    monkeypatch.setattr(agent, "http_request", fake)
    agent.SETTINGS = agent.ModelSettings(enabled=True, api_style="chat", model="test-model")
    result = agent.model_turn(d["id"], "检查数据", spec, lambda *args, **kwargs: None)
    assert "阳性" in result["message"]
    assert requests[1]["messages"][-1]["role"] == "tool"


def test_template_chat_job_and_secret_not_exposed():
    client = TestClient(main.app)
    dataset = client.post("/api/demo").json()
    response = client.post("/api/chat", json={"dataset_id": dataset["id"], "text": "生成 ROC", "spec": specs()[0].model_dump(), "direct": True})
    assert response.status_code == 200
    key = response.json()["job_id"]
    for _ in range(100):
        job = client.get(f"/api/jobs/{key}").json()
        if job["status"] != "running":
            break
        time.sleep(.1)
    assert job["status"] == "complete", job
    settings = client.post("/api/settings", json={"api_key": "sentinel-secret", "model": "test", "enabled": True}).json()
    assert "sentinel-secret" not in json.dumps(settings)
    assert "sentinel-secret" not in client.get("/api/state").text
    client.post("/api/settings/disconnect")
    assert not agent.SETTINGS.api_key
