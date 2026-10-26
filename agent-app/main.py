from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import threading
import time
import uuid

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agent
import accounts
import preferences
import task_control
import model_preferences
import matrix_input
from core import ARTIFACT_FILES, build_bundle
from recognition import recognize_frame
from core import CATALOG, ROOT, STORE, PlotSpec, demo_dataset, list_records, load_dataset, located, read_json, read_table, render, render_code, store_dataset, summarize, write_json
from bio import BIO_CATALOG, demo_recipe
from figure_edit import FigureEdits
from connection_info import connection_info

app = FastAPI(title="AISI-figure", docs_url=None, redoc_url=None)
jobs = {}
job_cancels = {}
API_KEYS = {}
lock = threading.Lock()
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "testserver"}


@app.middleware("http")
async def local_only(request: Request, call_next):
    from fastapi.responses import JSONResponse
    if request.url.hostname not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "只允许本机访问"}, status_code=403)
    origin = request.headers.get("origin")
    if request.method != "GET" and origin:
        from urllib.parse import urlparse
        if urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "拒绝跨站请求"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ValueError)
async def value_error(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/api/state")
def state():
    return {"datasets": list_records("datasets"), "runs": list_records("runs"), "catalog": CATALOG,
            "settings": agent.public_settings(), "providers": accounts.PROVIDERS, "workspace": str(STORE),
            "active_job": next((key for key,j in jobs.items() if j['status']=='running'), None)}


class MatrixRequest(BaseModel):
    label: str
    columns: list[str] = Field(min_length=2, max_length=50000)


@app.post('/api/datasets/{key}/transpose-preview')
def transpose_preview(key: str, request: MatrixRequest):
    return matrix_input.preview(key, request.label, request.columns)


@app.post('/api/datasets/{key}/transpose')
def transpose_dataset(key: str, request: MatrixRequest):
    return matrix_input.create(key, request.label, request.columns)


@app.get("/api/colors")
def group_colors():
    return {"colors":preferences.read_colors(STORE)}


class ColorUpdates(BaseModel):
    colors: dict[str,str]


@app.post("/api/colors")
def save_group_colors(request: ColorUpdates):
    return {"colors":preferences.update_colors(STORE,request.colors)}


class ColorPreparation(BaseModel):
    dataset_id: str
    column: str


@app.post("/api/colors/prepare")
def prepare_group_colors(request: ColorPreparation):
    data,_=load_dataset(request.dataset_id)
    if request.column not in data:
        raise ValueError("分组列不存在")
    selected=preferences.allocate_colors(STORE,data[request.column].dropna().unique())
    return {"colors":preferences.read_colors(STORE),"selected":list(selected)}


@app.get("/api/datasets/{key}/recognition")
def identify_dataset(key:str):
    data,_=load_dataset(key)
    return recognize_frame(data)


@app.get('/api/datasets/{key}')
def dataset_record(key: str):
    return read_json(located('datasets', key) / 'metadata.json')


@app.post("/api/datasets")
async def upload(file: UploadFile = File(...)):
    content = await file.read(100 * 1024 * 1024 + 1)
    if len(content) > 100 * 1024 * 1024:
        raise ValueError("文件最大支持 100 MB")
    return await asyncio.to_thread(store_dataset, content, file.filename or "data.csv")


@app.post("/api/demo")
def demo():
    return demo_dataset()


@app.post("/api/demo/{chart}")
def chart_demo(chart: str):
    if chart not in CATALOG:
        raise ValueError("图型不存在")
    if chart in BIO_CATALOG:
        frame, columns, options = demo_recipe(chart)
        metadata = store_dataset(frame.to_csv(index=False).encode("utf-8"), f"demo_{chart}.csv", True)
        spec = PlotSpec(chart=chart, columns=columns, **options)
    else:
        metadata = demo_dataset()
        spec = PlotSpec(chart=chart, positive="1", columns={"group": "group", "value": "score", "outcome": "response", "predictor": "score", "time": "time_months", "event": "event", "predictors": ["score", "marker_b"]})
    metadata["demo_spec"] = spec.model_dump()
    write_json(located("datasets", metadata["id"]) / "metadata.json", metadata)
    return metadata


class Reload(BaseModel):
    sheet: str | None = None
    header: int = Field(default=1, ge=1, le=30)


@app.post("/api/datasets/{key}/reload")
def reload_dataset(key: str, request: Reload):
    folder = located("datasets", key)
    meta = read_json(folder / "metadata.json")
    if meta.get('provenance') and (request.header != meta['header'] or request.sheet != meta['sheet']):
        raise ValueError('处理副本的表头已固定，请在原始上传文件中调整工作表或表头')
    d, sheets, sheet = read_table(folder / meta["original"], request.sheet, request.header,
                                 string_columns=meta.get('id_columns'))
    meta.update(summary=summarize(d), sheets=sheets, sheet=sheet, header=request.header, recognition=recognize_frame(d))
    write_json(folder / "metadata.json", meta)
    agent.HISTORY.pop(key, None)
    return meta


@app.get("/api/datasets/{key}/original")
def original_file(key: str):
    folder = located("datasets", key)
    meta = read_json(folder / "metadata.json")
    return FileResponse(folder / meta["original"], filename=meta["filename"])


@app.post("/api/settings")
def configure(settings: agent.ModelSettings):
    if jobs and any(j["status"] == "running" for j in jobs.values()):
        raise ValueError("作图任务运行中，请完成后再修改连接设置")
    if settings.provider not in accounts.PROVIDERS:
        raise ValueError("未知模型平台")
    if settings.connection == "account" and not accounts.PROVIDERS[settings.provider]["account"]:
        raise ValueError("此平台需要 API / 订阅密钥，不能通过普通网页账号直接调用")
    identity = (settings.provider, settings.base_url.rstrip("/"))
    model_preferences.save(STORE, settings)
    if settings.api_key:
        API_KEYS[identity] = settings.api_key
    elif settings.connection == "api":
        settings.api_key = API_KEYS.get(identity, "")
    agent.SETTINGS = settings
    return agent.public_settings()


@app.post("/api/settings/disconnect")
def disconnect():
    if any(j["status"] == "running" for j in jobs.values()):
        raise ValueError("请等待当前任务完成")
    agent.SETTINGS = agent.SETTINGS.model_copy(update={'enabled':False, 'api_key':''})
    model_preferences.save(STORE, agent.SETTINGS)
    API_KEYS.clear()
    agent.HISTORY.clear()
    return agent.public_settings()


@app.post("/api/settings/test")
def connection_test():
    return agent.test_connection()


@app.get("/api/accounts/{provider}/status")
def account_state(provider: str):
    return accounts.account_status(provider)


@app.get('/api/connection/info')
def current_connection_info():
    return connection_info(agent.SETTINGS.model_copy())


@app.post("/api/accounts/{provider}/login")
def login(provider: str):
    return accounts.start_login(provider)


@app.get("/api/account-logins/{key}")
def login_state(key: str):
    if key not in accounts.LOGIN:
        raise HTTPException(404, "登录会话不存在")
    return accounts.LOGIN[key]


class ChatRequest(BaseModel):
    dataset_id: str
    text: str = Field(min_length=1, max_length=5000)
    spec: PlotSpec
    direct: bool = False


class CodeRequest(BaseModel):
    parent_run_id: str = Field(pattern=r"^[a-f0-9]{12}$")
    code: str = Field(min_length=1, max_length=200000)


class CodeRevisionRequest(CodeRequest):
    text: str = Field(min_length=1, max_length=5000)
    include_image: bool = False


class FigureEditRequest(CodeRequest):
    edits: FigureEdits


def job_worker(key, target, request):
    def emit(message, stage, **extra):
        jobs[key]['events'].append({'message':message, 'stage':stage, 'at':time.time(), **extra})
    try:
        with task_control.scope(job_cancels[key], emit):
            target(key, request)
    except task_control.Cancelled as exc:
        jobs[key].update(status='cancelled', message=str(exc))
    finally:
        jobs[key]['finished_at'] = time.time()
        job_cancels.pop(key, None)


def start_job(target, request):
    context = {}
    if getattr(request, 'dataset_id', None) and not isinstance(request, ChatRequest):
        context = {'dataset_id':request.dataset_id, 'kind':'analysis'}
    elif isinstance(request, ChatRequest):
        context = {'dataset_id':request.dataset_id}
    elif isinstance(request, CodeRequest):
        parent = read_json(located('runs', request.parent_run_id) / 'manifest.json')
        context = {'dataset_id':parent['dataset_id'], 'parent_run_id':request.parent_run_id}
    with lock:
        if any(j['status']=='running' for j in jobs.values()):
            raise ValueError('当前有一个任务正在运行，请完成或停止后再试')
        for old in list(jobs)[:-99]:
            if jobs[old]['status'] != 'running':
                jobs.pop(old)
        key = uuid.uuid4().hex[:12]
        jobs[key] = {'status':'running','events':[], 'created_at':time.time(), 'cancel_requested':False, 'context':context}
        job_cancels[key] = threading.Event()
    threading.Thread(target=job_worker, args=(key,target,request), daemon=True).start()
    return {'job_id':key}


def execute_code_job(key, request):
    try:
        if isinstance(request, CodeRevisionRequest):
            jobs[key]["events"].append({"message": "模型正在修改当前代码", "stage": "model", "at": time.time()})
            parent = read_json(located("runs", request.parent_run_id) / "manifest.json")
            answer = agent.revise_code(request.code, request.text, parent["spec"]["engine"], request.parent_run_id, request.include_image)
        else:
            jobs[key]["events"].append({"message": "运行编辑后的代码并更新图片", "stage": "render", "at": time.time()})
            result = render_code(request.parent_run_id, request.code, figure_edits=request.edits.model_dump() if isinstance(request, FigureEditRequest) else None)
            answer = {"message": "已运行编辑后的代码，图片与代码保存为新版本。", "run": result, "mode": "edited"}
        with lock:
            task_control.check()
            jobs[key].update(status="complete", result=answer)
    except task_control.Cancelled:
        raise
    except Exception as exc:
        message = str(exc)
        if agent.SETTINGS.api_key:
            message = message.replace(agent.SETTINGS.api_key, "[redacted]")
        jobs[key].update(status="error", error=message[:4000])
        diagnostic = getattr(exc, "diagnostic", None)
        if diagnostic:
            jobs[key]["diagnostic"] = diagnostic


@app.post("/api/code/run")
def run_edited_code(request: CodeRequest):
    parent = read_json(located("runs", request.parent_run_id) / "manifest.json")
    if parent.get("status") != "complete":
        raise ValueError("来源版本未成功生成")
    return start_job(execute_code_job, request)


@app.post("/api/code/revise")
def revise_edited_code(request: CodeRevisionRequest):
    return run_edited_code(request)


@app.post("/api/figure/edit")
def edit_figure(request: FigureEditRequest):
    return run_edited_code(request)


def execute_job(key, request):
    job = jobs[key]
    def emit(message, stage, **extra):
        task_control.check()
        job["events"].append({"message": message, "stage": stage, "at": time.time(), **extra})
    try:
        if request.direct:
            emit("检查映射并运行固定模板", "render")
            result = render(request.dataset_id, request.spec)
            answer = {"message": "已按界面参数生成图像。统计、样本选择和自动检查见右侧。", "run": result, "mode": "template"}
        else:
            turn = agent.model_turn if agent.SETTINGS.enabled else agent.local_turn
            answer = turn(request.dataset_id, request.text, request.spec, emit)
        with lock:
            task_control.check()
            job.update(status="complete", result=answer)
    except task_control.Cancelled:
        raise
    except Exception as exc:
        message = str(exc)
        secret = agent.SETTINGS.api_key
        if secret:
            message = message.replace(secret, "[redacted]")
        job.update(status="error", error=message[:4000])


@app.post("/api/chat")
def chat(request: ChatRequest):
    load_dataset(request.dataset_id)
    return start_job(execute_job, request)


@app.post('/api/jobs/{key}/cancel')
def cancel_job(key: str):
    with lock:
        if key not in jobs:
            raise HTTPException(404, '任务不存在')
        if jobs[key]['status'] == 'running' and key in job_cancels:
            jobs[key]['cancel_requested'] = True
            job_cancels[key].set()
        return {'status':jobs[key]['status'], 'cancel_requested':jobs[key]['cancel_requested']}


@app.get("/api/jobs/{key}")
def get_job(key: str):
    if key not in jobs:
        raise HTTPException(404, "任务不存在")
    return jobs[key]


@app.get("/api/runs/{key}")
def get_run(key: str):
    return read_json(located("runs", key) / "manifest.json")


@app.get("/api/runs/{key}/files/{name}")
def artifact(key: str, name: str, download: bool = False):
    allowed = ARTIFACT_FILES | {'reproduce.zip'}
    if name not in allowed:
        raise HTTPException(404, "文件不存在")
    file = located("runs", key) / name
    if name == 'reproduce.zip':
        if read_json(file.parent / 'manifest.json').get('status') != 'complete':
            raise ValueError('此版本尚未成功生成')
        file = build_bundle(file.parent)
    if not file.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(file, filename=name if download else None)


@app.get('/api/runs/{key}/editable-figure')
def editable_figure(key: str):
    from figure_inspect import inspect_figure
    folder = located('runs', key)
    manifest = read_json(folder / 'manifest.json')
    if manifest.get('status') != 'complete':
        raise ValueError('请先完成图片生成')
    return inspect_figure(folder, manifest)


import analysis_routes
analysis_routes.install(app, start_job, jobs)

app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="ui")
