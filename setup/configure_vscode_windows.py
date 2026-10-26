"""Configure VS Code with explicit paths, preserving a backup of user settings."""
import json
import os
from pathlib import Path
import shutil

repo = Path(__file__).resolve().parent.parent
settings = {
    "labFigure.rscriptPath": str(repo / ".runtime/R/bin/Rscript.exe"),
    "labFigure.pythonPath": str(repo / ".venv/Scripts/python.exe"),
    "labFigure.labfigPath": str(repo / "skill/lab-figure/scripts/labfig.py"),
    "labFigure.debounceMs": 300,
    "labFigure.renderTimeoutSeconds": 120,
}
user = Path(os.environ["APPDATA"]) / "Code/User/settings.json"
original = json.loads(user.read_text(encoding="utf-8-sig")) if user.exists() else {}
backup = user.with_name("settings.before-lab-figure.json")
if user.exists() and not backup.exists():
    shutil.copy2(user, backup)
original.update(settings)
user.parent.mkdir(parents=True, exist_ok=True)
user.write_text(json.dumps(original, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
local = repo / ".vscode/settings.json"
local.parent.mkdir(exist_ok=True)
local.write_text(json.dumps({**settings, "python.defaultInterpreterPath": settings["labFigure.pythonPath"]}, indent=4) + "\n", encoding="utf-8")
print(f"Configured: {user}\nBackup: {backup}\nWorkspace: {local}")
