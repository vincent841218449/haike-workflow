"""Bind delivered media to the actual native plan and author package contracts."""
import json
from pathlib import Path

from backlot.studio_template_registry import legacy_ref, verify_ref
from backlot.work_catalog import WorkError, sha


def receipt(draft, folder, output):
    plan_path = Path(folder) / 'planning/auto_plan.json'
    saved = json.loads(plan_path.read_text())
    if saved.get('schema') != 'adu-auto-plan/1': return None
    layout = draft['input'].get('motionLayout', 'portrait')
    styles = {run['style'] for run in saved['runs']}
    selected = draft['input'].get('style')
    if selected and styles != {selected}: raise WorkError('实际原生构建改变了所选风格', 'template_mismatch')
    if len(styles) != 1: return None  # Manual mixed-style projects retain per-run native provenance.
    style = next(iter(styles))
    ref = legacy_ref(style, layout)
    expected = draft['input'].get('templateRef')
    if expected and ref != expected: raise WorkError('原生包与冻结模板版本不一致', 'template_mismatch')
    if {r['selection'] for r in saved['runs']} - {p['selection'] for p in ref['packages']}:
        raise WorkError('实际运行包与所选模板不一致', 'template_mismatch')
    scenes = saved['spec']['scenes']
    if not scenes: raise WorkError('原生构建缺少实际镜头', 'template_mismatch')
    from backlot.studio_template_names import label
    return {'id': f'adu:{style}:{layout}', 'style': style, 'layout': layout,
            'name': label(style),
            'adapter': 'adu-motion-video', 'variant': 'original', 'variant_name': 'ADu 原生镜头组',
            'template_ref': ref, 'plan_sha256': sha(plan_path), 'output_sha256': sha(output),
            'groups': [{'group': s['sceneId'], 'start_frame': s['startFrame'], 'end_frame': s['endFrame']} for s in scenes],
            'semantic_scope': 'source-grounded-internal-review' if draft['input'].get('nativeDirection') else 'manual-declarations',
            'visual_review': 'pending', 'technical_review': 'upstream-check'}


def cached_result(output):
    output = Path(output)
    qa = json.loads((output / 'qa.json').read_text())
    presentation = qa.get('presentation')
    if presentation:
        verify_ref(presentation['template_ref'])
        if presentation['output_sha256'] != sha(output / 'motion-preview.mp4'):
            raise WorkError('成片字节与原生模板回执不一致，原工程保留', 'template_mismatch')
        source = qa['source']
        if presentation['plan_sha256'] != source['plan_sha256']:
            raise WorkError('原生计划与成片回执不一致', 'template_mismatch')
    return {'output_path': str(output / 'motion-preview.mp4'), 'qa_status': 'pending',
            'engineering_archive': qa.get('archive'), **({'presentation': presentation} if presentation else {})}
