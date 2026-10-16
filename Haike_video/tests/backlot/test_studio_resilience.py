"""Recovery contracts with isolated files and fake suppliers; no paid calls."""
import json
from types import SimpleNamespace

import pytest

from backlot.studio import Studio, atomic_private
from backlot.studio_avatar import key_identity, run_avatar
from backlot.work_catalog import WorkError


def test_caption_spelling_uses_original_script_without_changing_speech_clock():
    from backlot.studio_avatar import source_captions
    draft={'text':'各位老板，我问一个问题。心里想下就行。去年大年三十，你在哪？'}
    cues=[{'startMs':0,'endMs':2900,'text':'各位老板,我问一个问题。'},
          {'startMs':3500,'endMs':4560,'text':'心理想像就行。'},
          {'startMs':5400,'endMs':7300,'text':'去年大年三十,你在哪?'}]
    corrected=source_captions(draft,cues)
    assert [c['text'] for c in corrected]==['各位老板，我问一个问题。','心里想下就行。','去年大年三十，你在哪？']
    assert [(c['startMs'],c['endMs']) for c in corrected]==[(c['startMs'],c['endMs']) for c in cues]
    with pytest.raises(WorkError):source_captions({'text':'这是完全不同的语音内容，不是这次口播。'},cues)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    studio = Studio(tmp_path / 'projects')
    draft = studio.save_draft({'template_id': 'avatar-safe-circle-v1', 'title': '测试', 'text': '今天讲工程结算。',
                              'input': {'soundMode': 'audio', 'subtitles': True}})
    project = studio.projects_root / draft['id']; project.mkdir(parents=True)
    audio = project / 'drive.wav'; audio.write_bytes(b'original-narration')
    request = {'id': 'original-quote', 'workflow_version': 2, 'draft': draft, 'key_identity': key_identity(studio),
               'render_id': 'test', 'prepared': {'audio_path': str(audio), 'audio_file': 'audio-1', 'image_file': 'image-1', 'duration': 3},
               'quotes': {k: {'model': m, 'max_charge_micros': n} for k, m, n in [('asr', 'haike/tencent-asr', 10), ('avatar', 'haike/avatar', 100)]},
               'max_charge_micros': 110}
    events = []
    class Gateway:
        speech = draft['text']
        status = 'succeeded'
        artifact = False
        def confirm(self, quote, maximum, identity):
            events.append(('confirm', quote['model'], identity)); return identity
        def wait(self, intent, timeout):
            asr = intent.endswith(__import__('hashlib').sha256((request['id']+':asr').encode()).hexdigest()[:32])
            events.append(('wait', 'asr' if asr else 'avatar', timeout))
            result = {'segments': [{'start': 0, 'end': 3, 'text': self.speech}]} if asr else {'video_url': 'https://supplier.example/original.mp4'}
            return {'id': 'asr-job' if asr else 'original-avatar-job', 'status': 'succeeded' if asr else self.status,
                    'upstream_id': 'original-provider-task', 'media_artifact_available': self.artifact, 'result': result}
    gateway = Gateway()
    monkeypatch.setattr('backlot.studio_storyboard.produce', lambda *a: None)
    monkeypatch.setattr('backlot.studio_avatar.download_result', lambda url, path: path.write_bytes(b'paid-avatar'))
    def compose(folder, effective, *args, **kwargs):
        events.append(('compose', effective['input'].get('outputLayout'), effective['template_id']))
        output = folder / 'avatar-preview.mp4'; output.write_bytes(b'render'); return output
    monkeypatch.setattr('backlot.studio_composition.compose_avatar', compose)
    return studio, project, request, gateway, events


def test_mismatched_sample_audio_stops_before_avatar_spending(rig):
    _, project, request, gateway, events = rig
    gateway.speech = '海客科技让创作更简单，一个接口连接配音数字人和创作工作流。'
    result = run_avatar(project, request, gateway)
    assert result['status'] == 'awaiting_human'
    assert result['error']['code'] == 'audio_script_mismatch'
    assert [e[1] for e in events if e[0] == 'confirm'] == ['haike/tencent-asr']


@pytest.mark.parametrize('strict', [False, True])
def test_incompatible_native_motion_stays_selected_and_stops_before_avatar(rig, monkeypatch, strict):
    _, project, request, gateway, events = rig
    request['draft']['input'].update(motion={'style': '03-A', 'layout': 'landscape'}, templatePolicy='strict' if strict else 'auto')
    def invalid(*args):
        events.append(('preflight',)); raise WorkError('AI动效分镜数量不一致')
    monkeypatch.setattr('backlot.studio_storyboard.select_motion', invalid)
    result = run_avatar(project, request, gateway)
    assert result['status'] == 'awaiting_human' and result['error']['code'] == 'template_incompatible'
    assert not any(e[0] == 'confirm' and e[1] == 'haike/avatar' for e in events)


def test_instrument_story_keeps_selected_style_through_pipeline_without_basic_composer(rig,monkeypatch):
    _,project,request,gateway,events=rig
    request['draft']['input'].update(motion={'style':'04-A','layout':'portrait'})
    story={'status':'ready','duration':3,'scenes':[{'id':'scene-1','start':0,'end':3,'text':request['draft']['text'],'asset':{'id':'source'},'asset_sha256':'frozen'}]}
    monkeypatch.setattr('backlot.studio_storyboard.produce',lambda *a:story)
    def compose(folder,*args):
        events.append(('instrument',args[-1]['id']));output=folder/'motion-preview.mp4';output.write_bytes(b'instrument');return output
    monkeypatch.setattr('backlot.studio_composition.compose_instrument',compose)
    result=run_avatar(project,request,gateway)
    assert result['status']=='completed'
    assert result['result']['presentation']['id']==result['result']['requested_presentation']['id']=='adu:04-A:portrait'
    assert ('instrument','adu:04-A:portrait') in events and not any(e[0]=='compose' for e in events)


def test_local_recomposition_cannot_start_missing_paid_stage(rig):
    _,project,request,gateway,events=rig
    request['local_recomposition']=True
    result=run_avatar(project,request,gateway)
    assert result['status']=='awaiting_human' and result['error']['code']=='local_artifact_missing'
    assert not events


def test_wrong_style_from_renderer_is_not_registered_as_completed(rig,monkeypatch):
    _,project,request,gateway,_=rig
    request['draft']['input']['motion']={'style':'04-A','layout':'portrait'}
    monkeypatch.setattr('backlot.studio_preflight.prepare',lambda *a,**k:{'mode':'motion','draft':request['draft'],'notice':''})
    monkeypatch.setattr('backlot.studio_storyboard.compose_motion',lambda *a,**k:{'status':'completed','result':{'output_path':'wrong.mp4','presentation':{'id':'adu:03-A:portrait'}}})
    result=run_avatar(project,request,gateway)
    assert result['status']=='awaiting_human' and result['error']['code']=='template_mismatch'


def test_unknown_provider_is_automatic_wait_and_reuses_one_intent(rig):
    _, project, request, gateway, events = rig
    gateway.status = 'submission_unknown'
    for _ in range(2):
        result = run_avatar(project, request, gateway)
        assert result['status'] == 'ambiguous' and result['error']['code'] == 'provider_pending'
    avatar_calls = [e for e in events if e[:2] == ('confirm', 'haike/avatar')]
    assert len(avatar_calls) == 1
    assert ('wait', 'avatar', 3600) in events


def test_billing_pending_with_actual_artifact_continues_without_faking_settlement(rig):
    _, project, request, gateway, _ = rig
    gateway.status = 'submission_unknown'; gateway.artifact = True
    assert run_avatar(project, request, gateway)['status'] == 'completed'
    state = json.loads((project / 'renders/test/gateway-state.json').read_text())
    assert state['stages']['avatar']['job']['status'] == 'submission_unknown'
    assert (project / 'renders/test/avatar-source.mp4').read_bytes() == b'paid-avatar'


def test_ancestor_reserved_cost_counts_before_any_new_avatar_call(rig):
    _, project, request, gateway, events = rig
    request['inherited_charge_micros'] = 100
    result = run_avatar(project, request, gateway)
    assert result['status'] == 'awaiting_human' and result['error']['code'] == 'budget_exceeded'
    assert not any(e[0] == 'confirm' and e[1] == 'haike/avatar' for e in events)


def test_motion_group_can_cover_adjacent_material_scenes_but_cannot_skip_required_assets(rig, monkeypatch):
    from backlot.studio_storyboard import select_motion
    studio, project, request, _, _ = rig
    draft = request['draft']; draft['input']['ai'] = {'materials': []}
    style = {'groups':[{'id':'group', 'duration':{'minFrames':180}, 'fields':[{'id':'media','type':'video'}]}]}
    scenes = [{'id':'scene-1','start':0,'end':1.5,'text':'今天','label':'一','from_cue':0,'to_cue':0,'asset':{'id':'a','kind':'video'}},
              {'id':'scene-2','start':1.5,'end':3,'text':'讲工程结算。','label':'二','from_cue':1,'to_cue':1,'asset':{'id':'b','kind':'video'}}]
    body = {'segments':[{'scene_ids':['scene-1','scene-2'],'group':'group','values':{'media':{'asset_id':'a'}},'anchors':{'start':0}}]}
    monkeypatch.setattr('backlot.studio_storyboard.motion_options', lambda d: style)
    monkeypatch.setattr('backlot.studio_storyboard.TrialRelay', lambda *a: SimpleNamespace(call=lambda *args: {'choices':[{'message':{'content':json.dumps(body)}}]}))
    cues = [{'startMs':0,'text':'今天'},{'startMs':1500,'text':'讲工程结算。'}]
    normalized = select_motion(studio,draft,project,cues,{'scenes':scenes})
    assert len(normalized) == 1 and normalized[0]['text'] == '今天讲工程结算。' and normalized[0]['end'] == 3
    (project / 'motion-selection.json').unlink()
    draft['input']['ai']['materials'] = [{'id':'b','mode':'must'}]
    with pytest.raises(WorkError, match='必须使用'): select_motion(studio,draft,project,cues,{'scenes':scenes})
    body['segments'][0]['scene_ids'] = ['scene-2']
    with pytest.raises(WorkError, match='原文顺序'): select_motion(studio,draft,project,cues,{'scenes':scenes})


def test_continuation_reuses_artifacts_and_counts_unknown_ancestor_once(rig):
    from copy import deepcopy
    from backlot.production_queue import ProductionQueue
    from backlot.studio_creation import continue_request
    studio, project, request, gateway, _ = rig
    (project/'project.json').write_text('{"title":"测试"}')
    queue = ProductionQueue(project.parent.parent/'queue.sqlite3', studio.projects_root)
    first = queue.submit(project_id=request['draft']['id'],kind='studio_avatar',source='workbench',priority='normal',parent_job_id='old',frozen_request={**request,'render_id':'old'})
    queue.claim_next('w'); queue.finish(first['job_id'],'w',status='failed',stage='旧请求未知')
    atomic_private(project/'renders/old/gateway-state.json',{'prepared':request['prepared'],'stages':{'avatar':{'quote':{'max_charge_micros':100},'intent':'original-unknown','job':{'id':'original','status':'submission_unknown'}}}})
    assert run_avatar(project,request,gateway)['status']=='completed'
    second=queue.submit(project_id=request['draft']['id'],kind='studio_avatar',source='workbench',priority='normal',parent_job_id='test',frozen_request=request)
    queue.claim_next('w'); queue.finish(second['job_id'],'w',status='completed',stage='已有数字人')
    queue.link_creation(second['job_id'],first['job_id'],'regeneration')
    next_request=deepcopy(request);next_request.update(render_id='new',id='new-quote',max_charge_micros=210)
    next_request['draft']['revision']+=1
    next_request['draft']['layout']['title_size']=48
    frozen=continue_request(studio,queue,next_request,second['job_id'])
    assert frozen['inherited_charge_micros']==100
    state=json.loads((project/'renders/new/gateway-state.json').read_text())
    assert len(state['stages'])==2 and (project/'renders/new/avatar-source.mp4').read_bytes()==b'paid-avatar'
    assert continue_request(studio,queue,next_request,second['job_id']) == frozen
    over=deepcopy(next_request);over['render_id']='over';over['max_charge_micros']=209
    with pytest.raises(WorkError,match='总上限'):continue_request(studio,queue,over,second['job_id'])
    assert not (project/'renders/over/gateway-state.json').exists()
    switched=deepcopy(next_request);switched.update(key_identity='another-account',render_id='other-account')
    with pytest.raises(WorkError,match='原API账户'):continue_request(studio,queue,switched,second['job_id'])
    third=queue.submit(project_id=request['draft']['id'],kind='studio_avatar',source='workbench',priority='normal',parent_job_id='new',frozen_request=frozen)
    assert len(queue.creation_members(third['job_id']))==3
    assert queue.list(collapse_creations=True)['pagination']['total']==1
