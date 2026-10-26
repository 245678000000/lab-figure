"""Small presentation-only edits, inserted just before the existing export."""
import json
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

FontFamily = Literal['Arial', 'Times New Roman', 'Calibri', 'Cambria', 'Consolas', 'Microsoft YaHei', 'SimSun', 'sans', 'serif', 'mono']


class FigureEdits(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str | None = Field(default=None, max_length=120)
    x_label: str | None = Field(default=None, max_length=120)
    y_label: str | None = Field(default=None, max_length=120)
    title_size: float | None = Field(default=None, ge=5, le=48)
    axis_title_size: float | None = Field(default=None, ge=5, le=48)
    tick_size: float | None = Field(default=None, ge=5, le=48)
    legend_size: float | None = Field(default=None, ge=5, le=48)
    note_size: float | None = Field(default=None, ge=5, le=48)
    x_label_size: float | None = Field(default=None, ge=5, le=48)
    y_label_size: float | None = Field(default=None, ge=5, le=48)
    title_family: FontFamily | None = None
    axis_title_family: FontFamily | None = None
    tick_family: FontFamily | None = None
    legend_family: FontFamily | None = None
    note_family: FontFamily | None = None
    x_label_family: FontFamily | None = None
    y_label_family: FontFamily | None = None
    note_hjust: float | None = Field(default=None, ge=0, le=1)
    note_vjust: float | None = Field(default=None, ge=0, le=1)
    legend_position: Literal['keep', 'right', 'left', 'top', 'bottom', 'none', 'manual'] = 'keep'
    legend_x: float = Field(default=.8, ge=.02, le=.98)
    legend_y: float = Field(default=.75, ge=.02, le=.98)
    note_position: Literal['keep', 'manual'] = 'keep'
    note_x: float = Field(default=.32, ge=.02, le=.98)
    note_y: float = Field(default=.8, ge=.02, le=.98)


def edit_code(code, engine, chart, edits):
    # Only replace our own block. Never regenerate the user's plotting script.
    code = re.sub(r'^# BEGIN AISI FIGURE EDIT\r?\n.*?^# END AISI FIGURE EDIT\r?\n', '', code, flags=re.M | re.S)
    code = re.sub(r'^ais_save_figure\(', 'save_fig(', code, flags=re.M)
    obj = 'p' if engine == 'r' else 'fig'
    # Current scripts end with finish(p); older versions call save_fig(p, ...) directly.
    finish = list(re.finditer(rf'^finish\(\s*{obj}\b', code, re.M))
    pattern = rf'^save_fig\(\s*{obj}\s*,'
    matches = finish or list(re.finditer(pattern, code, re.M))
    if len(matches) != 1:
        raise ValueError('未找到唯一的导出语句；请保留 finish(p) / finish(fig)，或直接修改代码。')
    settings = edits.model_dump()
    if engine == 'r':
        # Keep the script ASCII-safe even when the R process uses the C locale.
        literal = json.dumps(json.dumps(settings, ensure_ascii=True))
        body = f'source("figure-edit.R")\np <- ais_edit_figure(p, jsonlite::fromJSON({literal}, simplifyVector=FALSE), "{chart}")\n'
    else:
        body = f'from figure_edit_helpers import edit_figure\nedit_figure(fig, {settings!r})\n'
    block = '# BEGIN AISI FIGURE EDIT\n' + body + '# END AISI FIGURE EDIT\n'
    pos = matches[0].start()
    if engine == 'r' and not finish:
        code = code[:pos] + code[pos:].replace('save_fig(', 'ais_save_figure(', 1)
    return code[:pos] + block + code[pos:]
