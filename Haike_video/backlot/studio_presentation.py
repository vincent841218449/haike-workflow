"""The user's visual selection survives every production stage unchanged."""
from pathlib import Path

from backlot.work_catalog import WorkError, sha

INSTRUMENT_STYLE = '04-A'
INSTRUMENT_ADAPTER = 'studio-instrument-v1'


def selected(draft):
    motion = draft.get('input', {}).get('motion')
    if motion:
        return {'id':f"adu:{motion['style']}:{motion['layout']}", 'style':motion['style'],
                'layout':motion['layout'], 'name':'仪器台演示' if motion['style']=='04-A' else motion['style']}
    from backlot.studio import TEMPLATES
    template = next((t for t in TEMPLATES if t['id']==draft['template_id']), {})
    return {'id':draft['template_id'], 'style':None, 'layout':template.get('ratio'), 'name':template.get('name',draft['template_id'])}


def instrument_plan(draft, storyboard):
    motion = draft['input'].get('motion') or {}
    if motion.get('style') != INSTRUMENT_STYLE: raise WorkError('自动仪器台不能替代其他已选模板', 'template_mismatch')
    if not storyboard or storyboard.get('status') != 'ready' or not storyboard.get('scenes'):
        raise WorkError('仪器台需要完整的本期分镜与素材；已保留原模板', 'template_incompatible')
    scenes = storyboard['scenes']
    required={m['id'] for m in draft['input'].get('ai',{}).get('materials',[]) if m.get('mode')=='must'}
    if required-{s.get('asset',{}).get('id') for s in scenes}:
        raise WorkError('仪器台编排遗漏了必须使用的用户素材，原素材和模板已保留', 'template_incompatible')
    if ''.join(s['text'] for s in scenes) != draft['text']:
        raise WorkError('仪器台分镜必须完整保留原文', 'template_incompatible')
    cursor=0
    for scene in scenes:
        if abs(scene['start']-cursor)>.025 or scene['end']<=scene['start'] or not scene.get('asset') or not scene.get('asset_sha256'):
            raise WorkError('仪器台分镜、素材或真实时间轴尚未完整', 'template_incompatible')
        cursor=scene['end']
    if abs(cursor-storyboard['duration'])>.025: raise WorkError('仪器台分镜未覆盖口播结尾', 'template_incompatible')
    entry=Path(__file__).resolve().parents[1]/'templates'/INSTRUMENT_ADAPTER/'index.tsx'
    if not entry.is_file(): raise WorkError('所选仪器台渲染组件尚未安装', 'template_incompatible')
    return {**selected(draft), 'variant':'narrative-v1', 'variant_name':'自动口播版',
            'adapter':INSTRUMENT_ADAPTER, 'adapter_sha256':sha(entry), 'fps':60,
            'frames':round(storyboard['duration']*60), 'scene_ids':[s['id'] for s in scenes]}


def verify(draft, actual):
    if not isinstance(actual,dict) or actual.get('id') != selected(draft)['id']:
        raise WorkError('实际渲染模板与所选模板不一致，产物保留但不会标记制作成功', 'template_mismatch')
