"""One-click narration compiler for verified author component packages.

No fixed sample cardinality, generated facts, guessed word times or remote calls.
Native choreography remains a separate, immutable historical contract.
"""
import json
import math
from pathlib import Path

from backlot.studio import atomic_private
from backlot.studio_template_registry import digest
from backlot.work_catalog import WorkError, sha

VERSION = 'author-components-auto/1'


def contract(config, schema, caps):
    from backlot.studio_motiongit import execution_modes, component_profile, template_ref
    if config.get('version') != '2.5.7' or 'components' not in execution_modes(config):
        raise WorkError('这一模板尚未接通自动制作，请选择已接通的模板', 'template_incompatible')
    definitions = {s['properties']['control']['const']: s for s in schema['properties']['timeline']['properties']['segments']['items']['oneOf']}
    for kind in ('title', 'quote', 'media'):
        if kind not in definitions or kind not in caps['controls']:
            raise WorkError('所选模板缺少自动制作合同', 'template_incompatible')
    return {'compiler': VERSION, 'compiler_sha256': sha(Path(__file__)),
            'template_ref': template_ref(config), 'profile': component_profile(config, caps),
            'controls': ['title', 'quote', 'media'], 'fixed_sample_replay': False}


def snapshot(draft):
    from backlot.studio_motiongit import contracts
    return contract(*contracts(draft['input']['motion']['style']))


def precheck(studio, draft, folder):
    value = snapshot(draft)
    for material in draft['input'].get('ai', {}).get('materials', []):
        studio.asset(material['id'], draft['id'])
    saved = {'fingerprint': digest([draft, value]), 'contract': value,
             'route': 'motion-kit', 'feasible': True, 'paid_calls': 0}
    path = Path(folder) / 'automatic-template-content.json'
    if path.exists() and json.loads(path.read_text()) != saved:
        raise WorkError('自动模板输入已改变，保留原任务', 'template_mismatch')
    atomic_private(path, saved)
    return saved


def storyboard(studio, draft, folder, duration):
    """Bind owned optional media; never fetch or invent illustrative evidence."""
    scenes = []
    for m in draft['input'].get('ai', {}).get('materials', []):
        if m.get('mode') == 'reference':
            continue
        path = studio.asset(m['id'], draft['id'])
        scenes.append({'asset': m, 'asset_sha256': sha(path)})
    result = {'status': 'ready', 'duration': duration, 'scenes': scenes,
              'draft_fingerprint': digest(draft), 'workflow': VERSION}
    path = Path(folder) / 'automatic-storyboard.json'
    if path.exists() and json.loads(path.read_text()) != result:
        raise WorkError('自动模板素材或声音已改变', 'template_mismatch')
    atomic_private(path, result)
    return result


def select(draft, cues, board, config, schema, caps):
    """Compose neutral source quotations using measured sentence boundaries.

    Every source character belongs to one shot; captions carry the complete
    script. Text on cards is a labelled quotation, never an inferred fact/chart.
    """
    from jsonschema import Draft202012Validator
    from backlot.studio_storyboard import bind_script_ranges
    from backlot.studio_motiongit import narration_map
    value = contract(config, schema, caps)
    duration = board['duration']
    if not cues or not math.isfinite(duration) or duration < 3:
        raise WorkError('动效模板需要至少3秒的完整口播', 'template_incompatible')
    if any(not 0 <= c['startMs'] < c['endMs'] <= (duration + .04) * 1000 for c in cues):
        raise WorkError('字幕时间轴超出真实口播', 'template_incompatible')
    if any(a['endMs'] > b['startMs'] for a, b in zip(cues, cues[1:])):
        raise WorkError('字幕时间轴重叠，不能猜测镜头边界', 'template_incompatible')
    bound = bind_script_ranges({'scenes': [
        {'from_cue': i, 'to_cue': i, 'script_start': 0, 'script_end': 1}
        for i in range(len(cues))]}, draft, cues, max_units=3000)['scenes']
    captions = [{**c, 'text': draft['text'][r['script_start']:r['script_end']]}
                for c, r in zip(cues, bound)]
    # Reading groups use full caption units; a short final group joins its predecessor.
    ranges = []; start = 0
    for i in range(len(captions) - 1):
        at = 0 if start == 0 else captions[start]['startMs'] / 1000
        end = captions[i + 1]['startMs'] / 1000
        if end - at >= 5 and duration - end >= 3 and len(ranges) < 29:
            ranges.append((start, i)); start = i + 1
    ranges.append((start, len(captions) - 1))
    media = [s['asset'] for s in board['scenes'] if s.get('asset')]
    required = {m['id'] for m in draft['input'].get('ai', {}).get('materials', []) if m.get('mode') == 'must'}
    # Allocate media first so required inputs cannot disappear behind decoration.
    media.sort(key=lambda m: m['id'] not in required)
    if len(required) > len(ranges):
        # Use additional real sentence boundaries before declaring a capacity
        # problem. Required user media count is real; no invented script steps.
        expanded = []; start = 0
        minimum = max(3, caps['controls']['media']['minDur'])
        for i in range(len(captions)-1):
            at = 0 if start == 0 else captions[start]['startMs']/1000
            end = captions[i+1]['startMs']/1000
            if end-at >= minimum and duration-end >= minimum:
                expanded.append((start,i)); start=i+1
        expanded.append((start,len(captions)-1))
        if len(required) > len(expanded):
            raise WorkError('真实句界与口播时长不足以完整展示全部必用素材，请减少必用项或增加文案', 'template_incompatible')
        ranges = expanded
    definitions = {s['properties']['control']['const']: s for s in schema['properties']['timeline']['properties']['segments']['items']['oneOf']}
    result = []
    for index, (a, b) in enumerate(ranges):
        first, last = bound[a]['script_start'], bound[b]['script_end']
        text = draft['text'][first:last]
        row = {'t0': 0 if a == 0 else captions[a]['startMs'] / 1000,
               't1': duration if b == len(captions) - 1 else captions[b + 1]['startMs'] / 1000,
               '$text': text, 'styleProfile': value['profile'], 'transition': 'cut',
               'presenter': 'card', 'cues': []}
        if index < len(media):
            m = media[index]
            row.update(control='media', variant='tilt', props={'src': 'asset:' + m['id'], 'title': '用户素材'})
            if m.get('offset'): row['props']['sourceStart'] = m['offset']
            # Retain the entire provided frame; do not invent a subject or focus.
            row['$framing'] = {'role': 'evidence', 'focus': {'x': .5, 'y': .5}}
        else:
            excerpt = next((c['text'].strip() for c in captions[a:b+1] if 0 < len(c['text'].strip()) <= 60 and '*' not in c['text']), None)
            if excerpt is None:
                # The complete content remains in captions; never truncate a claim.
                row.update(control='title', variant='split', props={'line1': '口播正文'})
            elif index == 0 and len(excerpt) <= 32:
                row.update(control='title', variant='split', props={'line1': excerpt[:16]})
                if len(excerpt)>16:row['props']['line2']=excerpt[16:]
            elif index == len(ranges)-1 and value['profile']=='console' and len(excerpt)<=40 and 'highlight' in definitions:
                row.update(control='highlight',variant='underline',props={'text':excerpt,'kicker':'口播原文'})
            else:
                row.update(control='quote', variant='card', props={'text': excerpt, 'who': '口播原文'})
        checked = {k: v for k, v in row.items() if k != '$framing'}
        errors = list(Draft202012Validator(definitions[row['control']]).iter_errors(checked))
        if errors or row['t1'] - row['t0'] < caps['controls'][row['control']]['minDur']:
            raise WorkError('自动编排未通过所选原包的真实字段或时长合同', 'template_incompatible')
        row['$purpose'] = 'provided-evidence' if row['control'] == 'media' else 'neutral-emphasis'
        result.append(row)
    if ''.join(s['$text'] for s in result) != draft['text']:
        raise WorkError('自动模板没有完整保留原文', 'template_incompatible')
    narration_map(result, [{'s': c['startMs']/1000, 'e': c['endMs']/1000, 'text': c['text']} for c in captions])
    return result
