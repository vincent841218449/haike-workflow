"""Opt-in scene/clip sourcing for automatic templates; frozen legacy jobs stay local.

The source policy is part of the draft fingerprint. Only selected providers run;
an unavailable provider never becomes an empty search or a paid fallback.
"""
import copy
import hashlib
import json
import math
from pathlib import Path

from backlot.studio import atomic_private
from backlot.studio_template_registry import digest
from backlot.work_catalog import WorkError, sha

VERSION = 'haike-material-search/1'


def production_precheck(draft):
    settings=policy(draft)
    if settings and (settings['providers'] or draft['input'].get('ai',{}).get('materials')):
        # Real downloaded-video acceptance currently fails the signed renderer's
        # caption/subject geometry gate. Never spend speech/avatar budget first.
        raise WorkError('素材搜索与下载已接通，但本模板的片段合成尚未通过本地验收。请暂用原模板制作；本次未提交配音或数字人费用。','template_incompatible')


def fingerprint(draft,cues,duration):
    # Template-only editing may reuse the exact source passages/clip decisions.
    # Owner, script, selected sources, uploaded bytes and real clock still bind.
    return digest([draft['id'],draft['text'],draft['input'].get('ai'),cues,duration,VERSION])


def policy(draft):
    value = draft['input'].get('ai', {}).get('material_search')
    if value is None:
        return None
    if draft['input']['ai'].get('enabled') is not True:
        raise WorkError('请开启素材辅助制作，或取消网络素材来源')
    if not isinstance(value, dict) or set(value) != {'schema', 'providers', 'max_scenes'}:
        raise WorkError('素材来源设置无效')
    providers = value['providers']
    if value['schema'] != VERSION or not isinstance(providers, list) or any(not isinstance(p,str) or p not in ('douyin', 'pexels') for p in providers) or len(providers) != len(set(providers)):
        raise WorkError('素材来源设置无效')
    if type(value['max_scenes']) is not int or not 1 <= value['max_scenes'] <= 4:
        raise WorkError('每条最多匹配四段网络画面')
    return value


def resolve(scene, settings, sources):
    """Keep the selected order and stop on real errors, not on an empty result."""
    for provider in settings['providers']:
        asset = getattr(sources, provider)(scene)
        if asset:
            return asset
    return None


def clip_binding(scene, asset, source_in, source_out, reason):
    length = scene['end'] - scene['start']
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (source_in, source_out)) or source_in < 0 or source_out - source_in + .001 < length:
        raise WorkError('素材采用区间不足当前镜头，未循环补长', 'template_incompatible')
    return {'schema': 'haike-clip-binding/1', 'scene_id': scene['id'],
            'source_text_range': [scene['script_start'], scene['script_end']],
            'asset_id': asset['id'], 'sha256': asset['provenance']['sha256'],
            'source_in': source_in, 'source_out': source_in + length,
            'timeline_in': scene['start'], 'timeline_out': scene['end'],
            'mute': True, 'gain': 0, 'locked': False, 'reason': reason,
            'provenance': asset['provenance']}


def storyboard(studio, draft, folder, duration, cues, paid):
    from backlot.studio_storyboard import TrialRelay, make_plan, Sources
    settings = policy(draft)
    if settings is None:
        from backlot.studio_template_auto import storyboard as legacy
        return legacy(studio, draft, folder, duration)
    folder = Path(folder)
    path = folder / 'storyboard.json'
    identity = fingerprint(draft,cues,duration)
    plan = json.loads(path.read_text()) if path.is_file() else None
    if plan and plan.get('fingerprint') != identity:
        raise WorkError('原素材计划已冻结，不能用重试替换输入', 'template_mismatch')
    if plan and plan.get('status') == 'ready':
        for scene in plan['scenes']:
            if scene.get('asset') and sha(studio.asset(scene['asset']['id'], draft['id'])) != scene['asset_sha256']:
                raise WorkError('原片段素材已变化，未重新搜索或生成', 'template_mismatch')
        return plan
    relay = TrialRelay(studio, folder / 'material-requests')
    if plan is None:
        # The visual brief uses text cards for narrative passages. This does not
        # select another render template or mutate the immutable original draft.
        brief = copy.deepcopy(draft)
        brief['input']['motion'] = None
        brief['input']['ai']['brief'] = (brief['input']['ai'].get('brief', '') +
            '\n仅为需要情境画面的段落安排素材，最多' + str(settings['max_scenes']) +
            '段；观点、提问与总结用presentation:text。素材检索限于所选来源：' + ','.join(settings['providers']))[-1500:]
        plan = {**make_plan(studio, brief, cues, duration, relay), 'fingerprint': identity,
                'draft_fingerprint':hashlib.sha256(json.dumps(draft,sort_keys=True).encode()).hexdigest(),
                'workflow': VERSION, 'source_policy': settings, 'status': 'matching'}
        atomic_private(path, plan)
    sources = Sources(studio, draft, relay, paid)
    searched = sum(s.get('source_status') in {'bound','clip-review','clip-rejected','no-suitable-material','duplicate-source'} and not s.get('asset_id') for s in plan['scenes'])
    used = set()
    for scene in plan['scenes']:
        if scene.get('asset'):
            if sha(studio.asset(scene['asset']['id'], draft['id'])) != scene['asset_sha256']:
                raise WorkError('原素材摘要不符', 'template_mismatch')
            used.add(scene['asset'].get('provenance',{}).get('source_url') or scene['asset']['id'])
            continue
        if scene.get('source_status') in {'clip-rejected','no-suitable-material','duplicate-source'}:
            continue
        if scene.get('candidate_asset'):
            asset=scene['candidate_asset']
            if sha(studio.asset(asset['id'],draft['id']))!=scene['candidate_sha256']:
                raise WorkError('待核验的原候选素材已改变，未重新搜索','template_mismatch')
        elif scene.get('asset_id'):
            m = next(m for m in draft['input']['ai']['materials'] if m['id'] == scene['asset_id'])
            asset = {**m, 'provenance': {'source': 'user', 'rights': 'user-confirmed',
                     'sha256': sha(studio.asset(m['id'], draft['id']))}}
        elif scene.get('presentation') == 'text' or searched >= settings['max_scenes'] or not settings['providers']:
            scene.update(presentation='text', source_status='template-narrative')
            continue
        else:
            searched += 1
            asset = resolve(scene, settings, sources)
        if not asset:
            scene.update(presentation='text', source_status='no-suitable-material', reason='所选来源无合适画面，保留本模板叙述镜头')
            atomic_private(path, plan)
            continue
        source_id = asset.get('provenance', {}).get('source_url') or asset['id']
        if source_id in used:
            scene.update(presentation='text', source_status='duplicate-source')
            continue
        scene.update(candidate_asset=asset,candidate_sha256=sha(studio.asset(asset['id'],draft['id'])),source_status='clip-review')
        atomic_private(path,plan)  # Freeze the owned ID before any ambiguous model call.
        from backlot.studio_material_clips import select_clip
        binding = select_clip(studio, draft, scene, asset, relay)
        if binding is None:
            scene.update(presentation='text', source_status='clip-rejected')
        else:
            scene.update(asset=asset, asset_sha256=binding['sha256'], clip=binding, source_status='bound')
            used.add(source_id)
        atomic_private(path, plan)
    required = {m['id'] for m in draft['input']['ai'].get('materials', []) if m.get('mode') == 'must'}
    actual = {s['asset']['id'] for s in plan['scenes'] if s.get('asset')}
    if required - actual:
        raise WorkError('必用素材没有合适片段，原配音与数字人保留', 'template_incompatible')
    plan['status'] = 'ready'
    atomic_private(path, plan)
    return plan


def segments(draft, cues, board, config, schema, caps):
    """Keep media attached to its own source passage rather than the first N shots."""
    from backlot.studio_template_auto import select
    rows = []
    for scene in board['scenes']:
        a, b = scene['from_cue'], scene['to_cue']
        start, end = scene['script_start'], scene['script_end']
        short = copy.deepcopy(draft)
        short['text'] = draft['text'][start:end]
        short['input']['ai']['materials'] = []
        clock = [{**c, 'startMs': c['startMs'] - scene['start'] * 1000,
                  'endMs': min(c['endMs'] / 1000, scene['end']) * 1000 - scene['start'] * 1000}
                 for c in cues[a:b+1]]
        duration = scene['end'] - scene['start']
        if duration < 3:
            raise WorkError('素材场景短于模板最低时长，请合并相邻段落', 'template_incompatible')
        part = select(short, clock, {'duration': duration, 'scenes': []}, config, schema, caps)
        if scene.get('clip'):
            # One source is used once. Only the matched scene becomes a media
            # slot; the original speech and every source character stay intact.
            row = part[0]
            row.update(t0=0, t1=duration, control='media', variant='tilt',
                       props={'src': 'asset:' + scene['asset']['id'], 'title': scene['label'],
                              'sourceStart': scene['clip']['source_in']},
                       **{'$text': short['text'], '$purpose': 'provided-evidence',
                          '$framing': {'role': 'footage', 'focus': {'x': .5, 'y': .5}}})
            part = [row]
        for row in part:
            row['t0'] += scene['start']; row['t1'] += scene['start']
        rows.extend(part)
    if ''.join(r['$text'] for r in rows) != draft['text']:
        raise WorkError('素材时间线未完整保留原稿', 'template_mismatch')
    return rows
