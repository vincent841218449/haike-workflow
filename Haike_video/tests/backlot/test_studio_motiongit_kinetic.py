import copy
import json
from pathlib import Path
import zipfile
import pytest
from backlot import studio_motiongit_kinetic as k,studio_motiongit as m
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError,sha


def fixture():
    cues=[{'text':t,'start':i*5,'end':i*5+4} for i,t in enumerate(['不是承诺收益。','这是建议。','可以先了解，','以后再决定。'])]
    draft={'text':''.join(c['text'] for c in cues),'input':{'ai':{'materials':[]}}}
    body={'scenes':[{'id':'B1','title':'建议','from_cue':0,'to_cue':1,'support':[cues[0]['text']],'basic':{'keyword':'建议','explanation':cues[0]['text']}},
        {'id':'B4','title':'了解','from_cue':2,'to_cue':3,'support':[cues[2]['text']],'purpose':'summary','basic':{'summary':'了解','action':cues[3]['text']}}]}
    return draft,cues,body


def test_native_expression_plan_preserves_all_copy_and_actual_cue_times():
    draft,cues,body=fixture();v=k.validate_selection(draft,body,cues,20,{})
    assert v['workflow']=='kinetic' and ''.join(s['spokenText'] for s in v['narrationMap'])==draft['text']
    assert v['scenes'][0]['duration']==10
    assert v['narrationMap'][1]['beats'][-1]['at']==15
    for mutated in [cues[:-1],[{**cues[0],'text':'承诺收益。'},*cues[1:]]]:
        with pytest.raises(WorkError):k.validate_selection(draft,body,mutated,20,{})
    omitted=copy.deepcopy(body);omitted['scenes'][1]['from_cue']=3
    with pytest.raises(WorkError):k.validate_selection(draft,omitted,cues,20,{})
    invalid=copy.deepcopy(body);invalid['scenes'][0]['id']='S05'
    with pytest.raises(WorkError):k.validate_selection(draft,invalid,cues,20,{})


def test_missing_user_material_and_wrong_caption_binding_stop_before_render():
    draft,cues,body=fixture();draft['input']['ai']['materials']=[{'id':'a','mode':'must'}]
    with pytest.raises(WorkError):k.validate_selection(draft,body,cues,20,{'a':{'kind':'video'}})
    body['scenes'][0]['visuals']=[{'asset':'a','captionIndex':2}]
    with pytest.raises(WorkError):k.validate_selection(draft,body,cues,20,{'a':{'kind':'video'}})
    body['scenes'][0]['visuals'][0]['captionIndex']=1
    assert k.validate_selection(draft,body,cues,20,{'a':{'kind':'video'}})['scenes'][0]['visuals'][0]['file']=='asset:a'


def test_only_exact_kinetic_auto_receipt_can_complete_native_mode(monkeypatch):
    from backlot import studio_presentation as p
    monkeypatch.setattr(m,'installed',lambda s:{'display_name':'科技风'})
    ref={'runtime':'motiongit','template_id':'385712'}
    d={'input':{'motion':{'style':'motiongit-626-v0-2-29-open-beta','layout':'portrait'},'templateExecution':'auto','templateRef':ref}}
    v={**p.selected(d),'variant':'native','engine_workflow':'kinetic'};p.verify(d,v)
    for invalid in [{**v,'variant':'motion-kit'},{**v,'engine_workflow':'native'}]:
        with pytest.raises(WorkError):p.verify(d,invalid)


def test_editable_export_has_bound_user_inputs_but_no_generated_runtime(tmp_path):
    r=tmp_path/'instance';atomic_private(r/'haike-workflow.json',{'workflow':'kinetic'})
    atomic_private(r/'input-staging/params.json',{'scenes':[]});(r/'input-staging/voice.wav').write_bytes(b'user-audio')
    atomic_private(r/'plan/plan.json',{'profile':'kinetic-user-plan/1'})
    atomic_private(r/'project/user-input.js',{'private_runtime':'must not ship'});(r/'personal.motion').write_bytes(b'private')
    target=tmp_path/'editable-project.zip';m.export_project(r,target)
    with zipfile.ZipFile(target) as z:
        assert 'input-staging/params.json' in z.namelist() and 'input-staging/voice.wav' in z.namelist()
        assert not any('project/' in n or n.endswith('.motion') for n in z.namelist())
    before=target.read_bytes();m.export_project(r,target);assert target.read_bytes()==before
    (r/'input-staging/voice.wav').write_bytes(b'changed-audio')
    with pytest.raises(WorkError,match='旧工程已保留'):m.export_project(r,target)
    assert target.read_bytes()==before


def test_local_alignment_reuses_original_clock_and_rejects_changed_source(tmp_path,monkeypatch):
    from backlot import studio_forced_alignment as a
    from types import SimpleNamespace
    audio=tmp_path/'original.wav';audio.write_bytes(b'original audio')
    monkeypatch.setattr(a,'engine',lambda s:{'python':'offline-python','model_dir':'local-model'})
    calls=[]
    def run(command,**kwargs):
        assert kwargs['env']['HF_HUB_OFFLINE']=='1'
        calls.append(command)
        atomic_private(Path(command[-1]),{'sourceMediaSha256':sha(audio),'segments':[{'text':'一整个小区'}]})
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(a.subprocess,'run',run)
    cues=[{'text':'一整个小区','startMs':0,'endMs':1000}]
    _,result=a.align(None,audio,cues,tmp_path/'clock')
    assert result['segments'][0]['text']=='一整个小区'
    a.align(None,audio,cues,tmp_path/'clock');assert len(calls)==1
    audio.write_bytes(b'new recording')
    with pytest.raises(WorkError,match='旧结果保留'):a.align(None,audio,cues,tmp_path/'clock')
    assert len(calls)==1


def test_native_preview_rejects_tampering_and_symbolic_replacement(tmp_path,monkeypatch):
    project=tmp_path/'project';project.mkdir();parameter=tmp_path/'params.json';parameter.write_text('{}')
    source=project/'source.js';source.write_text('frozen runtime')
    atomic_private(project/'preview.json',{'parameters_sha256':sha(parameter),'projectHashes':{'source.js':sha(source)},'stills':{}})
    monkeypatch.setattr(k,'plan_info',lambda p:{'parameter_path':parameter})
    k.verify_preview(tmp_path)
    backup=project/'backup.js';source.rename(backup);source.symlink_to(backup)
    with pytest.raises(WorkError,match='工程已改变'):k.verify_preview(tmp_path)
