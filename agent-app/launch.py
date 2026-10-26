"""Start the shared local service, then open the desktop app (or --browser)."""
import os
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8765"

def running():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL + "/api/state", timeout=2) as r:
            state = json.load(r)
            return r.status == 200 and all(key in state for key in ('datasets', 'runs', 'catalog'))
    except Exception:
        return False

def ensure_server():
    if running():
        return
    python = ROOT.parent / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    log_dir = ROOT / "workspace"
    log_dir.mkdir(exist_ok=True)
    with (log_dir / "server.log").open("a", encoding="utf-8") as log:
        subprocess.Popen([str(python), "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8765"],
                         cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         env={**os.environ, "PYTHONUTF8": "1"},
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    for _ in range(80):
        if running():
            break
        time.sleep(.25)
    else:
        raise RuntimeError("启动失败，请查看 agent-app/workspace/server.log")


if __name__ == '__main__':
    # The desktop window uses Windows WebView2; other systems open the browser.
    if '--browser' in sys.argv or os.name != 'nt':
        ensure_server()
        webbrowser.open(URL)
    else:
        from desktop import run
        run()
