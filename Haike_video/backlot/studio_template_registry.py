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
        from backlot.studio_motiongit import template_ref, installed,execution_modes,component_profile
        config=installed(motion['style'])
        modes=execution_modes(config)
        if not modes:
            raise WorkError('完整模板尚未完成本地运行验收，未提交收费调用','template_incompatible')
        selected=draft['input'].get('templateExecution')
        if selected is None and 'validated_execution_modes' in config:
            raise WorkError('请明确选择已验收的模板制作方式，未提交收费调用','template_incompatible')
        if selected == 'auto':
            from backlot.studio_template_execution import snapshot
            snapshot(draft)
        elif selected and selected not in modes:
            raise WorkError('所选模板的这一制作方式尚未完成本地验收，未提交收费调用','template_incompatible')
        if motion.get('profile'):
            if selected not in {'components','auto'}:raise WorkError('当前材质选项只适用于官方组件编排','template_incompatible')
            component_profile(config,json.loads(Path(config['capabilities']).read_text()),motion['profile'])
        ref = template_ref(config)
        if motion['layout'] != ref['layout'] or draft['input'].get('templateRef') not in (None, ref):
            raise WorkError('所选完整模板版本或画幅已改变，请重新选择', 'template_mismatch')
        return ref
    if motion['style'] == 'quick':
        raise WorkError('轻量动画组件需要配置分镜，不能用于一键口播；请选择完整动效模板，原内容已保留', 'template_incompatible')
    if draft['input'].get('templateExecution') == 'auto':
        raise WorkError('历史原生编舞未接通此自动制作合同，请选择模板库中的新版自动模板', 'template_incompatible')
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


def pending_packages(layout=None):
    # Catalog announcements are not executable installations.
    from backlot.studio_motiongit import configuration,execution_modes
    from backlot.studio_template_names import MOTIONGIT_CATALOG,motiongit_label,CURRENT_PORTRAIT_VERSIONS
    from backlot.studio_motiongit_samples import official_sample
    entries=list(configuration().values());result=[]
    for slug,title,ratio in MOTIONGIT_CATALOG:
        if layout and ratio!=layout:continue
        installed=[c for c in entries if c.get('template_id')==slug]
        current=[c for c in installed if c.get('version')==CURRENT_PORTRAIT_VERSIONS.get(slug,'2.5.7')]
        if current and execution_modes(current[-1]):continue
        config=current[-1] if current else None
        result.append({'id':'motiongit:adunext:'+slug,'name':title,'official_name':title,'aliases':[motiongit_label(slug,title)],'layout':ratio,
            'version':config['version'] if config else None,'supported':False,
            'preview':config.get('preview') if config and str(config.get('preview','')).startswith('/api/') else None,
            'demo':config.get('demo') if config and str(config.get('demo','')).startswith('/api/') else None,
            'preview_basis':config.get('preview_basis') if config else None,
            'status':'validation-pending' if config else 'package-required',
            'reason':config.get('validation_reason') or ('官方组件已可制作；完整原生镜头组仍待验收' if 'components' in execution_modes(config) else '原包已验签，等待本地制作检查') if config else '最新版 .motion 尚未导入；旧版模板继续保留',
            'url':'https://motiongit.com/@adunext/'+slug, **official_sample(slug)})
    return result
