"""Exercise the real local route with a fake supplier, never a real API key."""
import json
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest

from backlot.studio import Studio, atomic_private
from backlot import studio_system_voice as local, studio_voices
from backlot.work_catalog import WorkError


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_WORKSPACE_ID", raising=False)
    studio = Studio(tmp_path / "projects")
    atomic_private(studio.config_path, {"base_url": "http://127.0.0.1:17894/v2", "api_key": "fake-platform-key"})
    (tmp_path / ".env.secrets.local").write_text('DASHSCOPE_API_KEY="fake-local-provider-key"\n')
    atomic_private(studio.private / "haike-api/system-voices.local.json", {"enabled": True})
    class Remote:
        state_dir = studio.private / "remote-intents"
        def request(self, path, body=None, **kwargs):
            if path == "/capabilities":
                return {"items": [{"id": "haike/avatar", "model": "haike/avatar", "status": "available"}]}
            if path == "/voices":
                error = ValueError("missing library"); error.status = 404; raise error
            return {"remote": path}
        def quote(self, model, inputs, project_ref=""):
            return {"model": model, "remote": True}
        def confirm(self, quote, maximum, intent_id=None): return intent_id or "call_" + "e" * 32
        def resume(self, intent_id): return {"remote": intent_id}
        def wait(self, intent_id, timeout=300): return {"remote": intent_id}
    client = local.SystemVoiceClient(studio, Remote())
    monkeypatch.setattr(studio, "client", lambda: client)
    seen = []
    def post(self, url, **kwargs):
        seen.append({"url": url, **kwargs})
        return SimpleNamespace(status_code=200, json=lambda: {"request_id": "fake-request", "usage": {"characters": 5},
            "output": {"audio": {"url": "https://example.test/audio.wav"}}})
    monkeypatch.setattr(local.requests.Session, "post", post)
    def download(url, target):
        with wave.open(str(target), "wb") as output:
            output.setparams((1, 2, 24000, 0, "NONE", "not compressed")); output.writeframes(b"\0\0" * 2400)
    monkeypatch.setattr("backlot.studio_avatar.download_result", download)
    return studio, client, seen


def quote(client, voice="longanyun_v3"):
    return client.quote(local.MODEL, {"text": "你好。", "voice_id": "voice_bailian_cv3_" + voice}, "draft")


def test_all_seven_voices_are_ready_and_submit_the_exact_selected_voice(rig):
    studio, client, seen = rig
    library = studio_voices.catalogue(studio)
    presets = [v for v in library["items"] if v.get("sample_kind") == "official"]
    assert len(presets) == 7 and all(v["production_ready"] for v in presets)
    assert all("本地配音已接通" in v["production_hint"] for v in presets)
    for voice in presets:
        q = client.quote(voice["model"], {"text": "你好。", "voice_id": voice["id"]})
        assert q["max_charge_micros"] == "500"  # Han counts twice, punctuation once.
        intent = client.confirm(q, 500)
        job = client.wait(intent)
        assert job["status"] == "succeeded" and job["result"]["audio_base64"].startswith("UklGR")
        assert job["estimated_cost_micros"] == "500" and "charged_micros" not in job
        assert client.wait(intent) == job
        assert seen[-1]["json"]["input"]["voice"] == voice["id"].removeprefix("voice_bailian_cv3_")
        assert seen[-1]["json"]["model"] == "cosyvoice-v3-flash"
        assert seen[-1]["allow_redirects"] is False
    assert len(seen) == 7
    assert "fake-local-provider-key" not in json.dumps([library, q, job])
    assert "audio_url" not in job


def test_disabled_route_keeps_remote_models_and_existing_intents(rig):
    studio, client, seen = rig
    q = quote(client); intent = client.confirm(q, 1000)
    atomic_private(studio.private / "haike-api/system-voices.local.json", {"enabled": False})
    assert client.quote("haike/cosyvoice", {"text": "旧音色"})["remote"]
    assert client.quote(local.MODEL, {"text": "你好"})["remote"]
    assert len(client.request("/capabilities")["items"]) == 1
    assert client.wait(intent)["status"] == "succeeded" and len(seen) == 1
    assert client.wait("call_" + "b" * 32) == {"remote": "call_" + "b" * 32}


def test_wrong_voice_price_and_budget_block_before_any_submission(rig):
    _, client, seen = rig
    for voice in (None, "voice_gateway_default", "voice_owned", "../../secrets"):
        with pytest.raises(WorkError): client.quote(local.MODEL, {"text": "你好", "voice_id": voice})
    q = quote(client)
    with pytest.raises(WorkError, match="上限"): client.confirm(q, 499)
    with pytest.raises(WorkError, match="报价"): client.confirm({**q, "max_charge_micros": "1"}, 1000)
    assert seen == []


def test_lost_response_and_missing_usage_cannot_submit_twice(rig, monkeypatch):
    _, client, seen = rig
    def lost(self, *args, **kwargs):
        seen.append("lost"); raise local.requests.Timeout()
    monkeypatch.setattr(local.requests.Session, "post", lost)
    q = quote(client); intent = client.confirm(q, 1000)
    assert client.wait(intent)["status"] == "submission_unknown"
    assert client.wait(intent)["status"] == "submission_unknown" and len(seen) == 1
    def missing(self, *args, **kwargs):
        seen.append("missing")
        return SimpleNamespace(status_code=200, json=lambda: {"output": {"audio": {"url": "https://example.test/audio.wav"}}})
    monkeypatch.setattr(local.requests.Session, "post", missing)
    q2 = quote(client); intent2 = client.confirm(q2, 1000)
    assert client.wait(intent2)["status"] == "submission_unknown"
    assert client.wait(intent2)["status"] == "submission_unknown" and len(seen) == 2
    assert client._read(intent2)["audio_url"]  # Original receipt is preserved privately.


def test_crash_after_submitting_and_known_rejection_are_durable(rig, monkeypatch):
    _, client, seen = rig
    q = quote(client); intent = client.confirm(q, 1000)
    job = client._read(intent); job["status"] = "submitting"; client._write(intent, job)
    assert client.wait(intent)["status"] == "submission_unknown" and seen == []
    monkeypatch.setattr(local.requests.Session, "post", lambda *a, **kw: SimpleNamespace(status_code=403))
    q2 = quote(client); intent2 = client.confirm(q2, 1000)
    assert client.wait(intent2)["status"] == "failed"
    assert client.wait(intent2)["status"] == "failed"


def test_download_failure_resumes_original_receipt_after_restart(rig, monkeypatch):
    studio, client, seen = rig
    from backlot import studio_avatar
    original = studio_avatar.download_result
    monkeypatch.setattr(studio_avatar, "download_result", lambda *a: (_ for _ in ()).throw(OSError("network")))
    q = quote(client); intent = client.confirm(q, 1000)
    assert client.wait(intent)["status"] == "accepted"
    monkeypatch.setattr(studio_avatar, "download_result", original)
    restarted = local.SystemVoiceClient(studio, client.remote)
    assert restarted.wait(intent)["status"] == "succeeded" and len(seen) == 1


def test_credential_or_account_change_cannot_retarget_a_quoted_voice(rig):
    studio, client, seen = rig
    q = quote(client); intent = client.confirm(q, 1000)
    secrets = studio.projects_root.parent / ".env.secrets.local"
    secrets.write_text("DASHSCOPE_API_KEY=different-provider-key\n")
    with pytest.raises(WorkError, match="凭据已改变"): client.wait(intent)
    secrets.write_text("DASHSCOPE_API_KEY=fake-local-provider-key\n")
    q2 = quote(client)
    c = studio.configuration(); c["api_key"] = "changed-platform-key"; atomic_private(studio.config_path, c)
    other = local.SystemVoiceClient(studio, client.remote)
    with pytest.raises(WorkError, match="原配音记录"): other.confirm(q2, 1000)
    assert seen == []


def test_expired_quote_renews_same_snapshot_and_cannot_accept_twice(rig):
    _, client, seen = rig
    q = quote(client)
    data = client._read(q["id"]); data["quote"]["expires_at"] = (local._now() - timedelta(seconds=1)).isoformat()
    client._write(q["id"], data); q = data["quote"]
    with pytest.raises(WorkError, match="过期"): client.confirm(q, 1000)
    renewed = client.request("/quotes/" + q["id"] + "/renew", {"confirmed": True})
    assert {k:v for k,v in q.items() if k != "expires_at"} == {k:v for k,v in renewed.items() if k != "expires_at"}
    intent = client.confirm(renewed, 1000)
    with pytest.raises(WorkError, match="原任务"): client.confirm(renewed, 1000)
    assert client.confirm(renewed, 1000, intent) == intent
    accepted = client._read(q["id"])
    accepted["created_at"] = (local._now() - timedelta(days=2)).isoformat()
    client._write(q["id"], accepted)
    assert client.request("/quotes/" + q["id"] + "/renew", {"confirmed": True}) == renewed
    assert client.wait(intent)["status"] == "succeeded" and len(seen) == 1


def test_concurrent_confirmation_reserves_one_durable_intent(rig):
    from lib.bailian_speech import BailianSpeechError
    _, client, seen = rig
    q = quote(client); intent = "call_" + "a" * 32
    def confirm(_):
        try:
            return client.confirm(q, 1000, intent)
        except BailianSpeechError:
            return "busy"
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(confirm, range(4)))
    assert intent in results and set(results) <= {intent, "busy"}
    assert client.confirm(q, 1000, intent) == intent
    client.wait(intent)
    assert len(seen) == 1


@pytest.mark.parametrize("voice", ["longxiaochun_v3", "longxiaoxia_v3", "longsanshu_v3", "longanyun_v3", "longanlang_v3", "longyingxiao_v3", "longjiayi_v3"])
@pytest.mark.parametrize("avatar_status", ["succeeded", "submission_unknown"])
def test_producer_uses_local_tts_then_original_avatar_path_and_reuses_both(rig, monkeypatch, voice, avatar_status):
    from backlot import studio_avatar, studio_composition
    studio, client, seen = rig
    draft = studio.save_draft({"template_id": "avatar-safe-circle-v1", "title": "测试", "text": "你好。",
        "input": {"soundMode": "voice", "voiceId": local.MODEL, "toneId": "voice_bailian_cv3_" + voice,
                  "subtitles": False, "rate": 1.15}})
    q = quote(client, voice)
    remote_calls = []
    monkeypatch.setattr(client.remote, "upload", lambda *args: {"id": "audio-file"}, raising=False)
    def wait_for_avatar(intent, timeout=300):
        remote_calls.append(intent)
        # Simulate a healthy twenty-minute generation, without real sleeps or billing.
        return {"id": "avatar-job", "status": avatar_status if timeout >= 1200 else "running",
                "media_artifact_available": True, "upstream_id": "supplier-task",
                "funds_status": "reconciliation_pending" if avatar_status == "submission_unknown" else "settled",
                "result": {"video_url": "https://example.test/avatar.mp4"}}
    monkeypatch.setattr(client.remote, "wait", wait_for_avatar)
    def prepare(source, target, rate=1):
        assert rate == 1.15
        target.write_bytes(source.read_bytes()); return .1
    monkeypatch.setattr(studio_avatar, "prepare_audio", prepare)
    def compose(directory, *args, **kwargs):
        path = directory / "avatar-preview.mp4"; path.write_bytes(b"fake-composed-video"); return path
    monkeypatch.setattr(studio_composition, "compose_avatar", compose)
    request = {"id": "frozen-" + voice, "draft": draft, "render_id": "test-local",
        "key_identity": studio_avatar.key_identity(studio), "prepared": {"image_file": "portrait-file"},
        "quotes": {"tts": q, "avatar": {"id": "avatar-quote", "model": "haike/avatar", "max_charge_micros": "100"}},
        "max_charge_micros": 600}
    project = studio.projects_root / draft["id"]
    progress = []
    result = studio_avatar.run_avatar(project, request, client, on_progress=lambda *args: progress.append(args[0]))
    assert result["status"] == "completed"
    assert seen[0]["json"]["input"]["voice"] == voice
    assert len(remote_calls) == 1 and "原始音轨已就绪" in progress
    saved = json.loads((project / "renders/test-local/gateway-state.json").read_text())
    assert saved["stages"]["avatar"]["job"]["status"] == avatar_status
    assert studio_avatar.run_avatar(project, request, client)["status"] == "completed"
    assert len(remote_calls) == len(seen) == 1


def test_personal_bailian_voice_to_coin_avatar_and_selected_04a_resumes_without_repaying(rig, monkeypatch):
    """Real stage coordinator, TTS intents and RH segment journal; fake suppliers.

    The transcript, audio and video here are test fixtures, not a new user film.
    Template rendering is checked at its input/output contract, without a GPU.
    """
    from backlot import studio_avatar as producer, studio_avatar_app as avatar
    from backlot import studio_personal_voice as personal, studio_system_voice
    from backlot import studio_template_auto as auto, studio_motiongit as motion
    studio, client, _ = rig
    monkeypatch.delenv('RUNNINGHUB_API_KEY', raising=False)
    monkeypatch.delenv('RUNNINGHUB_COINS_API_KEY', raising=False)
    (studio.projects_root.parent/'.env.secrets.local').write_text(
        'DASHSCOPE_API_KEY=fake-local-provider-key\nRUNNINGHUB_API_KEY=forbidden-wallet-key\nRUNNINGHUB_COINS_API_KEY=fake-coins-key\n')
    atomic_private(studio.private/'haike-api/avatar.local.json', {'enabled':True,'billing_mode':'rh_coins'})
    voice_id = 'voice_local_'+'f'*32
    personal._write(studio,voice_id,{'provider_voice_id':'existing-personal-voice',
        'credential_identity':studio_system_voice.configuration(studio)['identity'],
        'target_model':local.TARGET_MODEL,'name':'已选个人音色'})
    text = '原文开头，不承诺收益。'+'按真实成本核对，不增加未经说明的承诺。'*40
    text = text[:577]+'原文结尾'
    assert len(text) == 581
    draft = studio.save_draft({'template_id':'avatar-safe-circle-v1','title':'隔离测试','text':text,
        'input':{'soundMode':'voice','voiceId':'haike/cosyvoice','toneId':voice_id,'rate':1,
                 'subtitles':True,'motion':{'style':'04-A','layout':'portrait'},
                 'templateExecution':'auto','ai':{'enabled':True,'materials':[]}}})
    q = client.quote('haike/cosyvoice', {'text':text,'voice_id':voice_id},draft['id'])
    execution = avatar.snapshot(studio)
    assert q['execution_route']==local.ROUTE and q['price']['currency']=='CNY'
    assert execution['billing_mode']=='rh_coins'
    folder = studio.projects_root/draft['id']/'renders/isolated-mixed'
    folder.mkdir(parents=True); portrait = folder/'portrait.jpg'; portrait.write_bytes(b'selected-person')
    calls=[]; task_ids=[]; first_query=True
    def post(self,url,**kw):
        nonlocal first_query
        calls.append((url,kw))
        if url.endswith('/SpeechSynthesizer'):
            assert kw['json']['input']['voice']=='existing-personal-voice'
            assert kw['json']['input']['text']==text
            assert kw['headers']['Authorization']=='Bearer fake-local-provider-key'
            value={'request_id':'one-original-tts','usage':{'characters':1064},'output':{'audio':{'url':'https://example.test/original.wav'}}}
        else:
            assert kw['headers']['Authorization']=='Bearer fake-coins-key'
            if url.endswith('/accountStatus'): value={'code':0,'data':{'apiType':'NORMAL','remainCoins':'1000','remainMoney':'999'}}
            elif url.endswith('/upload/binary'): value={'fileName':'api/'+kw['files']['file'][0]}
            elif '/run/ai-app/' in url:
                task_ids.append(str(len(task_ids)+1)); value={'taskId':task_ids[-1],'status':'RUNNING'}
                assert kw['json']['instanceType']=='plus'
            elif url.endswith('/query'):
                task=kw['json']['taskId']; assert task in task_ids
                value={'taskId':task,'status':'RUNNING' if first_query else 'SUCCESS',
                       'results':[{'url':'https://example.test/original-'+task+'.mp4','outputType':'mp4'}]}
                first_query=False
            else: pytest.fail('unexpected provider call: '+url)
        return SimpleNamespace(ok=True,status_code=200,json=lambda:value)
    monkeypatch.setattr(local.requests.Session,'post',post)
    def download(url,target):
        if url.endswith('.wav'):
            with wave.open(str(target),'wb') as w:
                w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(b'\x01\x02'*(2727*960))
        else: target.write_bytes(b'original-paid-video')
    monkeypatch.setattr(producer,'download_result',download)
    monkeypatch.setattr(avatar,'_verify_clip',lambda *a:{'video':{'width':448,'height':560}})
    monkeypatch.setattr(avatar,'_stitch',lambda cache,state,audio,target:target.write_bytes(b'joined-original-person'))
    monkeypatch.setattr(auto,'snapshot',lambda d:{'compiler':'test-only'})
    monkeypatch.setattr(motion,'precheck',lambda *a:{'paid_calls':0})
    monkeypatch.setattr('backlot.studio_asr.identity',lambda c:'test-clock')
    cues=[{'text':text,'startMs':0,'endMs':109080}]
    heard=[{**cues[0],'text':'识别结果两万元，允许改变原文。'}]
    monkeypatch.setattr('backlot.studio_audio_check.assess',lambda *a:pytest.fail('generated voice must not use content approval'))
    monkeypatch.setattr('backlot.studio_asr.transcribe',lambda *a:{'test':True})
    monkeypatch.setattr(producer,'captions',lambda *a:heard)
    monkeypatch.setattr(producer,'clock_captions',lambda *a:heard)
    monkeypatch.setattr('backlot.studio_presentation.verify_native',lambda actual,expected,**kw:None)
    monkeypatch.setattr('backlot.studio_storyboard.produce',lambda *a:pytest.fail('no paid storyboard'))
    def preflight(s,d,f,a,c,board,caption_cues,**kw):
        assert d['input']['motion']=={'style':'04-A','layout':'portrait'}
        assert d['text']==text and c==cues and caption_cues==cues
        assert board['workflow']==auto.VERSION
        return {'mode':'motiongit','notice':'','segments':['selected-04a-plan']}
    monkeypatch.setattr('backlot.studio_preflight.prepare',preflight)
    rendered=[]
    def compose(s,d,f,v,a,c,segments,**kw):
        from backlot.studio_presentation import selected
        assert v.read_bytes()==b'joined-original-person' and c==cues
        assert segments==['selected-04a-plan'] and d['input']['toneId']==voice_id
        rendered.append(d['input']['motion'])
        return {'status':'completed','result':{'presentation':{**selected(d),'variant':'motion-kit'}}}
    monkeypatch.setattr(motion,'compose',compose)
    request={'id':'isolated-mixed','draft':draft,'render_id':'isolated-mixed',
        'key_identity':producer.key_identity(studio),'workflow_version':4,'billing_policy':'actual_usage',
        'avatar_execution':execution,'automatic_template_execution':{'compiler':'test-only'},
        'presentation':{'id':'adu:04-A:portrait'},'template_ref':{'runtime':'motiongit'},
        'quotes':{'tts':q},'prepared':{'portrait_path':str(portrait)},
        'asr':{'provider':'local-whisper','identity':'test-clock'}}
    project=studio.projects_root/draft['id']
    first=producer.run_avatar(project,request,client)
    assert first['error']['code']=='provider_pending' and len(task_ids)==1
    assert producer.run_avatar(project,request,client)['status']=='completed'
    assert producer.run_avatar(project,request,client)['status']=='completed'
    assert len(task_ids)==3 and len(rendered)==2
    assert producer.run_avatar(project,{**request,'local_recomposition':True},client)['status']=='completed'
    assert len(task_ids)==3 and len(rendered)==3
    assert sum(url.endswith('/SpeechSynthesizer') for url,_ in calls)==1
    assert all('/enrollment' not in url and '/create' not in url for url,_ in calls)
    state=json.loads((folder/'gateway-state.json').read_text())
    assert state['stages']['tts']['job']['billing_source']=='local-provider'
    assert state['stages']['avatar']['execution']['billing_mode']=='rh_coins'
    assert state['stages']['avatar']['job']['billing_policy']=='actual_usage'
    assert state['stages']['tts']['quote']==q
