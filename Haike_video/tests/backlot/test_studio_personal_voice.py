"""Local enrollment through real studio boundaries and an isolated supplier."""
import io
import json
import math
import struct
import wave
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from backlot.studio import Studio, atomic_private
from backlot import studio_personal_voice as personal, studio_system_voice as system, studio_voices
from backlot.work_catalog import WorkError


def wav(seconds=8, silent=False):
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        stream.writeframes(b"".join(struct.pack("<h", 0 if silent else int(8000 * math.sin(i * .04))) for i in range(seconds * 24000)))
    return output.getvalue()


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_WORKSPACE_ID", raising=False)
    studio = Studio(tmp_path / "projects")
    atomic_private(studio.config_path, {"base_url": "http://127.0.0.1:17894/v2", "api_key": "fake-owner-one"})
    (tmp_path / ".env.secrets.local").write_text('DASHSCOPE_API_KEY="fake-supplier-key"\n')
    atomic_private(studio.private / "haike-api/system-voices.local.json", {"enabled": True})
    class Remote:
        state_dir = studio.private / "remote"
        def request(self, path, *args, **kwargs):
            if path == "/capabilities": return {"items": []}
            error = ValueError("missing"); error.status = 404; raise error
        def quote(self, *args): raise AssertionError("personal TTS must stay local")
        def resume(self, *args): raise AssertionError("personal intent must stay local")
    client = system.SystemVoiceClient(studio, Remote())
    monkeypatch.setattr(studio, "client", lambda: client)
    seen, voices = [], []
    def get(self, url, **kwargs):
        seen.append(("policy", kwargs))
        return SimpleNamespace(status_code=200, json=lambda: {"data": {"upload_host": "https://dashscope-file-test.oss-cn-beijing.aliyuncs.com",
            "upload_dir": "dashscope-instant/test", "x_oss_object_acl": "private", "oss_access_key_id": "fake-ticket", "signature": "fake-signature", "policy": "fake-policy"}})
    def post(self, url, **kwargs):
        if "files" in kwargs:
            assert "headers" not in kwargs and kwargs["data"]["x-oss-object-acl"] == "private"
            seen.append(("upload", {}))
            return SimpleNamespace(status_code=200)
        data = kwargs["json"]
        if data["model"] == "voice-enrollment":
            value = data["input"]; action = value["action"]; seen.append((action, value))
            if action == "create_voice":
                assert kwargs["headers"]["X-DashScope-OssResourceResolve"] == "enable"
                assert value["url"].startswith("oss://")
                voice = value["target_model"] + "-" + value["prefix"] + "-test"
                voices.append({"voice_id": voice, "target_model": value["target_model"]})
                output = {"voice_id": voice}
            elif action == "list_voice": output = {"voice_list": voices}
            else: output = {"status": "OK", "target_model": system.TARGET_MODEL}
            return SimpleNamespace(status_code=200, json=lambda: {"request_id": "fake-create", "output": output})
        seen.append(("tts", data))
        return SimpleNamespace(status_code=200, json=lambda: {"request_id": "fake-tts", "usage": {"characters": 10}, "output": {"audio": {"url": "https://example.test/tts.wav"}}})
    monkeypatch.setattr(personal.requests.Session, "get", get)
    monkeypatch.setattr(personal.requests.Session, "post", post)
    monkeypatch.setattr("backlot.studio_avatar.download_result", lambda url, target: target.write_bytes(wav()))
    # Exercise the HTTP-facing confirmation without a nondeterministic background worker.
    monkeypatch.setattr(personal, "start", lambda s, i: personal._public(personal._read(s, i)))
    return studio, client, seen


def prepare(studio):
    sample = studio_voices.upload_sample(studio, "我的录音.wav", wav())
    return studio_voices.quote_clone(studio, {"name": "我的声音", "sample_id": sample["id"], "consent": True})


def complete(studio, operation):
    studio_voices.confirm(studio, operation["id"], True)
    return studio_voices.query(studio, operation["id"])


def test_old_gateway_now_offers_clone_and_uploaded_voice_can_make_tts(rig):
    studio, client, seen = rig
    assert studio_voices.catalogue(studio)["clone_ready"]
    operation = prepare(studio)
    assert operation["quote"]["max_charge_micros"] == "0"
    job = complete(studio, operation)
    assert job["job"]["status"] == "succeeded"
    voice = next(v for v in studio_voices.catalogue(studio)["items"] if v["id"] == job["voice_id"])
    assert voice["scope"] == "personal" and voice["production_ready"]
    quote = client.quote(voice["model"], {"voice_id": voice["id"], "text": "你好，海客。"})
    assert quote["model"] == "haike/cosyvoice" and int(quote["max_charge_micros"]) > 0
    intent = client.confirm(quote, int(quote["max_charge_micros"]))
    assert client.resume(intent)["status"] == "succeeded"
    assert seen[-1][1]["model"] == system.TARGET_MODEL
    assert seen[-1][1]["input"]["voice"] == personal.resolve(studio, voice["id"])["provider_voice_id"]
    assert "fake-supplier-key" not in json.dumps([operation, voice, job])


def test_repeated_upload_and_confirm_never_create_twice(rig):
    studio, _, seen = rig
    first = prepare(studio)
    complete(studio, first)
    second = prepare(studio)
    assert second["quote"] == first["quote"]
    assert complete(studio, second)["voice_id"] == studio_voices.query(studio, first["id"])["voice_id"]
    assert sum(k == "create_voice" for k, _ in seen) == 1


def test_lost_create_response_recovers_unique_prefix_without_resubmitting(rig, monkeypatch):
    studio, _, seen = rig
    original = personal._enrollment
    def lost(config, inputs, reference=False):
        result = original(config, inputs, reference)
        if inputs["action"] == "create_voice": raise personal.requests.Timeout()
        return result
    monkeypatch.setattr(personal, "_enrollment", lost)
    job = complete(studio, prepare(studio))
    assert job["job"]["status"] == "succeeded"
    assert sum(k == "create_voice" for k, _ in seen) == 1
    assert sum(k == "list_voice" for k, _ in seen) == 1


def test_unknown_receipt_or_wrong_model_cannot_register_or_recreate(rig, monkeypatch):
    studio, _, seen = rig
    original = personal._enrollment
    def uncertain(config, inputs, reference=False):
        if inputs["action"] == "create_voice":
            seen.append(("create_voice", {})); raise personal.requests.Timeout()
        if inputs["action"] == "list_voice":
            return SimpleNamespace(status_code=200, json=lambda: {"output": {"voice_list": [{"voice_id": "wrong"}]}})
        return original(config, inputs, reference)
    monkeypatch.setattr(personal, "_enrollment", uncertain)
    operation = prepare(studio)
    assert complete(studio, operation)["job"]["status"] == "submission_unknown"
    assert studio_voices.query(studio, operation["id"])["job"]["retryable"]
    assert sum(k == "create_voice" for k, _ in seen) == 1
    assert not [v for v in studio_voices.catalogue(studio)["items"] if v["scope"] == "personal"]


def test_reference_validation_and_consent_before_network(rig):
    studio, _, seen = rig
    for name, data in [("bad.txt", wav()), ("bad.wav", b"invalid"), ("short.wav", wav(2)), ("silent.wav", wav(8, True))]:
        with pytest.raises(WorkError): studio_voices.upload_sample(studio, name, data)
    with pytest.raises(WorkError): studio_voices.quote_clone(studio, {"consent": False})
    assert not seen


def test_account_isolation_rename_and_preview_cache(rig):
    studio, client, seen = rig
    operation = prepare(studio); result = complete(studio, operation); identity = result["voice_id"]
    studio_voices.rename(studio, identity, "我的品牌声音")
    preview = studio_voices.quote_preview(studio, identity)
    same = studio_voices.quote_preview(studio, identity)
    assert preview["operation"]["quote"] == same["operation"]["quote"]
    studio_voices.confirm(studio, preview["operation"]["id"], True)
    assert studio_voices.quote_preview(studio, identity)["cached"]
    assert studio_voices.sample(studio, identity).read_bytes().startswith(b"RIFF")
    assert sum(k == "tts" for k, _ in seen) == 1
    assert studio_voices.confirm(studio, same["operation"]["id"], True)["job"]["status"] == "succeeded"
    assert sum(k == "tts" for k, _ in seen) == 1
    atomic_private(studio.config_path, {"base_url": "http://127.0.0.1:17894/v2", "api_key": "fake-owner-two"})
    assert studio_voices.operations(studio) == []
    for action in (lambda: personal.resolve(studio, identity), lambda: studio_voices.sample(studio, identity), lambda: studio_voices.query(studio, operation["id"])):
        with pytest.raises(WorkError): action()


def test_frozen_credentials_and_rejected_clone(rig, monkeypatch):
    studio, _, seen = rig
    operation = prepare(studio); studio_voices.confirm(studio, operation["id"], True)
    (studio.projects_root.parent / ".env.secrets.local").write_text('DASHSCOPE_API_KEY="another-fake-key"\n')
    with pytest.raises(WorkError): studio_voices.query(studio, operation["id"])
    assert not seen


def test_durable_parallel_confirmation_reuses_intent(rig):
    studio, _, seen = rig
    operation = prepare(studio)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: studio_voices.confirm(studio, operation["id"], True), range(4)))
    assert len({v["job"]["id"] for v in jobs}) == 1
    studio_voices.query(studio, operation["id"])
    assert sum(k == "create_voice" for k, _ in seen) == 1


def test_http_upload_clone_preview_and_private_audio(rig, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backlot.studio_api import router
    studio, _, seen = rig
    monkeypatch.setattr("backlot.studio_voice_samples.prefetch", lambda *args: None)
    app = FastAPI(); app.state.studio = studio; app.include_router(router)
    with TestClient(app) as http:
        assert http.get("/api/studio/voices").json()["clone_ready"]
        upload = http.post("/api/studio/voices/samples?filename=own.wav", content=wav(), headers={"Content-Type": "application/octet-stream"})
        assert upload.status_code == 200
        request = {"name": "我的声音", "sample_id": upload.json()["id"], "consent": True}
        assert http.post("/api/studio/voices/clone-quotes", json=request, headers={"Origin": "https://other.test"}).status_code == 403
        operation = http.post("/api/studio/voices/clone-quotes", json=request).json()
        response = http.post("/api/studio/voice-operations/" + operation["id"] + "/confirm", json={"confirmed": True})
        assert response.status_code == 200 and response.json()["job"]["status"] == "queued"
        result = http.get("/api/studio/voice-operations").json()["items"][0]
        assert result["job"]["status"] == "succeeded"
        identity = result["voice_id"]
        preview = http.post("/api/studio/voices/preview-quotes", json={"voice_id": identity}).json()
        assert int(preview["operation"]["quote"]["max_charge_micros"]) > 0
        http.post("/api/studio/voice-operations/" + preview["operation"]["id"] + "/confirm", json={"confirmed": True}).raise_for_status()
        audio = http.get("/api/studio/voices/" + identity + "/sample")
        assert audio.status_code == 200 and audio.content.startswith(b"RIFF")
        assert audio.headers["cache-control"] == "private, no-store"
        assert sum(k == "create_voice" for k, _ in seen) == 1 and sum(k == "tts" for k, _ in seen) == 1


def test_upload_failure_and_pending_query_recover_without_second_create(rig, monkeypatch):
    studio, _, seen = rig
    operation = prepare(studio)
    original_upload, original_enrollment = personal._upload_reference, personal._enrollment
    monkeypatch.setattr(personal, "_upload_reference", lambda *args: (_ for _ in ()).throw(personal.requests.Timeout()))
    assert complete(studio, operation)["job"]["status"] == "queued"
    assert not seen
    monkeypatch.setattr(personal, "_upload_reference", original_upload)
    def pending(config, inputs, reference=False):
        if inputs["action"] == "query_voice":
            return SimpleNamespace(status_code=200, json=lambda: {"output": {"status": "DEPLOYING"}})
        return original_enrollment(config, inputs, reference)
    monkeypatch.setattr(personal, "_enrollment", pending)
    assert studio_voices.query(studio, operation["id"])["job"]["status"] == "running"
    monkeypatch.setattr(personal, "_enrollment", original_enrollment)
    assert studio_voices.query(studio, operation["id"])["job"]["status"] == "succeeded"
    assert sum(k == "create_voice" for k, _ in seen) == 1


def test_rejection_or_wrong_bound_model_never_enables_voice(rig, monkeypatch):
    studio, _, _ = rig
    operation = prepare(studio)
    original = personal._enrollment
    def wrong(config, inputs, reference=False):
        if inputs["action"] == "query_voice":
            return SimpleNamespace(status_code=200, json=lambda: {"output": {"status": "OK", "target_model": "other-model"}})
        return original(config, inputs, reference)
    monkeypatch.setattr(personal, "_enrollment", wrong)
    assert complete(studio, operation)["job"]["status"] == "running"
    assert personal.catalogue(studio) == []
    def reject(config, inputs, reference=False):
        return SimpleNamespace(status_code=200, json=lambda: {"output": {"status": "UNDEPLOYED"}})
    monkeypatch.setattr(personal, "_enrollment", reject)
    assert studio_voices.query(studio, operation["id"])["job"]["status"] == "failed"
    assert personal.catalogue(studio) == []


def test_running_job_is_bound_to_original_account_even_when_settings_change(rig):
    studio, _, seen = rig
    operation = prepare(studio)
    intent = personal.confirm(studio, operation["quote"])
    bound = personal.bind(studio)
    atomic_private(studio.config_path, {"base_url": "http://127.0.0.1:17894/v2", "api_key": "fake-owner-two"})
    result = personal.resume(bound, intent)
    assert result["status"] == "succeeded"
    assert personal.catalogue(studio) == []
    assert len(personal.catalogue(bound)) == 1
    assert sum(k == "create_voice" for k, _ in seen) == 1


def test_interrupted_preview_confirmation_recovers_already_saved_sdk_intent(rig, monkeypatch):
    studio, client, seen = rig
    voice = complete(studio, prepare(studio))["voice_id"]
    operation = studio_voices.quote_preview(studio, voice)["operation"]
    original = client.confirm
    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("process interrupted after SDK saved intent")
    monkeypatch.setattr(client, "confirm", interrupted)
    with pytest.raises(OSError): studio_voices.confirm(studio, operation["id"], True)
    monkeypatch.setattr(client, "confirm", original)
    assert studio_voices.confirm(studio, operation["id"], True)["job"]["status"] == "succeeded"
    assert sum(k == "tts" for k, _ in seen) == 1


def test_definite_rejection_retries_only_on_fresh_user_action(rig, monkeypatch):
    studio, _, seen = rig
    original = personal._enrollment
    def rejected(config, inputs, reference=False):
        seen.append(("rejected", {}))
        return SimpleNamespace(status_code=429)
    monkeypatch.setattr(personal, "_enrollment", rejected)
    operation = prepare(studio)
    assert complete(studio, operation)["job"]["status"] == "failed"
    assert studio_voices.query(studio, operation["id"])["job"]["status"] == "failed"
    assert sum(k == "rejected" for k, _ in seen) == 1
    monkeypatch.setattr(personal, "_enrollment", original)
    fresh = prepare(studio)
    assert complete(studio, fresh)["job"]["status"] == "succeeded"
    assert fresh["quote"]["id"] == operation["quote"]["id"]
