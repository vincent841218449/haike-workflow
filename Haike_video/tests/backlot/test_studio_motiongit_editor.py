import copy
import json
from pathlib import Path

import pytest

from backlot import studio_motiongit_editor as editor
from backlot.studio import Studio,atomic_private
from backlot.work_catalog import WorkError,sha


@pytest.fixture
def scene(tmp_path,monkeypatch):
    studio=Studio(tmp_path/'projects')
    draft=studio.save_draft({'template_id':'avatar-motion-adu-v1','text':'并非所有人都需要。有条件时才使用。','title':'已有口播'})
    draft['input']={'captions':[{'start':0,'end':2.8,'text':'并非所有人都需要。'},
        {'start':3.2,'end':5.8,'text':'有条件时才使用。'}],
        'segments':[{'id':'shot-1','control':'title','props':{'line1':'有条件时使用'},'toCue':1,'purpose':'neutral-emphasis'}]}
    caps={'styleProfiles':{'defaultProfile':'paper','profiles':{'paper':{}}},'controls':{
        'title':{'minDur':2,'props':{'line1':{'type':'string'}}},
        'media':{'minDur':2,'props':{'src':{'type':'media'}}}}}
    path=tmp_path/'caps.json';atomic_private(path,caps)
    config={'style':'motiongit-608-v2-5-7','layout':'portrait','style_profile':'paper','capabilities':str(path)}
    definitions=[{'properties':{'control':{'const':kind},'props':{'type':'object','properties':props,'additionalProperties':False}}} for kind,props in [
        ('title',{'line1':{'type':'string','maxLength':16}}),('media',{'src':{'type':'string'}})]]
    schema={'properties':{'timeline':{'properties':{'segments':{'items':{'oneOf':definitions}}}}}}
    monkeypatch.setattr(editor.motion,'template_ref',lambda config:{'fingerprint':'verified-pack'})
    return studio,draft,config,schema,caps


def test_existing_media_editor_keeps_complete_negated_script_and_sentence_clock(scene):
    s,d,c,schema,caps=scene
    execution,cues,selected=editor.compile_selection(s,d,c,schema,caps,6)
    assert execution['input']['templateExecution']=='components'
    assert execution['input']['motion']['style']=='motiongit-608-v2-5-7'
    assert ''.join(row['text'] for row in cues)==d['text']
    assert selected[0]['$text']==d['text']
    assert selected[0]['t0']==0 and selected[0]['t1']==6


@pytest.mark.parametrize('patch,message',[
    ({'segments':[{'control':'title','props':{'line1':'短标题'},'toCue':0}]},'最后一个镜头'),
    ({'segments':[{'control':'not-in-this-pack','props':{},'toCue':1}]},'本期字幕句'),
    ({'captions':[{'start':1,'end':.5,'text':'并非所有人都需要。'}]},'按实际口播'),
    ({'captions':[{'start':0,'end':3.5,'text':'并非所有人都需要。'},{'start':3.2,'end':5.8,'text':'有条件时才使用。'}]},'按实际口播'),
    ({'segments':[{'control':'title','props':{'line1':'短标题'},'toCue':True}]},'本期字幕句'),
])
def test_invalid_or_dropped_cues_block_before_any_media_runner(scene,patch,message):
    s,d,c,schema,caps=scene;d=copy.deepcopy(d);d['input'].update(patch)
    with pytest.raises(WorkError,match=message):editor.compile_selection(s,d,c,schema,caps,6)


def test_media_fields_cannot_be_arbitrary_files_urls_or_another_projects_asset(scene):
    s,d,c,schema,caps=scene
    d['input']['segments']=[{'control':'media','toCue':1,'props':{'src':'https://example.com/private.mp4'}}]
    with pytest.raises(WorkError,match='当前项目上传'):editor.compile_selection(s,d,c,schema,caps,6)
    other=s.save_draft({'template_id':'avatar-motion-adu-v1','text':'别的项目','title':'其他'})
    path=s.projects_root/other['id']/'assets/image.png';path.parent.mkdir(parents=True);path.write_bytes(b'owned-by-other')
    with s.db() as db:db.execute('INSERT INTO studio_assets VALUES(?,?,?,?,?)',('other-image',other['id'],'图片','image',str(path)))
    d['input']['segments'][0]['props']['src']={'asset':{'id':'other-image'}}
    with pytest.raises(WorkError):editor.compile_selection(s,d,c,schema,caps,6)


def test_changed_preview_or_frozen_input_cannot_reuse_user_confirmation(tmp_path):
    s=Studio(tmp_path/'projects');d=s.save_draft({'template_id':'avatar-motion-adu-v1','text':'真实内容','title':'核对'})
    root=s.projects_root/d['id']/'renders/studio-1/instance';root.mkdir(parents=True)
    source=root/'voice.wav';source.write_bytes(b'original voice')
    preview=root/'project/preview.json';atomic_private(preview,{})
    saved={'draft':d,'video':str(source),'video_sha256':sha(source),'audio':str(source),'audio_sha256':sha(source),
        'instance':'instance','preview_sha256':sha(preview),'stills':{},'request':{'render_id':'studio-1','files':{'voice.wav':sha(source)}}}
    plan_id='a'*32;atomic_private(s.projects_root/d['id']/'assets/motion-plans'/plan_id/'motiongit-snapshot.json',saved)
    atomic_private(preview,{'changed':True})
    with pytest.raises(WorkError,match='预览已改变'):editor.freeze(s,d,plan_id,True)
    source.write_bytes(b'different voice')
    with pytest.raises(WorkError,match='口播来源已改变'):editor.freeze(s,d,plan_id,True)


def test_preview_serving_checks_actual_bytes_and_rejects_directory_escape(tmp_path):
    s=Studio(tmp_path/'projects');d=s.save_draft({'template_id':'avatar-motion-adu-v1','text':'本期内容','title':'核对'})
    outside=tmp_path/'private.png';outside.write_bytes(b'not-a-preview')
    saved={'instance':'instance','request':{'render_id':'studio-1'},'stills':{str(outside):sha(outside)}}
    plan_id='b'*32;atomic_private(s.projects_root/d['id']/'assets/motion-plans'/plan_id/'motiongit-snapshot.json',saved)
    with pytest.raises(WorkError,match='实际预览已改变'):editor.preview_file(s,d['id'],plan_id,0)


def test_overlay_uses_real_sentence_window_and_owned_media(scene):
    s,d,c,schema,caps=scene
    definition={'type':'object','properties':{'control':{'const':'label'},'t0':{'type':'number'},
        't1':{'type':'number'},'cues':{'type':'array','items':{'type':'number'}},'props':{'type':'object','properties':{'text':{'type':'string','maxLength':8}},
        'required':['text'],'additionalProperties':False}},'required':['control','t0','t1','props'],'additionalProperties':False}
    schema['properties']['timeline']['properties']['overlays']={'items':{'oneOf':[definition]}}
    caps['controls']['label']={'minDur':1,'props':{'text':{'type':'string'}}}
    cues=[{'startMs':3200,'endMs':5800}]
    d['input']['overlays']=[{'id':'one','control':'label','fromCue':0,'toCue':0,'props':{'text':'真实标注'}}]
    assert editor.compile_overlays(s,d,schema,caps,cues)==[{'control':'label','t0':3.2,'t1':5.8,'props':{'text':'真实标注'}}]
    d['input']['overlays'][0]['anchorCues']=[0]
    assert editor.compile_overlays(s,d,schema,caps,cues)[0]['cues']==[3.2]
    d['input']['overlays'][0]['anchorCues']=[1]
    with pytest.raises(WorkError,match='本段真实句界'):editor.compile_overlays(s,d,schema,caps,cues)
    d['input']['overlays'][0]['anchorCues']=[]
    d['input']['overlays'][0]['fromCue']=True
    with pytest.raises(WorkError,match='真实句界'):editor.compile_overlays(s,d,schema,caps,cues)
    d['input']['overlays'][0]['fromCue']=0
    d['input']['overlays'][0]['props']={'text':'很长的标注不能绕过原包长度限制'}
    with pytest.raises(WorkError,match='原包要求'):editor.compile_overlays(s,d,schema,caps,cues)
    caps['controls']['label']['minDur']=3
    with pytest.raises(WorkError,match='时长不足'):editor.compile_overlays(s,d,schema,caps,cues)


def test_overlay_only_controls_are_not_exposed_or_accepted_as_main_shots(scene,monkeypatch):
    s,d,c,schema,caps=scene
    overlay={'properties':{'control':{'const':'lowerthird'},'props':{'type':'object'}}}
    schema['properties']['timeline']['properties']['overlays']={'items':{'oneOf':[overlay]}}
    schema['properties']['timeline']['properties']['segments']['items']['oneOf'][0]['properties']['transition']={'enum':['cut','wipe']}
    caps['controls']['lowerthird']={'minDur':2,'props':{}}
    monkeypatch.setattr(editor.motion,'contracts',lambda style:(c,schema,caps))
    monkeypatch.setattr(editor.motion,'execution_modes',lambda config:['components'])
    public=editor.contract(c['style'])
    assert set(public['controls'])=={'title','media'}
    assert set(public['overlays'])=={'lowerthird'}
    assert public['transitions']==['cut','wipe']
    d['input']['segments'][0]['control']='lowerthird'
    with pytest.raises(WorkError,match='主镜头组件'):editor.compile_selection(s,d,c,schema,caps,6)


def test_explicit_presenter_transition_and_chapter_survive_editor_compile(scene):
    s,d,c,schema,caps=scene
    d['input']['segments'][0].update(presenter='hide',transition='wipe',chapter='本期限定')
    result=editor.compile_selection(s,d,c,schema,caps,6)[2][0]
    assert result['presenter']=='hide' and result['transition']=='wipe' and result['chapter']=='本期限定'
