import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import agent
import accounts
import core
import main
from bio import BIO_CATALOG, demo_recipe


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "STORE", tmp_path)
    main.jobs.clear()
    main.API_KEYS.clear()
    agent.SETTINGS = agent.ModelSettings()
    agent.HISTORY.clear()


@pytest.mark.parametrize("chart", list(BIO_CATALOG))
def test_new_single_charts_render_from_real_data(chart):
    client = TestClient(main.app)
    dataset = client.post(f"/api/demo/{chart}", json={}).json()
    spec = core.PlotSpec.model_validate(dataset["demo_spec"])
    result = core.render(dataset["id"], spec)
    assert result["status"] == "complete"
    assert isinstance(result["stats"], list)
    assert result["stats"]
    assert result["figure_style"]["base_size_pt"] == 12
    assert result["figure_style"]["axis_text_pt"] == pytest.approx(9.6)
    assert (core.located("runs", result["id"]) / "figure-style.R").exists()
    folder = core.located("runs", result["id"])
    for name in ("figure.pdf", "figure.svg", "figure.png", "statistics.csv", "figure.R", "source_data.csv", "reproduce.zip"):
        assert (folder / name).stat().st_size > 20
    if chart == "volcano":
        assert sum(r["genes"] for r in result["stats"]) == 150
    if chart == "missingness":
        assert result["report"]["missing_rows"] == 0
        assert sum(r["missing"] for r in result["stats"]) == 13
    if chart == "paired_delta":
        frame, _, _ = demo_recipe(chart)
        wide = frame.pivot(index="pair", columns="group", values="value")
        assert result["stats"][0]["mean_delta"] == pytest.approx((wide.After - wide.Before).mean())
        assert result["stats"][0]["n_pairs"] == 12
    if chart == "lr_dot":
        frame, _, _ = demo_recipe(chart)
        assert len(result["stats"]) == len(frame)
        assert {row["label"] for row in result["stats"]} == set(frame.gene)
    if chart == "upset":
        frame, _, _ = demo_recipe(chart)
        assert sum(r["count"] for r in result["stats"]) == int(frame.any(axis=1).sum())


def test_pairs_reject_duplicates_and_missing():
    frame, columns, options = demo_recipe("paired")
    spec = core.PlotSpec(chart="paired", columns=columns, **options)
    with pytest.raises(ValueError, match="重复"):
        core.validate_spec(pd.concat([frame, frame.head(1)]), spec)
    frame.loc[0, "value"] = np.nan
    with pytest.raises(ValueError, match="缺失"):
        core.validate_spec(frame, spec)


def test_exvivo_scatter_computes_scc_and_pcc_separately():
    frame = pd.DataFrame({"sample": ["HNSCC3_HD", "GSM9266346_HNSCC3_T", "HNSCC3_LD", "A", "B", "C", "D"], "x": [100, 100, 1, 2, 3, 4, 5], "y": [-100, -100, 2, 1, 5, 4, 8]})
    dataset = core.store_dataset(frame.to_csv(index=False).encode(), "exvivo.csv")
    result = core.render(dataset["id"], core.PlotSpec(chart="scatter", columns={"x": "x", "y": "y"}, exvivo=True))
    assert result["report"]["excluded_rows"] == 2
    assert {r["method"] for r in result["stats"]} == {"pearson", "spearman"}
    assert all(r["n"] == 5 for r in result["stats"])
    for row in result["stats"]:
        assert row["r"] == pytest.approx(frame.iloc[2:].x.corr(frame.iloc[2:].y, method=row["method"]))


def test_platform_keys_do_not_cross_providers():
    client = TestClient(main.app)
    client.post("/api/settings", json={"provider": "deepseek", "base_url": "https://api.deepseek.com", "api_key": "platform-a-key"})
    client.post("/api/settings", json={"provider": "glm", "base_url": "https://open.bigmodel.cn/api/paas/v4", "api_key": ""})
    assert agent.SETTINGS.api_key == ""
    assert "platform-a-key" not in client.get("/api/state").text
    assert client.post("/api/settings", json={"provider": "qwen", "connection": "account"}).status_code == 400


def test_account_planner_executes_local_validated_recipe(monkeypatch):
    dataset = main.chart_demo("volcano")
    spec = core.PlotSpec.model_validate(dataset["demo_spec"])
    monkeypatch.setattr(accounts, "planner", lambda *args, **kwargs: {"action": "render", "message": "使用已有差异结果", "spec_json": spec.model_dump_json()})
    agent.SETTINGS = agent.ModelSettings(provider="openai", connection="account", enabled=True)
    result = agent.model_turn(dataset["id"], "画火山图", spec, lambda *args, **kwargs: None)
    assert result["run"]["status"] == "complete"
    assert result["mode"] == "account"


def test_custom_recipe_does_not_accept_code():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        core.PlotSpec(chart="custom", code="system('anything')")


def test_pca_row_scaling_matches_independent_svd():
    frame, columns, _ = demo_recipe("pca")
    dataset = core.store_dataset(frame.to_csv(index=False).encode(), "pca.csv")
    result = core.render(dataset["id"], core.PlotSpec(chart="pca", columns=columns, scaling="row_z", matrix_orientation="samples"))
    m = frame[columns["predictors"]].to_numpy()
    z = (m - m.mean(axis=1, keepdims=True)) / m.std(axis=1, ddof=1, keepdims=True)
    singular = np.linalg.svd(z - z.mean(axis=0), compute_uv=False)
    expected = singular ** 2 / np.sum(singular ** 2)
    assert result["stats"][0]["variance_explained"] == pytest.approx(expected[0])


def test_anthropic_api_translates_tool_roundtrip(monkeypatch):
    captured = {}
    class Response:
        is_error = False
        def json(self):
            return {"content": [{"type": "tool_use", "id": "t2", "name": "inspect_dataset", "input": {}}]}
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            return Response()
    monkeypatch.setattr(agent.httpx, "Client", Client)
    agent.SETTINGS = agent.ModelSettings(provider="claude", api_style="anthropic", base_url="https://api.anthropic.com/v1", model="user-selected-model", api_key="test-secret")
    body = {"model": "user-selected-model", "messages": [{"role": "system", "content": "system"}, {"role": "user", "content": "inspect"}, {"role": "assistant", "content": None, "tool_calls": [{"id": "t1", "function": {"name": "inspect_dataset", "arguments": "{}"}}]}, {"role": "tool", "tool_call_id": "t1", "content": "{}"}]}
    result = agent.http_request(body)
    assert captured["url"].endswith("/v1/messages")
    assert captured["json"]["messages"][-1]["content"][0]["type"] == "tool_result"
    assert captured["json"]["messages"][-1]["content"][0]["tool_use_id"] == "t1"
    assert result["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "inspect_dataset"


def test_nonlocal_http_model_endpoint_blocked():
    agent.SETTINGS = agent.ModelSettings(base_url="http://localhost.attacker.example/v1")
    with pytest.raises(ValueError, match="HTTPS"):
        agent.http_request({})
