import base64
import json
import hashlib
import io
from types import SimpleNamespace

import pytest

from backlot.studio import Studio, atomic_private
from backlot.studio_storyboard import TrialRelay, status
from backlot.work_catalog import WorkError


def test_gateway_resume_freezes_intent_and_uploads_owned_frames_once(tmp_path, monkeypatch):
    studio = Studio(tmp_path / "projects")
    atomic_private(studio.config_path, {"base_url": "https://haike.test/v2", "api_key": "test-customer-only"})
    events = []
    class Fake:
        def upload(self, path, kind): events.append("upload"); return {"id": "file-owned"}
        def quote(self, model, inputs, ref):
            events.append("quote")
            assert model == "haike/text" and inputs["messages"][0]["content"][0] == {"type": "image_file", "file_id": "file-owned"}
            return {"id": "quote-1", "max_charge_micros": "0"}
        def confirm(self, quote, maximum, intent): events.append(("confirm", intent)); assert maximum == "0"
        def wait(self, intent):
            events.append(("wait", intent))
            if sum(isinstance(e, tuple) and e[0] == "wait" for e in events) == 1: raise TimeoutError()
            return {"id": "gj-one", "status": "succeeded", "charged_micros": "0",
                    "usage": {"input_tokens": 52, "output_tokens": 12}, "result": {"choices": [{"message": {"content": "测试"}}]}}
    monkeypatch.setattr(studio, "client", lambda: Fake())
    relay = TrialRelay(studio, tmp_path / "requests")
    payload = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b"test-image").decode()}}]}]}
    with pytest.raises(WorkError): relay.call("storyboard", payload)
    result = relay.call("storyboard", payload)
    assert result["usage"] == {"prompt_tokens": 52, "completion_tokens": 12}
    assert relay.call("storyboard", payload) == result
    assert events.count("upload") == events.count("quote") == 1
    assert len({e[1] for e in events if isinstance(e, tuple)}) == 1
    assert status(studio)["chat_route"] == "gateway"
    receipt = json.loads(next(relay.folder.glob("*.json")).read_text())
    assert receipt["procurement_amount"] is None and "test-customer-only" not in json.dumps(receipt)


def test_gateway_trial_never_confirms_a_priced_quote_or_changes_original_account(tmp_path, monkeypatch):
    studio = Studio(tmp_path / "projects")
    atomic_private(studio.config_path, {"base_url": "https://haike.test/v2", "api_key": "one-customer"})
    class Priced:
        def quote(self, *args): return {"id": "q", "max_charge_micros": "1"}
        def confirm(self, *args): raise AssertionError("Cannot charge sponsored authorization")
    monkeypatch.setattr(studio, "client", lambda: Priced())
    relay = TrialRelay(studio, tmp_path / "requests")
    payload = {"messages": [{"role": "user", "content": "测试"}]}
    with pytest.raises(WorkError, match="预算"): relay.call("storyboard", payload)
    atomic_private(studio.config_path, {"base_url": "https://haike.test/v2", "api_key": "another-customer"})
    with pytest.raises(WorkError, match="变化"): relay.call("storyboard", payload)


def test_quote_rejection_retains_specific_diagnosis_without_confirm(tmp_path, monkeypatch):
    studio = Studio(tmp_path / 'projects')
    class Rejection(ValueError): status = 422
    class Fake:
        def quote(self, *args): raise Rejection('对话文本过长')
        def confirm(self, *args): pytest.fail('Rejected quote must never submit')
    monkeypatch.setattr(studio, 'client', lambda: Fake())
    with pytest.raises(WorkError, match='网关.*文本') as error:
        TrialRelay(studio, tmp_path / 'calls').call('native-semantic-plan-v1', {
            'model': 'gpt-6-luna', 'messages': [{'role':'user','content':'完整模板'}]})
    assert error.value.code == 'ai_input_rejected'


def test_local_chat_migrates_only_unsubmitted_gateway_preflight_and_caches(tmp_path, monkeypatch):
    studio = Studio(tmp_path / 'projects')
    atomic_private(studio.private / 'studio-ai/relay.json', {
        'chat_route':'direct','base_url':'https://local-relay.example/v1','api_key':'test-local-private'})
    relay = TrialRelay(studio, tmp_path / 'calls')
    payload = {'model':'gpt-6-luna','messages':[{'role':'user','content':'模板' * 40000}]}
    path = relay.folder / (hashlib.sha256(b'native').hexdigest() + '.json')
    atomic_private(path, {'status':'prepared','gateway':True,'intent':'call_'+'1'*32,
        'fingerprint':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),
        'identity':'old-gateway','images':{},'stage':'native'})
    calls=[]
    def open_request(request, **kwargs):
        calls.append(json.loads(request.data))
        return io.BytesIO(json.dumps({'choices':[{'message':{'content':'完整结果'}}]}).encode())
    monkeypatch.setattr('urllib.request.build_opener',lambda *_:SimpleNamespace(open=open_request))
    monkeypatch.setattr(studio,'client',lambda:pytest.fail('No gateway submit on local preflight migration'))
    assert relay.call('native',payload)['choices'][0]['message']['content']=='完整结果'
    assert relay.call('native',payload)['choices'][0]['message']['content']=='完整结果'
    saved=json.loads(path.read_text())
    assert len(calls)==1 and calls[0]==payload
    assert saved['status']=='succeeded' and saved['gateway'] is False
    assert saved['route_history'][0]['status']=='prepared'
    assert 'test-local-private' not in path.read_text()


def test_accepted_gateway_request_keeps_original_route_when_default_changes(tmp_path, monkeypatch):
    studio=Studio(tmp_path/'projects')
    atomic_private(studio.config_path,{'base_url':'https://gateway.example/v2','api_key':'test-key'})
    atomic_private(studio.private/'studio-ai/relay.json',{'chat_route':'direct','base_url':'https://relay.example/v1','api_key':'test-local'})
    relay=TrialRelay(studio,tmp_path/'calls');payload={'model':'gpt-6-luna','messages':[{'role':'user','content':'原文'}]}
    from backlot.studio_chat_gateway import identity
    path=relay.folder/(hashlib.sha256(b'native').hexdigest()+'.json')
    atomic_private(path,{'gateway':True,'status':'submitting','intent':'call_'+'2'*32,'identity':identity(studio),
        'fingerprint':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),'quote':{'id':'old-quote','max_charge_micros':'0'}})
    calls=[]
    class Fake:
        def confirm(self,quote,maximum,intent):calls.append(intent)
        def wait(self,intent):return {'id':'original-job','status':'succeeded','charged_micros':'0','result':{'choices':[{'message':{'content':'原结果'}}]}}
    monkeypatch.setattr(studio,'client',lambda:Fake())
    monkeypatch.setattr('urllib.request.build_opener',lambda *_:pytest.fail('Accepted request must not move'))
    assert relay.call('native',payload)['id']=='original-job'
    assert calls==['call_'+'2'*32] and json.loads(path.read_text())['gateway'] is True


def test_unknown_direct_request_is_not_replayed_via_changed_default(tmp_path, monkeypatch):
    studio=Studio(tmp_path/'projects');config=studio.private/'studio-ai/relay.json'
    atomic_private(config,{'chat_route':'direct','base_url':'https://relay.example/v1','api_key':'test-local'})
    calls=[]
    def fail(*a,**k):calls.append('submit');raise TimeoutError()
    monkeypatch.setattr('urllib.request.build_opener',lambda *_:SimpleNamespace(open=fail))
    monkeypatch.setattr(studio,'client',lambda:pytest.fail('Unknown direct request must not change route'))
    relay=TrialRelay(studio,tmp_path/'calls');payload={'model':'gpt-6-luna','messages':[{'role':'user','content':'原文'}]}
    with pytest.raises(WorkError):relay.call('native',payload)
    atomic_private(config,{'chat_route':'gateway'})
    with pytest.raises(WorkError,match='未重复'):relay.call('native',payload)
    assert calls==['submit']
