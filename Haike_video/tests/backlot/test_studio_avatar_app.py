import json
import hashlib
import subprocess
import shutil
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from backlot.studio import Studio
from backlot.studio_avatar_app import PROFILE_PATH, frame_segments, produce, _split_audio, _stitch
from backlot.work_catalog import WorkError, sha
from tools.avatar.runninghub_ai_app import RunningHubAIAppClient
from tools.avatar.runninghub_avatar import RunningHubAvatarError


def test_segments_cover_109_seconds_exactly_and_prefer_real_sentence_boundaries():
    parts=frame_segments(2727,[{'endMs':42000},{'endMs':81000}])
    assert parts==[{'start_frame':0,'end_frame':1050},{'start_frame':1050,'end_frame':2025},{'start_frame':2025,'end_frame':2727}]
    assert sum(p['end_frame']-p['start_frame'] for p in parts)==2727
    for n in [1,1125,1126,1250,3000]:
        p=frame_segments(n,[])
        assert p[0]['start_frame']==0 and p[-1]['end_frame']==n
        assert all(0<c['end_frame']-c['start_frame']<=1125 for c in p)
        assert all(a['end_frame']==b['start_frame'] for a,b in zip(p,p[1:]))


def audio(path,frames=2727):
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000)
        w.writeframes((b'\x01\x02\x03\x04'*(frames*960//2)))


def test_audio_chunks_reconstruct_every_original_sample(tmp_path):
    original=tmp_path/'original.wav';audio(original)
    chunks=frame_segments(2727,[{'endMs':42000},{'endMs':81000}]);combined=b''
    for i,c in enumerate(chunks):
        output=tmp_path/f'{i}.wav';_split_audio(original,output,c['start_frame'],c['end_frame'])
        with wave.open(str(output)) as w: combined+=w.readframes(w.getnframes())
    with wave.open(str(original)) as w: assert w.readframes(w.getnframes())==combined


class Response:
    ok=True;status_code=200
    def __init__(self,value): self.value=value
    def json(self): return self.value


@pytest.mark.parametrize('envelope',[False,True])
def test_official_app_payload_and_checkpoint_id(envelope):
    calls=[]
    def post(url,**kw):
        calls.append((url,kw)); data={'taskId':'123456','status':'QUEUED'}
        return Response({'code':0,'data':data} if envelope else data)
    profile=json.loads(PROFILE_PATH.read_text()); client=RunningHubAIAppClient('test-key',profile,SimpleNamespace(post=post))
    assert client.submit('portrait.jpg','audio.wav')['task_id']=='123456'
    url,kwargs=calls[0]
    assert url=='https://www.runninghub.cn/openapi/v2/run/ai-app/2006270540499128322'
    body=kwargs['json']
    assert body['instanceType']=='plus' and body['usePersonalQueue'] is False
    nodes={(n['nodeId'],n['fieldName']):n['fieldValue'] for n in body['nodeInfoList']}
    assert nodes=={('284','image'):'portrait.jpg',('125','audio'):'audio.wav',('312','value'):'1280',
                  ('314','prompt'):profile['prompt'],('369','value'):'0',('370','value'):'1'}
    assert not {'workflowId','apiKey','retainSeconds'} & body.keys()
    assert kwargs['allow_redirects'] is False


def test_query_throttling_is_a_read_failure_and_never_a_failed_generation():
    response=Response({'error':'rate limit'});response.status_code=429;response.ok=False
    client=RunningHubAIAppClient('test-key',json.loads(PROFILE_PATH.read_text()),SimpleNamespace(post=lambda *a,**k:response))
    with pytest.raises(RunningHubAvatarError,match='查询'):client.poll('original-task')


def test_non_json_auth_rejection_is_definite_before_a_task_is_accepted():
    class Denied:
        status_code=403;ok=False
        def json(self):raise ValueError('HTML forbidden')
    client=RunningHubAIAppClient('test-key',json.loads(PROFILE_PATH.read_text()),SimpleNamespace(post=lambda *a,**k:Denied()))
    result=client.submit('portrait','audio')
    assert result['status']=='FAILED' and result['error_code']=='403' and not result['task_id']


@pytest.fixture
def app_rig(tmp_path,monkeypatch):
    studio=Studio(tmp_path/'projects');folder=studio.projects_root/'studio-test'/'renders/test'
    folder.mkdir(parents=True);wav=folder/'narration.wav';audio(wav)
    portrait=folder/'portrait.jpg';portrait.write_bytes(b'owned-portrait')
    profile=json.loads(PROFILE_PATH.read_text())
    execution={'identity':'frozen-key-and-profile','profile':profile,'profile_sha256':hashlib.sha256(json.dumps(profile,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'billing_notice':'按供应商用量结算'}
    monkeypatch.setattr('backlot.studio_avatar_app.configuration',lambda s:{'identity':execution['identity'],'profile':profile,'key':'test-key'})
    monkeypatch.setattr('backlot.studio_avatar_app.media_probe',lambda p:{'duration':109.08,'video':{'width':448,'height':560},'audio':{}})
    monkeypatch.setattr('backlot.studio_avatar_app._verify_clip',lambda *a:{'video':{'width':448,'height':560}})
    monkeypatch.setattr('backlot.studio_avatar_app._stitch',lambda folder,state,audio,target:target.write_bytes(b'joined-original-audio'))
    monkeypatch.setattr('backlot.studio_avatar.download_result',lambda url,path:path.write_bytes(b'original-paid-clip'))
    class Client:
        calls=[];unknown=False;query_failure=False
        def upload(self,path): return path.name
        def submit(self,image,audio):
            self.calls.append(audio)
            if self.unknown: raise TimeoutError('lost response')
            return {'task_id':str(len(self.calls)),'status':'RUNNING'}
        def poll(self,task):
            if self.query_failure: raise TimeoutError('query interrupted')
            return {'task_id':task,'status':'SUCCESS','videos':[{'url':'https://supplier.example/original.mp4'}],
                    'billing':{'cost_status':'unknown','provider_usage':{'consume_coins':'12.4'}}}
    client=Client();client.calls=[]
    return studio,execution,folder,wav,portrait,client


def run(rig): return produce(*rig[:5],[],client=rig[5])


def test_completed_segments_and_whole_audio_are_cached_without_resubmission(app_rig):
    studio,execution,folder,wav,portrait,client=app_rig
    original=sha(wav)
    result=run(app_rig)
    assert result['status']=='succeeded' and len(client.calls)==3
    assert result['upstream_ids']==['1','2','3']
    assert result['billing_source']=='local-provider' and result['billing_policy']=='actual_usage'
    assert len(result['usage_receipts'])==3 and 'charged_micros' not in result
    assert run(app_rig)['status']=='succeeded' and len(client.calls)==3 and sha(wav)==original
    state=json.loads((folder/'avatar-app/state.json').read_text())
    assert [c['end_frame']-c['start_frame'] for c in state['chunks']]==[1125,1125,477]


def test_unknown_submit_blocks_later_segments_and_never_replays(app_rig):
    client=app_rig[5];client.unknown=True
    assert run(app_rig)['status']=='submission_unknown'
    client.unknown=False
    assert run(app_rig)['status']=='submission_unknown' and len(client.calls)==1


def test_query_disconnect_uses_original_segment_id_and_continues_remaining_only(app_rig):
    client=app_rig[5];client.query_failure=True
    assert run(app_rig)['status']=='running' and len(client.calls)==1
    client.query_failure=False
    assert run(app_rig)['status']=='succeeded' and len(client.calls)==3


def test_download_disconnect_automatically_resumes_same_paid_result(app_rig,monkeypatch):
    def interrupted(url,path): raise TimeoutError('download interrupted')
    monkeypatch.setattr('backlot.studio_avatar.download_result',interrupted)
    assert run(app_rig)['status']=='running'
    assert len(app_rig[5].calls)==1
    state=json.loads((app_rig[2]/'avatar-app/state.json').read_text())
    assert state['chunks'][0]['task_id']=='1'
    monkeypatch.setattr('backlot.studio_avatar.download_result',lambda url,path:path.write_bytes(b'valid original clip'))
    assert run(app_rig)['status']=='succeeded'
    assert len(app_rig[5].calls)==3


def test_invalid_download_is_preserved_and_redownloaded_without_regeneration(app_rig,monkeypatch):
    cache=app_rig[2]/'avatar-app';cache.mkdir()
    (cache/'video-000-00.mp4').write_bytes(b'truncated')
    def verify(path,frames):
        if path.read_bytes()==b'truncated': raise WorkError('incomplete file')
        return {'video':{'width':448,'height':560}}
    monkeypatch.setattr('backlot.studio_avatar_app._verify_clip',verify)
    assert run(app_rig)['status']=='running'
    assert (cache/'video-000-00.invalid.mp4').read_bytes()==b'truncated'
    assert run(app_rig)['status']=='succeeded'
    assert len(app_rig[5].calls)==3


def test_continued_render_folder_retains_original_segment_ids_and_local_job_id(app_rig):
    studio,execution,folder,wav,portrait,client=app_rig
    client.query_failure=True
    original=run(app_rig)
    new=folder.parent/'next-version';new.mkdir()
    shutil.copytree(folder/'avatar-app',new/'avatar-app')
    client.query_failure=False
    result=produce(studio,execution,new,wav,portrait,[],client=client)
    assert result['id']==original['id'] and result['status']=='succeeded'
    assert client.calls==['audio-000.wav','audio-001.wav','audio-002.wav']


def test_frozen_input_change_is_rejected_before_upload_or_submission(app_rig):
    client=app_rig[5];client.query_failure=True
    assert run(app_rig)['status']=='running'
    app_rig[4].write_bytes(b'different-picture')
    with pytest.raises(WorkError,match='输入已改变'):run(app_rig)
    assert len(client.calls)==1


def test_real_ffmpeg_stitch_uses_complete_master_audio_and_frame_clock(tmp_path):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from backlot.studio_render import media_probe
    ffmpeg,_=resolve_ffmpeg_pair();wav=tmp_path/'master.wav';audio(wav,50)
    chunks=[]
    for i,frames in enumerate([27,23]):
        path=tmp_path/f'segment-{i}.mp4'
        r=subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i',f'color=c={"red" if i==0 else "blue"}:s=80x100:r=25',
                          '-frames:v',str(frames),'-c:v','libx264','-pix_fmt','yuv420p',str(path)],capture_output=True)
        assert r.returncode==0
        chunks.append({'index':i,'start_frame':0 if i==0 else 27,'end_frame':27 if i==0 else 50,
                       'video_file':path.name,'video_sha256':sha(path)})
    target=tmp_path/'final.mp4';_stitch(tmp_path,{'chunks':chunks,'total_frames':50},wav,target)
    probe=media_probe(target)
    assert abs(probe['duration']-2)<.05 and probe['audio'] and probe['video']['width']==80


def test_new_audio_submission_freezes_app_and_never_quotes_legacy_workflow(tmp_path,monkeypatch):
    from PIL import Image
    from backlot.studio import atomic_private
    from backlot.studio_avatar import quote,frozen_request
    studio=Studio(tmp_path/'projects')
    atomic_private(studio.private/'haike-api/avatar.local.json',{'enabled':True})
    (tmp_path/'.env.secrets.local').write_text('RUNNINGHUB_API_KEY=test-local-key\n')
    draft=studio.save_draft({'template_id':'avatar-template3-card-3x4-v001','title':'测试新应用','text':'这是原始口播。','input':{'soundMode':'audio'}})
    portrait=tmp_path/'portrait.png';Image.new('RGB',(300,400),'navy').save(portrait)
    wav=tmp_path/'source.wav';audio(wav,75)
    image=studio.save_asset(draft['id'],'人物.png','image',portrait.read_bytes())
    sound=studio.save_asset(draft['id'],'原声.wav','audio',wav.read_bytes())
    draft=studio.save_draft({**draft,'input':{**draft['input'],'portrait':image,'audio':sound}})
    def unexpected(*args,**kwargs): raise AssertionError('new app must not upload/quote legacy gateway avatar')
    monkeypatch.setattr(studio,'client',lambda:SimpleNamespace(upload=unexpected,quote=unexpected))
    monkeypatch.setattr('backlot.studio_asr.snapshot',lambda s:{'provider':'local-whisper','identity':'local-asr'})
    result=quote(studio,draft)
    frozen=frozen_request(studio,draft,result['id'])
    assert frozen['avatar_execution']['profile']['app_id']=='2006270540499128322'
    assert frozen['avatar_execution']['billing_policy']=='actual_usage'
    assert frozen['prepared']['audio_file'] is None and frozen['prepared']['image_file'] is None
    assert frozen['quotes']=={} and frozen['draft']==draft
    assert 'test-local-key' not in json.dumps(frozen)
    atomic_private(studio.private/'haike-api/avatar.local.json',{'enabled':False})
    with pytest.raises(WorkError,match='配置已改变'):frozen_request(studio,draft,result['id'])


def test_frozen_app_parameters_survive_a_local_default_change(tmp_path,monkeypatch):
    from backlot.studio_avatar_app import verify_execution
    studio=Studio(tmp_path/'projects')
    profile=json.loads(PROFILE_PATH.read_text())
    execution={'identity':'same-key','profile':profile,'profile_sha256':hashlib.sha256(json.dumps(profile,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
    new_defaults={**profile,'long_edge':1024,'max_segment_frames':1000}
    monkeypatch.setattr('backlot.studio_avatar_app.configuration',lambda s:{'key':'key','identity':'same-key','profile':new_defaults})
    verify_execution(studio,execution)  # Frozen accepted parameters survive a default change.


def test_explicit_provider_rejection_never_resubmits_or_runs_later_segments(app_rig):
    client=app_rig[5]
    def reject(image,audio):
        client.calls.append(audio)
        return {'status':'FAILED','task_id':'','error_code':'401'}
    client.submit=reject
    assert run(app_rig)['status']=='failed'
    assert run(app_rig)['status']=='failed' and len(client.calls)==1


def test_terminal_long_running_805_is_split_once_and_keeps_original_receipt(app_rig):
    client=app_rig[5];client.query_failure=True
    assert run(app_rig)['status']=='running'
    path=app_rig[2]/'avatar-app/state.json'
    state=json.loads(path.read_text())
    state['chunks'][0]['submitted_at']='2026-01-01T00:00:00+00:00'
    path.write_text(json.dumps(state))
    original_poll=client.poll
    client.poll=lambda task:{'task_id':task,'status':'FAILED','error_code':'805','videos':[],
                             'billing':{'cost_status':'unknown','provider_usage':{}}}
    result=run(app_rig)
    assert result['status']=='running' and len(client.calls)==1
    state=json.loads(path.read_text())
    assert state['failed_attempts'][0]['task_id']=='1'
    assert state['failed_attempts'][0]['error_code']=='805'
    assert state['recovery']['reason']=='terminal_805_after_55m'
    assert all(c['end_frame']-c['start_frame']<=625 for c in state['chunks'])
    assert state['chunks'][0]['start_frame']==0 and state['chunks'][-1]['end_frame']==2727
    assert all(a['end_frame']==b['start_frame'] for a,b in zip(state['chunks'],state['chunks'][1:]))
    with wave.open(str(app_rig[3])) as source: expected=source.readframes(source.getnframes())
    actual=b''
    for chunk in state['chunks']:
        with wave.open(str(path.parent/f"audio-{chunk['index']:03d}.wav")) as source:
            actual+=source.readframes(source.getnframes())
    assert actual==expected
    client.query_failure=False;client.poll=original_poll
    result=run(app_rig)
    assert result['status']=='succeeded' and len(client.calls)==6
    assert result['upstream_ids']==['1','2','3','4','5','6']
    assert result['cost_status']=='supplier_bill_pending'
    assert run(app_rig)['status']=='succeeded' and len(client.calls)==6


@pytest.mark.parametrize('status,code,old',[
    ('RUNNING','805',True),('FAILED','401',True),('FAILED','805',False),
    ('CANCELLED','805',True),('FAILED','433',True),
])
def test_shortening_never_replays_pending_cancelled_or_unrelated_failures(app_rig,status,code,old):
    client=app_rig[5];client.query_failure=True
    run(app_rig)
    path=app_rig[2]/'avatar-app/state.json'
    state=json.loads(path.read_text())
    if old: state['chunks'][0]['submitted_at']='2026-01-01T00:00:00+00:00'
    path.write_text(json.dumps(state))
    client.poll=lambda task:{'task_id':task,'status':status,'error_code':code,'videos':[]}
    result=run(app_rig)
    assert result['status']==('running' if status=='RUNNING' else 'failed')
    assert len(client.calls)==1 and 'recovery' not in json.loads(path.read_text())


def test_failed_shortened_attempt_is_not_automatically_submitted_again(app_rig):
    client=app_rig[5];client.query_failure=True
    run(app_rig)
    path=app_rig[2]/'avatar-app/state.json'
    state=json.loads(path.read_text());state['recovery']={'reason':'terminal_805_after_55m'}
    state['chunks'][0]['submitted_at']='2026-01-01T00:00:00+00:00'
    path.write_text(json.dumps(state))
    client.poll=lambda task:{'task_id':task,'status':'FAILED','error_code':'805','videos':[]}
    assert run(app_rig)['status']=='failed'
    assert run(app_rig)['status']=='failed' and len(client.calls)==1


def test_late_success_on_failed_checkpoint_reuses_original_result(app_rig):
    client=app_rig[5];client.query_failure=True
    run(app_rig)
    path=app_rig[2]/'avatar-app/state.json'
    state=json.loads(path.read_text());state['status']='failed'
    state['chunks'][0].update(status='failed',error_code='805',submitted_at='2026-01-01T00:00:00+00:00')
    path.write_text(json.dumps(state));client.query_failure=False
    assert run(app_rig)['status']=='succeeded' and len(client.calls)==3
    assert 'recovery' not in json.loads(path.read_text())


def test_shortening_preserves_already_successful_chunks(app_rig):
    client=app_rig[5];original_poll=client.poll
    client.poll=lambda task:original_poll(task) if task=='1' else {'task_id':task,'status':'RUNNING','videos':[]}
    assert run(app_rig)['status']=='running' and len(client.calls)==2
    path=app_rig[2]/'avatar-app/state.json';state=json.loads(path.read_text())
    completed=state['chunks'][0].copy()
    state['chunks'][1]['submitted_at']='2026-01-01T00:00:00+00:00'
    path.write_text(json.dumps(state))
    client.poll=lambda task:{'task_id':task,'status':'FAILED','error_code':'805','videos':[]}
    assert run(app_rig)['status']=='running' and len(client.calls)==2
    assert json.loads(path.read_text())['chunks'][0]==completed
    client.poll=original_poll
    assert run(app_rig)['status']=='succeeded' and len(client.calls)==5
    assert json.loads(path.read_text())['chunks'][0]==completed
