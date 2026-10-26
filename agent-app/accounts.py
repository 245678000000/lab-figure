"""Official CLI account bridges. Credentials remain owned by each vendor's CLI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
import task_control

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PROVIDERS = {
    "openai": {"name": "ChatGPT / OpenAI", "base_url": "https://api.openai.com/v1", "api_style": "responses", "account": "codex", "docs": "https://learn.chatgpt.com/docs/auth", "note": "账号授权通过本机 Codex 官方客户端；模型可留空使用客户端默认值。"},
    "claude": {"name": "Claude", "base_url": "https://api.anthropic.com/v1", "api_style": "anthropic", "account": "claude", "docs": "https://code.claude.com/docs/en/authentication", "note": "账号授权通过 Claude Code 官方客户端，需要账号具有相应服务权限。"},
    "deepseek": {"name": "DeepSeek", "base_url": "https://api.deepseek.com", "api_style": "chat", "account": None, "docs": "https://api-docs.deepseek.com/", "note": "使用 DeepSeek 开放平台 API Key；普通聊天网站登录不能替代模型调用凭证。"},
    "glm": {"name": "GLM / 智谱", "base_url": "https://open.bigmodel.cn/api/paas/v4", "api_style": "chat", "account": None, "docs": "https://docs.bigmodel.cn/cn/guide/develop/openai/introduction", "note": "使用智谱开放平台 API Key。Coding Plan 请填写其专用地址及对应密钥。"},
    "kimi": {"name": "Kimi", "base_url": "https://api.moonshot.cn/v1", "api_style": "chat", "account": "kimi", "docs": "https://moonshotai.github.io/kimi-code/en/reference/kimi-command", "note": "账号登录使用 Kimi Code OAuth；API 模式可填写 Moonshot / Kimi 开放平台对应地区地址。"},
    "qwen": {"name": "千问 / Qwen", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_style": "chat", "account": None, "docs": "https://help.aliyun.com/en/model-studio/base-url", "note": "使用百炼 / 千问平台 API Key 或订阅密钥，可修改为工作空间专用地址。Qwen Code 的旧 Qwen OAuth 已停止提供，不能承诺普通网页账号直连。"},
    "custom": {"name": "其他兼容服务", "base_url": "", "api_style": "chat", "account": None, "docs": "", "note": "填写服务商提供的地址、模型和凭证，支持 OpenAI 兼容或 Anthropic Messages 接口。"},
}
LOGIN = {}
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def cli_path(provider):
    if provider == "codex":
        return shutil.which("codex")
    if provider == "claude":
        native = Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe"
        return str(native) if native.exists() else shutil.which("claude.exe")
    native = REPO / ".runtime/kimi-code/node_modules/@moonshot-ai/kimi-code/dist/main.mjs"
    return str(native) if native.exists() else None


def command(provider):
    path = cli_path(provider)
    return [shutil.which("node"), path] if provider == "kimi" else [path]


def safe_env():
    env = {**os.environ, "PYTHONUTF8": "1", "NO_COLOR": "1"}
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(key, None)
    return env


def account_status(provider):
    if provider not in ("codex", "claude", "kimi"):
        raise ValueError("不支持的账号平台")
    executable = cli_path(provider)
    result = {"provider": provider, "installed": bool(executable), "logged_in": False, "message": "未安装官方客户端"}
    if not executable:
        return result
    if provider in ('codex', 'claude'):
        from connection_info import codex_details, claude_details
        result.update(codex_details() if provider == 'codex' else claude_details())
        return result
    if provider == "kimi":
        result["logged_in"] = any(j.get("provider") == "kimi" and j.get("status") == "complete" for j in LOGIN.values())
        result["message"] = "本次账号授权成功" if result["logged_in"] else "官方客户端已安装；请登录，或测试已有账号连接"
        return result


class CodexRPC:
    def __init__(self):
        self.proc = None
        self.pending = {}
        self.write_lock = threading.Lock()
        self.next_id = 1

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        path = cli_path("codex")
        if not path:
            raise ValueError("请先安装 Codex 官方 CLI")
        self.proc = subprocess.Popen([path, "app-server", "--listen", "stdio://"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=safe_env(), creationflags=FLAGS)
        threading.Thread(target=self.reader, daemon=True).start()
        self.request("initialize", {"clientInfo": {"name": "lab_figure_agent", "title": "AISI-figure", "version": "0.2.0"}})
        self.send({"method": "initialized", "params": {}})

    def send(self, value):
        with self.write_lock:
            self.proc.stdin.write(json.dumps(value) + "\n")
            self.proc.stdin.flush()

    def reader(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
                if "id" in msg and msg["id"] in self.pending:
                    self.pending[msg["id"]].put(msg)
                elif msg.get("method") == "account/login/completed":
                    p = msg.get("params", {})
                    for login in LOGIN.values():
                        if login.get("login_id") == p.get("loginId"):
                            login["status"] = "complete" if p.get("success") else "error"
                            login["message"] = "登录成功" if p.get("success") else "登录未完成，请重试"
            except (ValueError, OSError):
                continue

    def request(self, method, params):
        key = self.next_id
        self.next_id += 1
        q = queue.Queue()
        self.pending[key] = q
        try:
            self.send({"id": key, "method": method, "params": params})
            response = q.get(timeout=35)
            if response.get("error"):
                raise ValueError("Codex 官方登录请求未成功，请检查客户端与网络")
            return response.get("result", {})
        except queue.Empty:
            raise ValueError("Codex 官方登录服务未及时响应") from None
        finally:
            self.pending.pop(key, None)


CODEX = CodexRPC()


def start_login(provider):
    if provider not in ("codex", "claude", "kimi"):
        raise ValueError("该平台目前需要 API / 订阅密钥，没有可接入的账号授权入口")
    if not cli_path(provider):
        raise ValueError("该平台官方客户端尚未安装")
    for key, job in LOGIN.items():
        if job["provider"] == provider and job["status"] == "waiting":
            return {"id": key, **job}
    key = uuid.uuid4().hex[:12]
    job = {"provider": provider, "status": "waiting", "message": "请在官方页面完成账号登录", "url": "", "code": ""}
    LOGIN[key] = job
    if provider == "codex":
        CODEX.start()
        result = CODEX.request("account/login/start", {"type": "chatgpt", "useHostedLoginSuccessPage": True})
        job.update(url=result.get("authUrl", ""), login_id=result.get("loginId"))
    else:
        def worker():
            args = command(provider) + (["auth", "login", "--claudeai"] if provider == "claude" else ["login", "--region", "mainland-cn"])
            try:
                proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", env=safe_env(), creationflags=FLAGS)
                timer = threading.Timer(600, lambda: proc.kill() if proc.poll() is None else None)
                timer.start()
                try:
                    for line in proc.stdout:
                        line = re.sub(r"\x1b\[[0-9;]*m", "", line)
                        # Only official authorization URLs and non-secret device codes are shown.
                        for url in re.findall(r'https://[^\s"<>]+', line):
                            from urllib.parse import urlparse
                            host = urlparse(url).hostname or ""
                            if host in ("claude.ai", "console.anthropic.com", "auth.anthropic.com", "www.kimi.com", "kimi.com", "auth.kimi.com", "www.kimi.ai", "kimi.ai"):
                                job["url"] = url
                        if provider == "kimi":
                            code_match = re.search(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", line)
                            if code_match:
                                job["code"] = code_match[0]
                            try:
                                event = json.loads(line)
                                for k in ("user_code", "userCode"):
                                    if event.get(k):
                                        job["code"] = str(event[k])
                            except ValueError:
                                pass
                    rc = proc.wait()
                    job["status"] = "complete" if rc == 0 else "error"
                    job["message"] = "登录成功，可以保存并启用" if rc == 0 else "登录未完成或已超时，请重试"
                finally:
                    timer.cancel()
            except OSError:
                job.update(status="error", message="无法启动官方登录客户端")
        threading.Thread(target=worker, daemon=True).start()
    return {"id": key, **job}


def planner(provider, prompt, model="", image_path=None, image_paths=()):
    images = [p for p in [image_path, *image_paths] if p]
    if images and provider != 'codex':
        raise ValueError('当前账号桥接的看图入口支持 ChatGPT / Codex；其他平台请使用支持图片的 API 模型，或关闭看图继续文字修改。')
    executable = cli_path(provider)
    if not executable:
        raise ValueError("官方账号客户端未安装")
    work = ROOT / "workspace/account-bridge"
    work.mkdir(parents=True, exist_ok=True)
    schema = {"type": "object", "properties": {"action": {"type": "string", "enum": ["render", "answer", "code"]}, "message": {"type": "string"}, "spec_json": {"type": "string"}}, "required": ["action", "message", "spec_json"], "additionalProperties": False}
    schema_file = work / "response-schema.json"
    schema_file.write_text(json.dumps(schema), encoding="utf-8")
    if provider == "codex":
        args = [executable, "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--disable", "shell_tool", "--disable", "unified_exec", "--disable", "multi_agent", "-c", 'web_search="disabled"', "--output-schema", str(schema_file), "--json", "-"]
    elif provider == "claude":
        args = [executable, "-p", "--tools", "", "--restricted", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--disable-slash-commands", "--no-session-persistence", "--output-format", "json", "--json-schema", json.dumps(schema)]
    else:
        agent_file = ROOT / "kimi-planner.md"
        args = command(provider) + ["--agent-file", str(agent_file), "--output-format", "text", "-p", prompt, "--skills-dir", str(work)]
    if model:
        args.extend(["--model", model])
    for image in images:
        args.extend(['--image', str(image)])
    try:
        r = task_control.run(args, input=None if provider == "kimi" else prompt, cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, env=safe_env(), creationflags=FLAGS)
        if r.returncode:
            raise ValueError("账号模型调用失败，请测试官方账号连接、模型权限及网络。")
        if provider == "codex":
            messages = [json.loads(line) for line in r.stdout.splitlines() if line.startswith("{")]
            texts = [m["item"].get("text", "") for m in messages if m.get("type") == "item.completed" and m.get("item", {}).get("type") == "agent_message"]
            content = texts[-1] if texts else ""
        elif provider == "claude":
            result = json.loads(r.stdout)
            if result.get("is_error"):
                raise ValueError("Claude 账号请求未成功，请检查账号权限")
            if isinstance(result.get("structured_output"), dict):
                return result["structured_output"]
            content = result.get("result", "")
        else:
            content = r.stdout.strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        result = json.loads(content)
        if result.get("action") not in ("render", "answer", "code") or not isinstance(result.get("spec_json"), str):
            raise ValueError("账号模型未返回有效作图计划，请重试")
        return result
    except subprocess.TimeoutExpired:
        raise ValueError("账号模型请求超时，请检查服务状态后重试") from None
    except (json.JSONDecodeError, IndexError, KeyError):
        raise ValueError("账号模型响应格式无法识别，请重试或切换 API 模式") from None
