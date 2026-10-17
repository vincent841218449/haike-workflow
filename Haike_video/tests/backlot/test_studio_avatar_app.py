import json
import hashlib
import subprocess
import shutil
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from backlot.studio import Studio
from backlot.studio_avatar_app import PROFILE_PATH, frame_segments, produce, _split_audio, _stitch, _verify_clip
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


def test_flat_balance_rejection_without_status_is_not_an_unknown_submission():
    response=Response({'errorCode':'416','errorMessage':'wallet insufficient'})
    client=RunningHubAIAppClient('test-key',json.loads(PROFILE_PATH.read_text()),SimpleNamespace(post=lambda *a,**k:response))
    result=client.submit('portrait','audio')
    assert result['status']=='FAILED' and result['error_code']=='416' and not result['task_id']
    assert '余额' in result['message']


@pytest.mark.parametrize('api_type,coins',[('SHARED','99999'),('NORMAL','0'),('NORMAL',None),('NORMAL','NaN')])
def test_coin_mode_rejects_wallet_keys_or_unavailable_coins_before_submit(api_type,coins):
    calls=[]
    def post(url,**kwargs):
        calls.append(url)
        return Response({'code':0,'data':{'apiType':api_type,'remainCoins':coins,'remainMoney':'1000'}})
    client=RunningHubAIAppClient('test-key',json.loads(PROFILE_PATH.read_text()),SimpleNamespace(post=post))
    with pytest.raises(RunningHubAvatarError):client.ensure_billing_mode('rh_coins')
    assert calls==['https://www.runninghub.cn/uc/openapi/accountStatus']


def test_coin_mode_verifies_member_key_without_generation():
    calls=[]
    def post(url,**kwargs):
        calls.append((url,kwargs))
        return Response({'code':0,'data':{'apiType':'NORMAL','remainCoins':'50000','remainMoney':'0'}})
    client=RunningHubAIAppClient('test-member',json.loads(PROFILE_PATH.read_text()),SimpleNamespace(post=post))
    assert client.ensure_billing_mode('rh_coins')['apiType']=='NORMAL'
    assert len(calls)==1 and calls[0][0].endswith('/accountStatus')
    assert calls[0][1]['allow_redirects'] is False


def test_coin_default_preserves_original_credential_and_never_falls_back(tmp_path,monkeypatch):
    from backlot.studio import atomic_private
    from backlot.studio_avatar_app import configuration,snapshot,verify_execution,execution_key
    monkeypatch.delenv('RUNNINGHUB_COINS_API_KEY',raising=False)
    studio=Studio(tmp_path/'projects')
    (tmp_path/'.env.secrets.local').write_text('RUNNINGHUB_API_KEY=test-wallet\nRUNNINGHUB_COINS_API_KEY=test-coins\n')
    path=studio.private/'haike-api/avatar.local.json'
    atomic_private(path,{'enabled':True})
    old=snapshot(studio)
    atomic_private(path,{'enabled':True,'billing_mode':'rh_coins'})
    coins=snapshot(studio);config=configuration(studio)
    assert coins['billing_mode']=='rh_coins' and coins['identity']!=old['identity']
    verify_execution(studio,old)
    assert execution_key(config,old)=='test-wallet' and execution_key(config,coins)=='test-coins'
    assert 'test-coins' not in json.dumps(coins)
    (tmp_path/'.env.secrets.local').write_text('RUNNINGHUB_API_KEY=test-wallet\n')
    assert not configuration(studio)['ready']
    with pytest.raises(WorkError,match='会员密钥'):snapshot(studio)


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
    state=json.loads((app_rig[2]/'avatar-app/state.json').read_text())
    assert state['chunks'][0]['submission_diagnostic']['exception_type']=='TimeoutError'
    assert 'lost response' not in json.dumps(state)


def test_later_unknown_segment_does_not_borrow_previous_successful_task_id(app_rig):
    client=app_rig[5];submit=client.submit
    def third_lost(image,audio):
        if len(client.calls)==2:
            client.calls.append(audio);raise TimeoutError('private-response-not-recorded')
        return submit(image,audio)
    client.submit=third_lost
    result=run(app_rig)
    assert result['status']=='submission_unknown' and result['upstream_ids']==['1','2']
    assert result['upstream_id'] is None
    assert run(app_rig)['status']=='submission_unknown' and len(client.calls)==3


def test_coin_override_does_not_reissue_unknown_or_change_successful_segments(app_rig,monkeypatch):
    from backlot.studio_avatar_app import _advance
    client=app_rig[5];submit=client.submit
    def third_lost(image,audio):
        if len(client.calls)==2:
            client.calls.append(audio);raise TimeoutError('lost')
        return submit(image,audio)
    client.submit=third_lost
    assert run(app_rig)['status']=='submission_unknown'
    path=app_rig[2]/'avatar-app/state.json';before=json.loads(path.read_text())
    coins={**app_rig[1],'identity':'member-key','billing_mode':'rh_coins'}
    monkeypatch.setattr('backlot.studio_avatar_app.verify_execution',lambda *args:None)
    assert _advance(*app_rig[:5],[],client=client,billing_execution=coins)['status']=='submission_unknown'
    after=json.loads(path.read_text())
    assert after['chunks']==before['chunks'] and len(client.calls)==3


@pytest.mark.parametrize('lost_again',[False,True])
def test_one_authorized_coin_reissue_preserves_success_unknown_and_recovery(app_rig,monkeypatch,lost_again):
    client=app_rig[5];submit=client.submit
    def third_lost(image,audio):
        if len(client.calls)==2:
            client.calls.append(audio);raise TimeoutError('lost')
        return submit(image,audio)
    client.submit=third_lost
    assert run(app_rig)['status']=='submission_unknown'
    path=app_rig[2]/'avatar-app/state.json';before=json.loads(path.read_text())
    before['recovery']={'reason':'terminal_805_after_55m','previous_chunks':[{'task_id':'old-failed'}]}
    path.write_text(json.dumps(before))
    coins={**app_rig[1],'identity':'member-key','billing_mode':'rh_coins'}
    authorization={'approval_ref':'user-third-once','chunk_index':2,'expected_state_sha256':sha(path),
                   'state_id':before['id'],'execution':coins}
    monkeypatch.setattr('backlot.studio_avatar_app.verify_execution',lambda *args:None)
    client.submit=submit;client.unknown=lost_again;client.query_failure=True
    def advance():
        return produce(*app_rig[:5],[],client=client,billing_execution=coins,submission_reissue=authorization)
    result=advance()
    assert result['status']==('submission_unknown' if lost_again else 'running')
    assert len(client.calls)==4
    state=json.loads(path.read_text())
    assert state['chunks'][:2]==before['chunks'][:2] and state['recovery']==before['recovery']
    assert state['unknown_attempts'][0]['status']=='submission_unknown'
    assert state['unknown_attempts'][0]['submitted_at']==before['chunks'][2]['submitted_at']
    assert state['unknown_attempts'][0]['execution']==app_rig[1]
    assert state['chunks'][2]['execution']==coins
    assert len(state['submission_reissues'])==1 and result['cost_status']=='supplier_bill_pending'
    assert advance()['status']==result['status'] and len(client.calls)==4
    client.query_failure=False
    assert advance()['status']==('submission_unknown' if lost_again else 'succeeded')
    assert len(client.calls)==4


@pytest.mark.parametrize('change',['hash','task_id','success','other_chunk','wallet','profile'])
def test_reissue_rejects_changed_or_queryable_attempt_without_payment(app_rig,monkeypatch,change):
    client=app_rig[5];client.unknown=True
    assert run(app_rig)['status']=='submission_unknown'
    path=app_rig[2]/'avatar-app/state.json';state=json.loads(path.read_text())
    coins={**app_rig[1],'billing_mode':'rh_coins'}
    auth={'approval_ref':'once','chunk_index':0,'state_id':state['id'],'execution':coins}
    if change=='task_id':state['chunks'][0]['task_id']='accepted'
    if change=='success':state['chunks'][0]['status']='succeeded'
    if change=='other_chunk':auth['chunk_index']=1
    if change=='wallet':coins['billing_mode']='provider_default'
    if change=='profile':coins['profile']={'app_id':'other'}
    path.write_text(json.dumps(state));auth['expected_state_sha256']='0'*64 if change=='hash' else sha(path)
    monkeypatch.setattr('backlot.studio_avatar_app.verify_execution',lambda *args:None)
    with pytest.raises(WorkError):
        produce(*app_rig[:5],[],client=client,billing_execution=coins,submission_reissue=auth)
    assert len(client.calls)==1 and json.loads(path.read_text())==state


def test_coin_override_only_changes_unsubmitted_segments_and_uses_separate_uploads(app_rig,monkeypatch):
    from backlot.studio_avatar_app import _advance
    wallet=app_rig[5];wallet.query_failure=True
    assert run(app_rig)['status']=='running'
    wallet.query_failure=False
    coins={**app_rig[1],'identity':'member-key','billing_mode':'rh_coins'}
    member=type(wallet)();member.calls=[]
    monkeypatch.setattr('backlot.studio_avatar_app.verify_execution',lambda *args:None)
    result=_advance(*app_rig[:5],[],client=None,billing_execution=coins,
                    client_for_execution=lambda execution:member if execution==coins else wallet)
    state=json.loads((app_rig[2]/'avatar-app/state.json').read_text())
    assert result['status']=='succeeded'
    assert wallet.calls==['audio-000.wav'] and member.calls==['audio-001.wav','audio-002.wav']
    assert 'execution' not in state['chunks'][0]
    assert all(c['execution']==coins for c in state['chunks'][1:])
    assert state['credential_uploads']['member-key']['image_file']==app_rig[4].name


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
    def verify(path,frames,reference=None,final_segment=False):
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


@pytest.mark.parametrize('code',['401','416'])
def test_explicit_provider_rejection_never_resubmits_or_runs_later_segments(app_rig,code):
    client=app_rig[5]
    def reject(image,audio):
        client.calls.append(audio)
        return {'status':'FAILED','task_id':'','error_code':code}
    client.submit=reject
    assert run(app_rig)['status']=='failed'
    assert run(app_rig)['status']=='failed' and len(client.calls)==1
    state=json.loads((app_rig[2]/'avatar-app/state.json').read_text())
    assert state['chunks'][0]['submit_receipt']['error_code']==code


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


@pytest.mark.parametrize('seconds,padding',[(2,1),(9.96,1.92)])
def test_provider_tail_padding_reuses_original_audio_and_cached_download(app_rig,monkeypatch,seconds,padding):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from backlot.studio_render import media_probe
    ffmpeg,_=resolve_ffmpeg_pair()
    folder=app_rig[2];master=app_rig[3];provider=folder/'provider-padded.mp4'
    duration=seconds+padding
    subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i',f'sine=frequency=880:sample_rate=24000:duration={seconds}',
                    '-ac','1','-c:a','pcm_s16le',str(master)],check=True)
    subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i',f'color=navy:s=80x100:r=25:d={duration}',
                    '-i',str(master),'-af',f'apad=pad_dur={padding}','-t',str(duration),'-c:v','libx264','-c:a','aac',str(provider)],check=True)
    cache=folder/'avatar-app';cache.mkdir()
    shutil.copyfile(provider,cache/'video-000-00.invalid.mp4')
    monkeypatch.setattr('backlot.studio_avatar_app.media_probe',media_probe)
    monkeypatch.setattr('backlot.studio_avatar_app._verify_clip',_verify_clip)
    monkeypatch.setattr('backlot.studio_avatar_app._stitch',_stitch)
    def no_second_download(*args): raise AssertionError('already downloaded paid result must be reused')
    monkeypatch.setattr('backlot.studio_avatar.download_result',no_second_download)
    result=run(app_rig)
    assert result['status']=='succeeded' and len(app_rig[5].calls)==1
    state=json.loads((cache/'state.json').read_text())
    assert state['chunks'][0]['tail_padding']['seconds']==pytest.approx(padding)
    assert state['chunks'][0]['tail_padding']['audio_correlation']>.98
    assert abs(media_probe(folder/'avatar-source.mp4')['duration']-seconds)<.05


@pytest.mark.parametrize('seconds,padding,delay,final',[
    (9.96,1.92,0,False),(10.04,1.92,0,True),(9.96,2.04,0,True),(9.96,1.92,.5,True),
])
def test_short_terminal_padding_keeps_scope_bound_and_audio_alignment(tmp_path,seconds,padding,delay,final):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg,_=resolve_ffmpeg_pair();master=tmp_path/'master.wav';provider=tmp_path/'provider.mp4'
    subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i',f'sine=frequency=887:sample_rate=24000:duration={seconds}',
                    '-ac','1','-c:a','pcm_s16le',str(master)],check=True)
    duration=str(seconds+padding)
    subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i',f'color=navy:s=80x100:r=25:d={duration}',
                    '-i',str(master),'-af',f'adelay={delay*1000}:all=1,apad','-t',duration,
                    '-c:v','libx264','-c:a','aac',str(provider)],check=True)
    with pytest.raises(WorkError,match='时长|原音轨'):
        _verify_clip(provider,round(seconds*25),master,final)


@pytest.mark.parametrize('delay,padding',[(.5,1),(0,2)])
def test_tail_padding_does_not_accept_offset_audio_or_excessive_extra_video(tmp_path,delay,padding):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from backlot.studio_avatar_app import _verify_clip
    ffmpeg,_=resolve_ffmpeg_pair();master=tmp_path/'master.wav';provider=tmp_path/'provider.mp4'
    subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i','sine=frequency=887:sample_rate=24000:duration=2',
                    '-ac','1','-c:a','pcm_s16le',str(master)],check=True)
    duration=str(2+padding)
    subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i',f'color=navy:s=80x100:r=25:d={duration}',
                    '-i',str(master),'-af',f'adelay={delay*1000}:all=1,apad','-t',duration,
                    '-c:v','libx264','-c:a','aac',str(provider)],check=True)
    with pytest.raises(WorkError,match='时长|原音轨'):
        _verify_clip(provider,50,reference=master)
