"""Local enrollment through real studio boundaries and an isolated supplier."""
import io
import json
import math
import struct
import subprocess
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
        second = b"".join(struct.pack("<h", 0 if silent else int(8000 * math.sin(i * .04))) for i in range(24000))
        stream.writeframes(second * seconds)
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
            seen.append(("upload", {"bytes": len(kwargs["files"]["file"][1].read())}))
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


def test_166_second_recording_is_prepared_locally_without_cloud_submission(rig):
    studio, _, seen = rig
    sample = studio_voices.upload_sample(studio, "长录音.wav", wav(166))
    assert sample["source_duration"] == 166 and sample["duration"] == 20 and sample["trimmed"]
    assert sample["reference_url"].startswith("/api/studio/voices/references/samplelocal-")
    assert not seen  # Only the prepared excerpt is uploaded after voice consent and confirmation.
    operation = studio_voices.quote_clone(studio, {"name": "长录音", "sample_id": sample["id"], "consent": True})
    assert complete(studio, operation)["job"]["status"] == "succeeded"
    assert next(v["bytes"] for action, v in seen if action == "upload") < 1_000_000


def test_long_m4a_uses_twenty_second_private_reference(rig, tmp_path):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    studio, _, seen = rig
    source, compressed = tmp_path / "long.wav", tmp_path / "long.m4a"
    source.write_bytes(wav(166))
    ffmpeg, _ = resolve_ffmpeg_pair()
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(source), "-c:a", "aac", str(compressed)], check=True, capture_output=True, timeout=60)
    sample = studio_voices.upload_sample(studio, "用户长录音.m4a", compressed.read_bytes())
    assert sample["source_duration"] == pytest.approx(166, abs=.1) and sample["duration"] == 20
    with wave.open(str(personal.reference(studio, sample["id"]))) as audio:
        assert audio.getnframes() / audio.getframerate() == 20
    assert not seen


def test_excerpt_chooses_non_silent_section_instead_of_first_twenty_seconds(rig):
    studio, _, seen = rig
    output = io.BytesIO()
    with wave.open(io.BytesIO(wav(20))) as voice:
        speech = voice.readframes(voice.getnframes())
    with wave.open(output, "wb") as audio:
        audio.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * (90 * 24000) + speech + b"\0\0" * (56 * 24000))
    sample = studio_voices.upload_sample(studio, "带停顿.wav", output.getvalue())
    assert 89.8 <= sample["excerpt_start"] <= 90.2
    assert sample["excerpt_end"] - sample["excerpt_start"] == 20
    assert not seen


def test_length_and_silence_errors_are_distinct_and_longer_than_ten_minutes_is_bounded(rig, tmp_path):
    from backlot.studio_voice_reference import prepare as prepare_reference
    studio, _, _ = rig
    with pytest.raises(WorkError, match="只有2.0秒"):
        studio_voices.upload_sample(studio, "too-short.wav", wav(2))
    with pytest.raises(WorkError, match="接近静音"):
        studio_voices.upload_sample(studio, "silent.wav", wav(8, True))
    source = tmp_path / "too-long.wav"
    source.write_bytes(wav(601))
    with pytest.raises(WorkError, match="超过10分钟"):
        prepare_reference(source, tmp_path / "excerpt.wav")


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


def test_preview_survives_restart_and_plays_offline_without_new_quote_or_charge(rig, monkeypatch):
    studio, client, seen = rig
    identity = complete(studio, prepare(studio))["voice_id"]
    operation = studio_voices.quote_preview(studio, identity)["operation"]
    studio_voices.confirm(studio, operation["id"], True)
    original = studio_voices.sample(studio, identity).read_bytes()
    restarted = Studio(studio.projects_root)
    client = system.SystemVoiceClient(restarted, client.remote)
    monkeypatch.setattr(restarted, "client", lambda: client)
    monkeypatch.setattr("backlot.studio_avatar.download_result", lambda *a: pytest.fail("cached playback must stay offline"))
    # Playback depends on the original account, not live supplier credentials.
    (studio.projects_root.parent / ".env.secrets.local").write_text("")
    for _ in range(3):
        assert studio_voices.quote_preview(restarted, identity) == {"cached": True}
        path = studio_voices.sample(restarted, identity)
        assert path.read_bytes() == original and path.stat().st_mode & 0o777 == 0o600
        assert studio_voices.catalogue(restarted)["items"][-1]["sample_status"] == "succeeded"
    assert sum(k == "tts" for k, _ in seen) == 1
    with restarted.db() as db:
        assert db.execute("SELECT COUNT(*) FROM studio_voice_operations WHERE json_extract(data,'$.kind')='sample'").fetchone()[0] == 1


@pytest.mark.parametrize("damage", ["missing", "invalid", "different-wav"])
def test_preview_repairs_original_result_without_resynthesizing(rig, monkeypatch, damage):
    studio, client, seen = rig
    identity = complete(studio, prepare(studio))["voice_id"]
    operation = studio_voices.quote_preview(studio, identity)["operation"]
    confirmed = studio_voices.confirm(studio, operation["id"], True)
    path = studio_voices.sample(studio, identity)
    original = path.read_bytes()
    if damage == "missing": path.unlink()
    else: path.write_bytes(b"invalid" if damage == "invalid" else wav(3))
    downloads = []
    def restore(url, target):
        downloads.append(url); target.write_bytes(original)
    monkeypatch.setattr("backlot.studio_avatar.download_result", restore)
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(value == original for value in pool.map(lambda _: studio_voices.sample(studio, identity).read_bytes(), range(3)))
    assert downloads == ["https://example.test/tts.wav"]
    assert studio_voices.query(studio, confirmed["id"])["job"]["status"] == "succeeded"
    assert studio_voices.quote_preview(studio, identity) == {"cached": True}
    assert sum(k == "tts" for k, _ in seen) == 1


@pytest.mark.parametrize("result", ["expired", "changed-audio", "invalid-audio"])
def test_unavailable_original_cannot_trigger_another_paid_preview(rig, monkeypatch, result):
    studio, client, seen = rig
    identity = complete(studio, prepare(studio))["voice_id"]
    operation = studio_voices.quote_preview(studio, identity)["operation"]
    studio_voices.confirm(studio, operation["id"], True)
    studio_voices.sample(studio, identity).unlink()
    def unavailable(url, target):
        if result == "expired": raise OSError("original signed result expired")
        target.write_bytes(wav(3) if result == "changed-audio" else b"not audio")
    monkeypatch.setattr("backlot.studio_avatar.download_result", unavailable)
    for _ in range(2):
        assert studio_voices.quote_preview(studio, identity) == {"cached": True}
        with pytest.raises(WorkError, match="不会重新生成或收费"):
            studio_voices.sample(studio, identity)
    assert sum(k == "tts" for k, _ in seen) == 1


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
        reference = http.get(upload.json()["reference_url"], headers={"Range": "bytes=0-99"})
        assert reference.status_code == 206 and len(reference.content) == 100
        assert reference.content.startswith(b"RIFF") and reference.headers["cache-control"] == "private, no-store"
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


def test_prepared_reference_is_account_private_and_integrity_checked(rig):
    studio, _, _ = rig
    sample = studio_voices.upload_sample(studio, "own.wav", wav())
    path = personal.reference(studio, sample["id"])
    owner = studio.configuration()
    atomic_private(studio.config_path, {**owner, "api_key": "another-fake-owner"})
    with pytest.raises(WorkError): personal.reference(studio, sample["id"])
    atomic_private(studio.config_path, owner)
    path.write_bytes(b"tampered")
    with pytest.raises(WorkError): personal.reference(studio, sample["id"])
    with pytest.raises(WorkError): personal.reference(studio, "../../other")


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
