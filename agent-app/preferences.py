"""Persistent named group colours. File location is supplied by core.STORE."""
import json
import math
from pathlib import Path
import re
import threading
import numbers

from labstyle_py.style import lab_colors, to_mpl_color
from matplotlib.colors import to_hex

LOCK = threading.RLock()
COLOR_CHARTS = {'box','violin','rate_bar','km','pie','embedding','composition','scatter','pca','custom','paired','waterfall','swimmer','ridge','density'}


def group_key(value):
    if isinstance(value, (bool,)) or type(value).__name__ == 'bool_':
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, numbers.Real):
        return format(float(value), '.15g')
    return str(value)


def palette():
    colors=[]
    for family in ('binary','categorical','clusters'):
        for value in lab_colors(family):
            color=to_hex(to_mpl_color(value),keep_alpha=False).upper()
            if color not in colors: colors.append(color)
    return colors


def read_colors(store):
    path=Path(store)/'preferences/group-colors.json'
    if not path.exists(): return {}
    return json.loads(path.read_text(encoding='utf-8'))['colors']


def save_colors(store, colors):
    path=Path(store)/'preferences/group-colors.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps({'version':1,'colors':colors},ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def allocate_colors(store, groups):
    groups=sorted(set(group_key(g) for g in groups))
    if len(groups)>100: raise ValueError('分组超过 100 类，请核对是否误选样本编号列')
    with LOCK:
        colors=read_colors(store)
        preferred=[to_hex(to_mpl_color(c),keep_alpha=False).upper() for c in lab_colors('categorical' if len(groups)>2 else 'binary')]
        choices=list(dict.fromkeys(preferred+palette()))
        available=[c for c in choices if c not in colors.values()]
        for group in groups:
            if group not in colors:
                if not available: raise ValueError('原配色已用完，请在分组配色中手动指定新颜色')
                colors[group]=available.pop(0)
        save_colors(store,colors)
        return {g:colors[g] for g in groups}


def update_colors(store, updates):
    if len(updates)>500: raise ValueError('一次最多更新 500 个分组')
    for group,color in updates.items():
        if not group.strip() or len(group)>200 or not re.fullmatch(r'#[0-9A-Fa-f]{6}',color):
            raise ValueError('分组名不能为空，颜色需为 #RRGGBB')
    with LOCK:
        colors=read_colors(store)
        colors.update({g:c.upper() for g,c in updates.items()})
        save_colors(store,colors)
        return colors
