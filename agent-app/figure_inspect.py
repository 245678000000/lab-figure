"""Read selectable text from the actual exported PDF, without changing the run."""
import base64
import re

import pymupdf


def inspect_figure(folder, manifest):
    with pymupdf.open(folder / 'figure.pdf') as doc:
        page = doc[0]
        width, height = page.rect.width, page.rect.height
        lines = []
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                spans = [s for s in line['spans'] if s['text'].strip()]
                if not spans:
                    continue
                lines.append(dict(text=''.join(s['text'] for s in spans), bbox=line['bbox'],
                                  size=spans[0]['size'], font=spans[0]['font'],
                                  vertical=abs(line['dir'][1]) > .9,
                                  spans=[{k: s[k] for k in ('text', 'origin', 'size', 'font', 'color')} for s in spans]))
        info, spec = manifest.get('figure_edit_info', {}), manifest['spec']
        roles = {}
        # Only the known annotation is draggable; data labels and P-value brackets stay intact.
        notes = [l for l in lines if re.search(r'\b(?:AUC|HR|p|r)\s*[=:<>]\s*[-+]?(?:\d|\.)', l['text'], re.I)]
        if notes and (len(notes) == 1 or spec['chart'] in ('scatter', 'paired_delta') or info.get('note_moved')
                      or all(l['bbox'][1] > height * .65 for l in notes)):
            # ROC notes include confidence intervals and n on following lines.
            # Require adjacency so sample-count tables cannot become part of this object.
            extra = [l for l in lines if re.match(r'^(95%\s*CI|n\s*[:=])', l['text'], re.I)]
            group = list(notes)
            for line in sorted(extra, key=lambda l:l['bbox'][1]):
                if any(abs(line['bbox'][1]-prev['bbox'][3]) < line['size']*1.5
                       and line['bbox'][0] < prev['bbox'][2] and line['bbox'][2] > prev['bbox'][0] for prev in group):
                    group.append(line)
            roles['note'] = sorted(group, key=lambda l:l['bbox'][1])
        for role, key in [('title', 'title'), ('x', 'x_label'), ('y', 'y_label')]:
            label = info.get(key, spec.get(key))
            candidates = [l for l in lines if label and l['text'] == label]
            if len(candidates) == 1:
                roles[role] = candidates
        # Standard single-panel axes can also have automatic labels absent from the spec.
        if spec['chart'] in ('scatter', 'roc', 'box', 'rate_bar', 'histogram', 'volcano', 'ma'):
            if 'y' not in roles:
                candidates = [l for l in lines if l['vertical'] and l['bbox'][0] < width * .12]
                if len(candidates) == 1:
                    roles['y'] = candidates
            if 'x' not in roles:
                candidates = [l for l in lines if not l['vertical'] and l['bbox'][1] > height*.65
                              and l not in notes and not re.fullmatch(r'[\d.−+%\- ]+', l['text'])]
                if len(candidates) == 1:
                    roles['x'] = candidates
        objects = []
        assigned = []
        for role, members in roles.items():
            if any(l in assigned for l in members):
                continue
            assigned.extend(members)
            box = [min(l['bbox'][0] for l in members), min(l['bbox'][1] for l in members),
                   max(l['bbox'][2] for l in members), max(l['bbox'][3] for l in members)]
            objects.append(dict(role=role, text='\n'.join(l['text'] for l in members), bbox=box, lines=members,
                                size=round(members[0]['size'], 2), font=members[0]['font']))
            for line in members:
                # Transparent text-only redaction retains the plot, markers, fills, and lines.
                page.add_redact_annot(pymupdf.Rect(line['bbox']), fill=False, cross_out=False)
        numeric = [l for l in lines if l not in assigned and re.fullmatch(r'[\d.−+%\- ]+', l['text'])]
        styles = {o['role']: dict(font=o['font'], size=o['size']) for o in objects}
        if numeric:
            styles['ticks'] = dict(font=numeric[0]['font'], size=round(numeric[0]['size'], 2))
        page.apply_redactions(images=0, graphics=0)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(min(3, 1500/max(width,height)), min(3, 1500/max(width,height))), alpha=False)
        background = 'data:image/png;base64,' + base64.b64encode(pix.tobytes('png')).decode('ascii')
        return dict(width=width, height=height, objects=objects, styles=styles, background=background)
