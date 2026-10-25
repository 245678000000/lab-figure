# lab-figure

按导师的作图风格出图：固定的风格包 + 图型模板 + 一个很薄的 agent skill。

| 目录 | 内容 |
|---|---|
| `labstyle/` | R 包：`theme_lab()`、调色板、`save_fig()` 和 9 个模板（ROC、KM、森林图、箱线图、小提琴图、比例柱状图、AUC 柱状图、相关性热图、饼图） |
| `labstyle-py/` | Python 包 `labstyle_py`：同一套风格、`save_fig()` 和 ROC / 箱线图 / 比例柱状图模板，统计结果与 R 版一致（测试直接对照 R） |
| `skill/lab-figure/` | 给 Claude Code / Codex 用的 skill，入口脚本 `scripts/labfig` |
| `examples/` | 每个模板一个示例（用 HNSCC 数据），`style_sheet.R` 生成风格样张 |
| `docs/style-spec.md` | 风格规范：每个数值来自导师代码的哪里 |
| `evals/` | 对比评测用的数据和记录 |
| `vscode-ext/` | VS Code / Cursor 插件：左边改代码，右边实时出图（R 端是 `labstyle::serve()`），见其 README |

## 安装

```bash
brew install --cask r-app                 # R（需要管理员密码）
Rscript setup/install_r_packages.R        # 依赖包 + labstyle
# Python 环境放在 iCloud 之外：~/Documents 开了 iCloud 同步时，放在项目里会被移到云端，导入要等几十秒
uv venv --python 3.12 ~/.local/share/lab-figure/venv
uv pip install --python ~/.local/share/lab-figure/venv/bin/python -r requirements.txt
uv pip install --python ~/.local/share/lab-figure/venv/bin/python -e "labstyle-py[test]"
ln -s ~/.local/share/lab-figure/venv .venv
skill/lab-figure/scripts/labfig doctor    # 检查环境
```

## 安装 skill

用软链接安装，仓库里改了马上生效。`~/.agents/skills` 是 Codex 读取的位置，Claude Code 再链到它（与本机其他 skill 的做法一致）：

```bash
ln -s "$PWD/skill/lab-figure" ~/.agents/skills/lab-figure
ln -s ../../.agents/skills/lab-figure ~/.claude/skills/lab-figure
```

## 常用命令

```bash
Rscript -e 'testthat::test_local("labstyle")'   # 模板测试
.venv/bin/python -m pytest labstyle-py/tests     # Python 版测试（与 R 对照）
Rscript examples/style_sheet.R                   # 风格样张 -> docs/style-sheet.pdf
.venv/bin/python -I examples/make_gallery.py     # 重画示例并更新 skill 图库缩略图
skill/lab-figure/scripts/labfig inspect data.xlsx
skill/lab-figure/scripts/labfig render figures/roc.R
skill/lab-figure/scripts/labfig qa figures/roc.pdf
```

第三方代码与数据来源见 `THIRD_PARTY_NOTICES.md`。
