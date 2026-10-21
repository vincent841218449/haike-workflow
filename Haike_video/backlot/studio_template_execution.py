"""Versioned dispatch: new contracts never change the compiler of frozen jobs."""
import copy
import json
import re
from pathlib import Path
from backlot.studio import atomic_private
from backlot.studio_template_registry import digest
from backlot.work_catalog import WorkError, sha

VERSION='author-narration-auto/2'
VERSIONS={'2.7.10','2.7.11'}


def contract(config,schema,caps):
    if config.get('version') not in VERSIONS:
        from backlot.studio_template_auto import contract as old
        return old(config,schema,caps)
    from backlot.studio_motiongit import execution_modes,template_ref,component_profile
    if 'components' not in execution_modes(config) or not caps.get('controls'):
        raise WorkError('新版模板尚未通过实际制作验收','template_incompatible')
    definitions=schema.get('properties',{}).get('timeline',{}).get('properties',{}).get('segments',{}).get('items',{}).get('oneOf',[])
    controls={d['properties']['control']['const'] for d in definitions}
    if not {'title','quote','media'}<=controls:
        raise WorkError('模板缺少本期口播的公开编排合同','template_incompatible')
    return {'compiler':VERSION,'compiler_sha256':sha(Path(__file__)),
            'template_ref':template_ref(config),'profile':component_profile(config,caps),
            'controls':sorted(controls & caps['controls'].keys()),'fixed_sample_replay':False,
            'selection':'source-grounded-author-controls','native_modes':execution_modes(config)}


def snapshot(draft):
    if not re.fullmatch(r'motiongit-\d+-v2-7-(?:10|11)',draft['input']['motion']['style']):
        from backlot.studio_template_auto import snapshot as old
        return old(draft)
    from backlot.studio_motiongit import contracts
    return contract(*contracts(draft['input']['motion']['style']))


def precheck(studio,draft,folder):
    from backlot.studio_material_search import production_precheck
    production_precheck(draft)
    value=snapshot(draft)
    if value['compiler']!=VERSION:
        from backlot.studio_template_auto import precheck as old
        return old(studio,draft,folder)
    for material in draft['input'].get('ai',{}).get('materials',[]):studio.asset(material['id'],draft['id'])
    receipt={'fingerprint':digest([draft,value]),'contract':value,'feasible':True,'paid_calls':0}
    path=Path(folder)/'automatic-template-content.json'
    if path.exists() and json.loads(path.read_text())!=receipt:
        raise WorkError('新版模板输入已冻结，请保留原任务','template_mismatch')
    atomic_private(path,receipt)
    return receipt


def select(studio,draft,folder,cues,board,caption_cues,attempt=0,diagnostics=None):
    """Use all declared controls via the source-grounded author director.

    A same-package component route follows the current author's narration
    contract. Native editing retains its separate schema and actual validation.
    """
    from backlot.studio_motiongit import select as author_select
    current=copy.deepcopy(draft)
    current['input']['templateExecution']='components'
    return author_select(studio,current,folder,cues,board,caption_cues=caption_cues,
                         attempt=attempt,diagnostics=diagnostics)
