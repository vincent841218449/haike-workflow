"""Durable voice intents and account-scoped cached media, without external calls."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from backlot import studio_voices
from backlot.studio import Studio, atomic_private
from backlot.work_catalog import WorkError


@pytest.fixture
def rig(tmp_path, monkeypatch):
    studio = Studio(tmp_path / "projects")
    atomic_private(studio.config_path, {"base_url": "http://127.0.0.1:17894/v2", "api_key": "test-voice-account-one"})
    class Client:
        def __init__(self): self.intents = []; self.downloads = 0; self.lost = True
        def quote(self, *args): return {"id": "clone-quote", "max_charge_micros": "0"}
        def confirm(self, q, maximum):
            self.intents.append({"id": "intent-one"}); return self.intents[-1]
        def resume(self, intent):
            assert intent["id"] == "intent-one"
            if self.lost: self.lost = False; raise OSError("response lost")
            return {"id": "clone-job", "status": "succeeded", "result": {"voice_id": "voice_owned"}}
        def request(self, path, data=None):
            return {"items": [{"id": "voice_owned", "sample_status": "succeeded", "sample_url": "/v2/voices/voice_owned/sample"}]}
        def media(self, path): self.downloads += 1; return b"RIFFcached-audio"
    client = Client(); monkeypatch.setattr(studio, "client", lambda: client)
    return studio, client


def test_lost_confirmation_and_parallel_retries_keep_original_intent(rig):
    studio, client = rig
    operation = studio_voices.quote_clone(studio, {"name": "我的口播", "sample_id": "file-one", "consent": True})
    with pytest.raises(WorkError, match="原任务"):
        studio_voices.confirm(studio, operation["id"], True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: studio_voices.confirm(studio, operation["id"], True), range(4)))
    assert len(client.intents) == 1
    assert all(j["job"]["id"] == "clone-job" and j["voice_id"] == "voice_owned" for j in jobs)
    assert "test-voice-account" not in json.dumps(studio_voices.operations(studio))


def test_changed_account_cannot_confirm_old_quote_or_read_old_cache(rig, monkeypatch):
    studio, client = rig
    operation = studio_voices.quote_clone(studio, {"name": "我的口播", "consent": True})
    first = studio_voices.sample(studio, "voice_owned")
    assert studio_voices.sample(studio, "voice_owned") == first and client.downloads == 1
    atomic_private(studio.config_path, {"base_url": "http://127.0.0.1:17894/v2", "api_key": "test-voice-account-two"})
    assert studio_voices.operations(studio) == []
    with pytest.raises(WorkError): studio_voices.confirm(studio, operation["id"], True)
    monkeypatch.setattr(client, "request", lambda *args: {"items": []})
    with pytest.raises(WorkError): studio_voices.sample(studio, "voice_owned")
    assert client.downloads == 1


def test_library_rejects_path_like_voice_ids_before_local_media_access(rig, monkeypatch):
    studio, client = rig
    monkeypatch.setattr(client, "request", lambda *args: {"items": [{"id": "../../private"}]})
    with pytest.raises(WorkError, match="无效"):
        studio_voices.sample(studio, "../../private")
    assert client.downloads == 0


def test_old_gateway_offers_explicit_default_without_claiming_cloning_or_audition(rig, monkeypatch):
    studio, client = rig
    class MissingLibrary(ValueError): status = 404
    def request(path):
        if path == "/voices": raise MissingLibrary("not found")
        assert path == "/capabilities"
        return {"items": [{"model": "haike/cosyvoice", "status": "available"}]}
    monkeypatch.setattr(client, "request", request)
    value = studio_voices.catalogue(studio)
    official = [v for v in value['items'] if v.get('sample_kind') == 'official']
    assert len(official) == 7 and value['default_voice_id'] == 'voice_bailian_cv3_longxiaochun_v3'
    assert all(v['production_ready'] is False for v in official)
    voice = next(v for v in value['items'] if v['id'] == 'voice_gateway_default')
    assert voice['scope'] == 'legacy'
    assert not value["clone_ready"] and not voice["preview_ready"]
    from backlot.studio_avatar import tts_input
    assert tts_input({"text": "原文", "input": {"toneId": voice["id"]}}) == {"text": "原文"}
    assert tts_input({"text": "原文", "input": {"toneId": "voice_owned"}})["voice_id"] == "voice_owned"
    with pytest.raises(WorkError, match="单独试听"):
        studio_voices.quote_preview(studio, voice["id"])
    assert client.intents == []


def test_system_model_uses_exact_preset_and_requires_its_own_capability(rig, monkeypatch):
    studio, client = rig
    monkeypatch.setattr(client,'request',lambda path:{'items':[{'model':'haike/cosyvoice-system','status':'available'}]} if path=='/capabilities' else {'items':[]})
    value=studio_voices.catalogue(studio)
    tone=next(v for v in value['items'] if v['id']==value['default_voice_id'])
    assert tone['production_ready'] and tone['sample_kind']=='official'
    from backlot.studio_avatar import validate_voice, tts_input
    selected={'soundMode':'voice','voiceId':tone['model'],'toneId':tone['id']}
    validate_voice(selected)
    assert tts_input({'text':'原文','input':selected})=={'text':'原文','voice_id':tone['id']}
    with pytest.raises(WorkError,match='官方系统音色'):
        validate_voice({**selected,'toneId':'voice_gateway_default'})
    assert client.intents==[]


def test_curated_catalogue_hides_extra_gateway_presets_but_preserves_personal_voices(rig, monkeypatch):
    studio, client = rig
    def request(path):
        if path == '/capabilities':
            return {'items': [{'model': 'haike/cosyvoice-system', 'status': 'available'}]}
        return {'items': [
            {'id': 'voice_bailian_cv3_longhouge_v3', 'scope': 'system', 'model': 'haike/cosyvoice-system', 'sample_kind': 'official'},
            {'id': 'voice_owned', 'scope': 'personal', 'model': 'haike/cosyvoice'},
        ]}
    monkeypatch.setattr(client, 'request', request)
    value = studio_voices.catalogue(studio)
    assert len([v for v in value['items'] if v.get('sample_kind') == 'official']) == 7
    assert 'voice_bailian_cv3_longhouge_v3' not in {v['id'] for v in value['items']}
    assert any(v['id'] == 'voice_owned' for v in value['items'])


def test_unavailable_gateway_does_not_silently_replace_a_personal_voice(rig, monkeypatch):
    studio, client = rig
    class Unauthorized(ValueError): status = 401
    def request(path): raise Unauthorized("private account")
    monkeypatch.setattr(client, "request", request)
    with pytest.raises(WorkError, match="音色库暂不可用"):
        studio_voices.catalogue(studio)
