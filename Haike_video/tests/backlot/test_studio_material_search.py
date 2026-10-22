import copy
from types import SimpleNamespace
import pytest
from backlot import studio_material_search as search
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha


def draft():
    return {'id':'studio-material-test','text':'先看看办公室。最后做个总结。','input':{
        'ai':{'enabled':True,'materials':[], 'material_search':{
            'schema':search.VERSION,'providers':['douyin'],'max_scenes':4}},
        'motion':{'style':'frozen-package'},'templateExecution':'auto','soundMode':'voice'}}


def test_selected_provider_only_and_errors_never_silently_fall_back():
    calls=[]
    sources=SimpleNamespace(douyin=lambda s:calls.append('douyin'),
                            pexels=lambda s:pytest.fail('unselected stock'))
    assert search.resolve({},search.policy(draft()),sources) is None
    assert calls==['douyin']
    def unavailable(s):raise WorkError('登录已过期','unavailable')
    sources.douyin=unavailable
    with pytest.raises(WorkError,match='登录'):search.resolve({},search.policy(draft()),sources)


def test_policy_is_versioned_and_does_not_enable_historical_jobs():
    old=draft();del old['input']['ai']['material_search']
    assert search.policy(old) is None
    for patch in ({'providers':['douyin','douyin']},{'providers':['image']},{'max_scenes':True},{'schema':'unknown'}):
        d=draft();d['input']['ai']['material_search'].update(patch)
        with pytest.raises(WorkError):search.policy(d)
    d=draft();d['input']['ai']['enabled']=False
    with pytest.raises(WorkError,match='开启素材'):search.policy(d)


def test_unaccepted_real_video_integration_is_blocked_before_any_legacy_production_precheck(tmp_path,monkeypatch):
    from backlot import studio_template_execution as execution,studio_template_auto as legacy
    monkeypatch.setattr(legacy,'precheck',lambda *a:pytest.fail('must stop before production work'))
    with pytest.raises(WorkError,match='未提交配音或数字人费用'):
        execution.precheck(None,draft(),tmp_path)


def test_clip_binding_keeps_exact_scene_interval_and_mutes_external_audio():
    s={'id':'scene-2','start':8,'end':13,'script_start':10,'script_end':20}
    asset={'id':'a','provenance':{'sha256':'original','source':'douyin','author':'author'}}
    b=search.clip_binding(s,asset,23,30,'实际画面相关')
    assert (b['source_in'],b['source_out'],b['timeline_in'],b['timeline_out'])==(23,28,8,13)
    assert b['source_text_range']==[10,20] and b['mute'] and b['gain']==0
    for start,end in ((0,3),(-1,8),(float('nan'),10)):
        with pytest.raises(WorkError):search.clip_binding(s,asset,start,end,'bad')


def test_ready_material_plan_reuses_original_bytes_without_search_models_or_paid_calls(tmp_path,monkeypatch):
    from backlot import studio_storyboard as planning
    d=draft();media=tmp_path/'source.mp4';media.write_bytes(b'cached-original')
    studio=SimpleNamespace(asset=lambda *a:media)
    cues=[{'text':d['text'],'startMs':0,'endMs':12000}]
    plan={'fingerprint':search.fingerprint(d,cues,12),'status':'ready',
          'scenes':[{'asset':{'id':'cached'},'asset_sha256':sha(media)}]}
    atomic_private(tmp_path/'storyboard.json',plan)
    monkeypatch.setattr(planning,'TrialRelay',lambda *a:pytest.fail('cached plan must not call remote'))
    assert search.storyboard(studio,d,tmp_path,12,cues,lambda *a:pytest.fail('paid'))==plan
    changed=copy.deepcopy(d);changed['revision']=2;changed['input']['motion']['style']='other-template'
    assert search.storyboard(studio,changed,tmp_path,12,cues,None)==plan
    media.write_bytes(b'changed')
    with pytest.raises(WorkError,match='素材已变化'):search.storyboard(studio,d,tmp_path,12,cues,None)


def test_auto_production_entry_routes_selected_sources_and_preserves_old_compiler(monkeypatch,tmp_path):
    from backlot import studio_template_auto as legacy
    d=draft();del d['input']['ai']['material_search']
    monkeypatch.setattr(legacy,'storyboard',lambda *a:{'workflow':legacy.VERSION})
    assert search.storyboard(None,d,tmp_path,12,[],None)['workflow']==legacy.VERSION


def test_clip_windows_are_real_bounded_intervals_not_looped():
    from backlot.studio_material_clips import windows
    assert windows(3,5)==[]
    result=windows(20,5,2)
    assert result==[(2,7),(8.5,13.5),(15,20)]
    assert len(windows(5,5))==1


def test_media_stays_at_its_script_scene_instead_of_front_of_film(monkeypatch):
    from backlot import studio_template_auto as old
    def compose(d,c,b,*args):
        return [{'t0':0,'t1':b['duration'],'$text':d['text'],'control':'quote','props':{'text':d['text']}}]
    monkeypatch.setattr(old,'select',compose)
    d=draft();text=d['text'];cut=text.index('最后')
    cues=[{'startMs':0,'endMs':5900,'text':text[:cut]}, {'startMs':6000,'endMs':11900,'text':text[cut:]}]
    board={'scenes':[{'id':'first','from_cue':0,'to_cue':0,'script_start':0,'script_end':cut,'start':0,'end':6},
       {'id':'second','label':'总结画面','from_cue':1,'to_cue':1,'script_start':cut,'script_end':len(text),'start':6,'end':12,
        'asset':{'id':'matched'},'clip':{'source_in':23}}]}
    rows=search.segments(d,cues,board,None,None,None)
    assert rows[0]['control']=='quote' and rows[1]['props']['src']=='asset:matched'
    assert (rows[1]['t0'],rows[1]['t1'],rows[1]['props']['sourceStart'])==(6,12,23)
    assert ''.join(r['$text'] for r in rows)==text


def test_matching_plan_runs_selected_source_once_then_reuses_clip_and_decode(tmp_path,monkeypatch):
    from backlot import studio_storyboard as planning,studio_material_clips as clips
    d=draft();cut=d['text'].index('最后');media=tmp_path/'source.mp4';media.write_bytes(b'cached original video')
    studio=SimpleNamespace(asset=lambda *a:media)
    calls=[]
    monkeypatch.setattr(planning,'TrialRelay',lambda *a:SimpleNamespace(folder=tmp_path))
    monkeypatch.setattr(planning,'make_plan',lambda *a:{'duration':12,'scenes':[
        {'id':'scene-1','label':'办公室','from_cue':0,'to_cue':0,'script_start':0,'script_end':cut,'text':d['text'][:cut],'start':0,'end':6,'query':'办公室','asset_id':''},
        {'id':'scene-2','label':'总结','from_cue':1,'to_cue':1,'script_start':cut,'script_end':len(d['text']),'text':d['text'][cut:],'start':6,'end':12,'presentation':'text','asset_id':''}]})
    asset={'id':'actual-video','kind':'video','provenance':{'sha256':sha(media),'source':'douyin','source_url':'https://www.douyin.com/video/123','author':'作者','rights':'operator-declared-default'}}
    class Source:
        def __init__(self,*a):pass
        def douyin(self,scene):calls.append('douyin');return asset
        def pexels(self,scene):pytest.fail('not selected')
    monkeypatch.setattr(planning,'Sources',Source)
    def choose(s,d,scene,a,relay):
        calls.append('clip');return search.clip_binding(scene,a,2,8,'实际画面区间')
    monkeypatch.setattr(clips,'select_clip',choose)
    cues=[{'startMs':0,'endMs':5900,'text':d['text'][:cut]}, {'startMs':6000,'endMs':11900,'text':d['text'][cut:]}]
    first=search.storyboard(studio,d,tmp_path,12,cues,lambda *a:pytest.fail('no generation'))
    assert first['scenes'][0]['clip']['source_in']==2
    assert first['scenes'][1]['source_status']=='template-narrative'
    assert search.storyboard(studio,d,tmp_path,12,cues,None)==first
    assert calls==['douyin','clip']


def test_unknown_clip_review_keeps_same_candidate_identity_on_resume(tmp_path,monkeypatch):
    from backlot import studio_storyboard as planning,studio_material_clips as clips
    d=draft();media=tmp_path/'source.mp4';media.write_bytes(b'original')
    studio=SimpleNamespace(asset=lambda *a:media)
    monkeypatch.setattr(planning,'TrialRelay',lambda *a:SimpleNamespace(folder=tmp_path))
    scene={'id':'s','label':'办公室','asset_id':'','query':'办公室','start':0,'end':6,'script_start':0,'script_end':len(d['text']),'text':d['text'],'from_cue':0,'to_cue':0}
    monkeypatch.setattr(planning,'make_plan',lambda *a:{'duration':6,'scenes':[scene]})
    calls=[]
    asset={'id':'once','kind':'video','provenance':{'sha256':sha(media),'source':'douyin','source_url':'https://www.douyin.com/video/123'}}
    class Source:
        def __init__(self,*a):pass
        def douyin(self,s):calls.append('source');return asset
    monkeypatch.setattr(planning,'Sources',Source)
    seen=[]
    def unknown(*args):
        seen.append(copy.deepcopy(args[2]));raise WorkError('原片段核验结果待查询','unavailable')
    monkeypatch.setattr(clips,'select_clip',unknown)
    for _ in range(2):
        with pytest.raises(WorkError,match='待查询'):search.storyboard(studio,d,tmp_path,6,[],None)
    assert calls==['source'] and seen[0]==seen[1] and seen[1]['candidate_asset']['id']=='once'


def test_avatar_entry_plans_clips_with_complete_sentences_before_avatar_submission(tmp_path,monkeypatch):
    from backlot.studio import Studio
    from backlot.studio_avatar import run_avatar,key_identity
    from backlot import studio_asr
    from backlot import studio_template_execution
    studio=Studio(tmp_path/'projects')
    d=studio.save_draft({'template_id':'avatar-safe-circle-v1','text':'第一段第二段'})
    d['input']={'soundMode':'audio','subtitles':True,'templateExecution':'auto','ai':{'enabled':True}}
    project=studio.projects_root/d['id'];project.mkdir(parents=True);audio=project/'audio.wav';audio.write_bytes(b'cached source')
    actual={'segments':[{'start':.1,'end':2.8,'text':d['text'],'words':[
        {'start':.1,'end':.4,'text':'第一段'},{'start':2.2,'end':2.8,'text':'第二段'}]}]}
    monkeypatch.setattr(studio_asr,'transcribe',lambda *a:actual)
    monkeypatch.setattr(studio_template_execution,'snapshot',lambda draft:{'test_contract':'frozen'})
    seen=[]
    def source(s,draft,folder,duration,cues,paid):
        seen.extend(cues);raise WorkError('素材来源当前不可用','unavailable')
    monkeypatch.setattr(search,'storyboard',source)
    class NoGeneration:
        def quote(self,*a):pytest.fail('must not generate before sourcing succeeds')
        def confirm(self,*a):pytest.fail('must not submit avatar')
    request={'id':'source-preflight','draft':d,'key_identity':key_identity(studio),'render_id':'test',
        'asr':{'provider':'local-whisper','identity':studio_asr.identity(studio_asr.configuration(studio))},
        'automatic_template_execution':{'test_contract':'frozen'},'quotes':{},'prepared':{'audio_path':str(audio),'duration':3}}
    result=run_avatar(project,request,NoGeneration())
    assert result['status']=='failed' and len(seen)==1,result
    assert (seen[0]['startMs'],seen[0]['endMs'],seen[0]['text'])==(100,2800,d['text'])
