# AISI-figure Windows 配置

## 从 GitHub 下载后的安装

GitHub 保存源码，不包含本机的 Python、R、账号或作图数据。首次安装需要 Python 3.12、R 和 Microsoft Edge WebView2 Runtime。当前桌面实现面向 Windows。

在仓库根目录运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r agent-app/requirements-desktop.txt
.\.venv\Scripts\python.exe -m pip install -e "labstyle-py[test]"
```

将 R 安装到仓库下的 `.runtime/R`，确认 `.runtime/R/bin/Rscript.exe` 存在，再安装 R 包：

```powershell
.\.runtime\R\bin\Rscript.exe setup/install_r_packages.R
.\.runtime\R\bin\Rscript.exe -e "install.packages(c('ggrepel', 'scales'), repos='https://cloud.r-project.org')"
powershell -NoProfile -ExecutionPolicy Bypass -File setup/create_desktop_shortcut.ps1
```

之后双击桌面 **AISI-figure** 或仓库根目录的 `打开 AISI-figure.vbs`。账号登录或 API 配置在应用的“管理模型与登录”中完成，不随 GitHub 同步。使用 ex vivo 专项排除功能还需要本机研究项目的 `../analysis_config/exvivo_sample_exclusions.tsv`；该文件不在此仓库中，缺失时应用会明确报错。

## 现有电脑上的 VS Code 配置记录

已安装的环境均在此仓库内：R 在 `.runtime/R`，Python 在 `.venv`。
Lab Figure Preview 的 Windows 适配版本打包在 `vscode-ext/lab-figure-preview-0.2.0.vsix`。
VS Code 的用户设置已指定上述解释器以及原生 Python 版 `labfig.py`，原设置另存备份。

打开仓库文件夹，打开 `examples/roc.R` 或 `examples/py/roc.py`，
如果 VS Code 显示“受限模式”，需用户手动信任此文件夹，才会启用扩展。
按 Ctrl+Shift+P，运行 `Lab Figure: Open Figure Preview`。
改动脚本后右侧自动更新；面板中 `Export and check` 会导出 PDF/PNG 并检查文字和碰撞。
样例导出到 `examples/out/` 或 `examples/out/py/`。

PowerShell 环境检查：

```powershell
.\.venv\Scripts\python.exe skill/lab-figure/scripts/labfig.py doctor
```

本地修改仅适配 Windows：预览子进程隐藏控制台、Python 使用 UTF-8、导出命令通过配置的 Python 运行。
传给预览进程的脚本文本会统一换行为 LF，避免 Windows CRLF 导致 R 解析失败。
原始 Bash 入口仍保留。

验证记录（2026-10-25）：插件自带的 10 项 R/Python 真实进程测试全部通过；
R/Python ROC 示例均成功导出 PDF/PNG，两个 PDF 的字号与碰撞检查均为 PASS。
