"""Frozen export and colour settings for standalone Python reproduction."""
import json
from pathlib import Path
import numbers
from labstyle_py.style import resolve_size

SETTINGS=json.loads(Path('plot-settings.json').read_text(encoding='utf-8')) if Path('plot-settings.json').exists() else {}

def key(value):
    if isinstance(value,bool) or type(value).__name__=='bool_': return 'TRUE' if value else 'FALSE'
    return format(float(value),'.15g') if isinstance(value,numbers.Real) else str(value)

def configure_colors(data):
    colors=SETTINGS.get('group_colors') or {}
    column=SETTINGS.get('group_column')
    if not colors or SETTINGS.get('chart') not in ('box','rate_bar') or column not in data: return
    import labstyle_py.templates as templates
    levels=templates._levels(data[column].dropna())
    selected=[colors[key(level)] for level in levels]
    previous=templates.palette_for
    templates.palette_for=lambda n:selected if n==len(selected) else previous(n)
    Path('render-colors.json').write_text(json.dumps({key(level):colors[key(level)] for level in levels},ensure_ascii=False,indent=2),encoding='utf-8')

def export_size(size,fig):
    original=size or getattr(fig,'lab_size',None) or 'single'
    wh=resolve_size(original)
    width=SETTINGS.get('width_mm')
    if width is None: return wh
    return (width/25.4,(SETTINGS['height_mm']/25.4 if SETTINGS.get('height_mm') is not None else width/25.4*wh[1]/wh[0]))

def write_style(wh):
    from labstyle_py.style import BASE_SIZE,DPI,TEXT_MM,lab_colors
    info={'name':'AISI-figure','reference':'Original nine labstyle templates','version':'1','base_size_pt':BASE_SIZE,'axis_text_pt':BASE_SIZE*.8,'axis_title_pt':BASE_SIZE,'legend_text_pt':BASE_SIZE*.8,'annotation_mm':TEXT_MM['small'],'colors':lab_colors('binary'),'width_in':wh[0],'height_in':wh[1],'dpi':DPI}
    Path('figure-style.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
