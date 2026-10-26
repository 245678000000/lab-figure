"""Frozen export and colour settings for standalone Python reproduction.

A figure script needs only: d = read_source(); fig = <a labstyle_py template>; finish(fig).
"""
import json
from pathlib import Path
import numbers
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from labstyle_py.style import resolve_size

plt.rcParams["font.sans-serif"] = ["Arial", "Microsoft YaHei", "DejaVu Sans"]

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


def read_source():
    """This run's input table, with the run's group colours applied to the templates."""
    data = pd.read_csv("source_data.csv")
    configure_colors(data)
    return data


def finish(fig, size=None):
    """Save figure.pdf/png/svg plus the statistics and versions the app reads."""
    import importlib.metadata
    from labstyle_py import lab_stats, save_fig
    wh = export_size(size, fig)
    write_style(wh)
    save_fig(fig, "figure", dir=".", size=wh, formats=("pdf", "png", "svg"))
    s = lab_stats(fig)
    if s is not None:
        s.to_json("stats.json", orient="records", force_ascii=False, double_precision=15)
        s.to_csv("statistics.csv", index=False)
    packages = ["labstyle-py", "pandas", "numpy", "scipy", "scikit-learn", "matplotlib"]
    Path("session-info.txt").write_text("\n".join(f"{p}=={importlib.metadata.version(p)}" for p in packages), encoding="utf-8")
    return fig
