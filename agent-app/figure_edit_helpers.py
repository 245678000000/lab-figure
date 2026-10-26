"""Frozen Matplotlib presentation edits for independently reproducible exports."""
import json
import re
from pathlib import Path


def edit_figure(fig, edits):
    ax = fig.axes[0]
    for key, setter in [('title', ax.set_title), ('x_label', ax.set_xlabel), ('y_label', ax.set_ylabel)]:
        if edits[key] is not None:
            setter(edits[key])
    legend = ax.get_legend()
    for key, artists in [('title_family',[ax.title]), ('axis_title_family',[ax.xaxis.label,ax.yaxis.label]),
                         ('tick_family',[*ax.get_xticklabels(), *ax.get_yticklabels()]),
                         ('legend_family', [legend.get_title(), *legend.get_texts()] if legend is not None else [])]:
        if edits.get(key) is not None:
            for artist in artists:
                artist.set_fontfamily(edits[key])
    for key, artists in [('title_size',[ax.title]), ('axis_title_size',[ax.xaxis.label,ax.yaxis.label])]:
        if edits.get(key) is not None:
            for artist in artists:
                artist.set_fontsize(edits[key])
    if edits.get('tick_size') is not None:
        ax.tick_params(axis='both', labelsize=edits['tick_size'])
    for axis, artist in [('x',ax.xaxis.label),('y',ax.yaxis.label)]:
        if edits.get(axis+'_label_size') is not None:
            artist.set_fontsize(edits[axis+'_label_size'])
        if edits.get(axis+'_label_family') is not None:
            artist.set_fontfamily(edits[axis+'_label_family'])
    if legend is not None and edits.get('legend_size') is not None:
        for artist in [legend.get_title(), *legend.get_texts()]:
            artist.set_fontsize(edits['legend_size'])
    position = edits['legend_position']
    moved = False
    if position == 'manual':
        if legend is None:
            raise ValueError('这张图没有可移动的图例。')
        legend.set_loc('center')
        legend.set_bbox_to_anchor((edits['legend_x'], edits['legend_y']), transform=fig.transFigure)
        moved = True
    elif position == 'none' and legend is not None:
        legend.remove()
    elif position != 'keep' and legend is not None:
        places = {'right': ('center left', (1.01,.5)), 'left': ('center right',(-.08,.5)),
                  'top': ('lower center',(.5,1.02)), 'bottom': ('upper center',(.5,-.15))}
        loc, xy = places[position]
        legend.set_loc(loc)
        legend.set_bbox_to_anchor(xy, transform=ax.transAxes)
        # Reserve space for outside legends on the fixed export canvas.
        fig.subplots_adjust(**{'right':dict(right=.72), 'left':dict(left=.3),
                               'top':dict(top=.74), 'bottom':dict(bottom=.3)}[position])
    note_moved = edits['note_position'] == 'manual'
    if note_moved or edits.get('note_size') is not None or edits.get('note_family') is not None:
        notes = [t for t in ax.texts if re.search(r'AUC|HR|[pPrR]\s*[=<>]|Wilcoxon|Spearman|Pearson', t.get_text())]
        if len(notes) != 1:
            raise ValueError('这张图没有唯一可移动的统计说明；显著性括号等请使用代码或看图修改。')
        note = notes[0]
        if edits.get('note_size') is not None:
            note.set_fontsize(edits['note_size'])
        if edits.get('note_family') is not None:
            note.set_fontfamily(edits['note_family'])
    if note_moved:
        note.set_transform(fig.transFigure)
        note.set_position((edits['note_x'], edits['note_y']))
        note.set_ha('left' if edits['note_x'] < .4 else 'right' if edits['note_x'] > .6 else 'center')
        note.set_va('bottom' if edits['note_y'] < .4 else 'top' if edits['note_y'] > .6 else 'center')
        if edits.get('note_hjust') == .5:
            note.set_ha('center')
        if edits.get('note_vjust') == .5:
            note.set_va('center')
        note.set_clip_on(False)
    info = dict(title=ax.get_title(), x_label=ax.get_xlabel(), y_label=ax.get_ylabel(), note_moved=note_moved, legend_moved=moved)
    info['font_sizes'] = {k:edits.get(k) for k in ('title_size','axis_title_size','tick_size','legend_size','note_size','x_label_size','y_label_size')}
    Path('figure-edit-info.json').write_text(json.dumps(info,ensure_ascii=False),encoding='utf-8')
