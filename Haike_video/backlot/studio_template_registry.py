"""Resolve author packages by immutable bytes, never by a display name alone."""
import hashlib
import json
import functools
from pathlib import Path

from backlot.work_catalog import WorkError, sha


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@functools.lru_cache(maxsize=2)
def package_paths(root):
    result = {}
    for path in root.joinpath('packs').rglob('manifest.json'):
        manifest = json.loads(path.read_text())
        key = manifest.get('id', '') + '@' + manifest.get('version', '')
        if key in result: raise WorkError('原生模板版本重复，无法确定实际来源', 'template_mismatch')
        result[key] = path
    return result


def legacy_ref(style, layout, groups=None):
    from backlot.studio_motion import COMMIT, VERSION, capabilities, runtime
    root = runtime()
    groups = groups if groups is not None else capabilities(layout)['groups']
    eligible = [g for g in groups if g['style'] == style and layout in g['layouts']]
    selections = sorted({g['selection'] for g in eligible})
    if not selections: raise WorkError('所选原生模板不支持当前画幅', 'template_incompatible')
    packages = []
    for selection in selections:
        name, version = selection.split('@')
        manifest = package_paths(root).get(selection)
        profile = root / 'adaptation-profiles' / name / (version + '.json')
        if manifest is None:
            raise WorkError('所选原生模板或适配合同缺失，尚未提交收费调用', 'template_incompatible')
        data = json.loads(manifest.read_text())
        embedded = data.get('adaptationProfile')
        if not embedded and not profile.is_file(): raise WorkError('原生适配合同缺失', 'template_incompatible')
        packages.append({'selection': selection, 'manifest_sha256': sha(manifest),
                         'profile_sha256': digest(embedded) if embedded else sha(profile),
                         'profile_origin': 'embedded' if embedded else 'sidecar',
                         'source_revision': data.get('sourceRevision')})
    ref = {'schema': 'haike-template-ref/1', 'author': 'adunext', 'runtime': 'adu-legacy',
           'engine_commit': COMMIT, 'skill_version': VERSION, 'mode': 'native',
           'style': style, 'layout': layout, 'packages': packages,
           'groups_sha256': digest(eligible), 'validation_scope': 'upstream-contract; episode-output-required'}
    return {**ref, 'fingerprint': digest(ref)}


def resolve(draft):
    motion = draft['input'].get('motion')
    if not motion: return None
    if motion['style'].startswith('motiongit-'):
        from backlot.studio_motiongit import template_ref, installed
        config=installed(motion['style'])
        if config.get('production_ready') is not True:
            raise WorkError('完整模板尚未完成本地运行验收，未提交收费调用','template_incompatible')
        ref = template_ref(config)
        if motion['layout'] != ref['layout'] or draft['input'].get('templateRef') not in (None, ref):
            raise WorkError('所选完整模板版本或画幅已改变，请重新选择', 'template_mismatch')
        return ref
    if motion['style'] == 'quick':
        from backlot.studio_motion import COMMIT
        return {'schema': 'haike-template-ref/1', 'runtime': 'adu-quick', 'mode': 'quick-start',
                'style': 'quick', 'layout': motion['layout'], 'engine_commit': COMMIT}
    ref = legacy_ref(motion['style'], motion['layout'])
    supplied = draft['input'].get('templateRef')
    if supplied is not None and supplied != ref:
        raise WorkError('模板版本已改变，请重新选择模板；原文与已生成素材保留', 'template_mismatch')
    return ref


def verify_ref(ref):
    if isinstance(ref,dict) and ref.get('runtime') == 'motiongit':
        from backlot.studio_motiongit import verify_ref as verify_motiongit
        return verify_motiongit(ref)
    if not isinstance(ref, dict) or ref.get('runtime') != 'adu-legacy' or ref != legacy_ref(ref.get('style'), ref.get('layout')):
        raise WorkError('所选模板来源、版本或运行文件已变化，原产物保留', 'template_mismatch')


def pending_packages():
    # Catalog announcements are not executable installations.
    from backlot.studio_motiongit import configuration, STYLE
    config = configuration().get(STYLE)
    if config and config.get('production_ready'): return []
    return [{'id': 'motiongit:adunext:template-04-dark-console-portrait',
             'name': '仪器台演示 · 新版完整包', 'version': config['version'] if config else None, 'supported': False,
             'status': 'validation-pending' if config else 'package-required', 'reason': '真实模板包已验证，正在进行本地运行验收' if config else '尚未导入真实 .motion 包，不能制作',
             'url': 'https://motiongit.com/@adunext/template-04-dark-console-portrait'}]
