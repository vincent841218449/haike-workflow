"""One click prepares an account-private audition without a customer checkout."""
import time
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.studio_api import router
from backlot import studio_voices
from backlot import studio_voice_audition as audition, studio_personal_voice as personal
from backlot.work_catalog import WorkError
from test_studio_personal_voice import rig, prepare, complete


def wait_for_audition(studio):
    for _ in range(100):
        jobs = [v for v in studio_voices.operations(studio) if v["kind"] == "sample"]
        if jobs and jobs[0]["job"]["status"] not in {"queued", "submitting", "accepted"}: return jobs[0]
        time.sleep(.01)
    raise AssertionError("audition did not finish")


def test_one_click_audition_needs_no_fee_confirmation_and_reuses_cache(rig, monkeypatch):
    studio, _, seen = rig
    identity = complete(studio, prepare(studio))["voice_id"]
    studio_voices.catalogue(studio)
    # Migrate the unconfirmed quote left by the previous checkout screen.
    old = studio_voices.quote_preview(studio, identity)["operation"]
    monkeypatch.setattr("backlot.studio_voice_samples.prefetch", lambda *a: None)
    app = FastAPI(); app.state.studio = studio; app.include_router(router)
    with TestClient(app) as http:
        path = "/api/studio/voices/" + identity + "/audition"
        response = http.post(path, json={})
        assert response.status_code == 200, response.text
        assert response.json()["customer_charge_micros"] == "0"
        assert "quote" not in response.json()
        for _ in range(100):
            items = http.get("/api/studio/voice-operations").json()["items"]
            job = next(v for v in items if v["kind"] == "sample")
            if job.get("job", {}).get("status") == "succeeded": break
            time.sleep(.01)
        assert job["id"] == old["id"] and job["job"]["status"] == "succeeded"
        assert job["quote"]["max_charge_micros"] != "0"  # Supplier cost stays truthful.
        for _ in range(3):
            ready = http.post(path, json={}).json()
            assert ready["status"] == "succeeded" and ready["customer_charge_micros"] == "0"
            audio = http.get(ready["sample_url"], headers={"Range": "bytes=0-99"})
            assert audio.status_code == 206 and audio.content.startswith(b"RIFF")
    assert sum(action == "tts" for action, _ in seen) == 1


def test_preparation_runs_in_background_and_library_remains_responsive(rig, monkeypatch):
    studio, _, seen = rig
    identity = complete(studio, prepare(studio))["voice_id"]
    original = personal.requests.Session.post
    entered, release = threading.Event(), threading.Event()
    def slow(self, url, **kwargs):
        if kwargs.get("json", {}).get("model") != "voice-enrollment":
            entered.set(); assert release.wait(3)
        return original(self, url, **kwargs)
    monkeypatch.setattr(personal.requests.Session, "post", slow)
    started = time.monotonic()
    assert audition.prepare(studio, identity)["customer_charge_micros"] == "0"
    assert entered.wait(1)
    try:
        for _ in range(3):
            assert studio_voices.operations(studio)[0]["job"]["status"] == "submitting"
            assert audition.prepare(studio, identity)["status"] == "submitting"
        assert time.monotonic() - started < 1
    finally:
        release.set()
        assert wait_for_audition(studio)["job"]["status"] == "succeeded"
    assert sum(action == "tts" for action, _ in seen) == 1


def test_parallel_clicks_share_one_funded_operation_and_original_intent(rig):
    studio, _, seen = rig
    identity = complete(studio, prepare(studio))["voice_id"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: audition.prepare(studio, identity), range(8)))
    assert all(v["customer_charge_micros"] == "0" for v in results)
    assert wait_for_audition(studio)["job"]["status"] == "succeeded"
    jobs = [v for v in studio_voices.operations(studio) if v["kind"] == "sample"]
    assert len(jobs) == 1 and jobs[0]["funding"] == audition.POLICY
    assert sum(action == "tts" for action, _ in seen) == 1


def test_unknown_audition_never_submits_again(rig, monkeypatch):
    studio, _, seen = rig
    identity = complete(studio, prepare(studio))["voice_id"]
    def lost(*args, **kwargs):
        seen.append(("tts", {})); raise personal.requests.Timeout()
    monkeypatch.setattr(personal.requests.Session, "post", lost)
    audition.prepare(studio, identity)
    assert wait_for_audition(studio)["job"]["status"] == "submission_unknown"
    for _ in range(3):
        assert audition.prepare(studio, identity)["status"] == "submission_unknown"
    assert sum(action == "tts" for action, _ in seen) == 1


@pytest.mark.parametrize("limit", ["MAX_PREVIEW_MICROS", "DAILY_MAX_MICROS", "DAILY_MAX_VOICES"])
def test_service_budget_limits_block_new_calls_without_customer_checkout(rig, monkeypatch, limit):
    studio, _, seen = rig
    identity = complete(studio, prepare(studio))["voice_id"]
    monkeypatch.setattr(audition, limit, 0)
    with pytest.raises(WorkError): audition.prepare(studio, identity)
    assert not [v for v in seen if v[0] == "tts"]
    assert not [v for v in studio_voices.operations(studio) if v["kind"] == "sample"]


def test_arbitrary_text_or_voice_account_cannot_spend_the_audition_budget(rig):
    from backlot.studio import atomic_private
    studio, _, seen = rig
    identity = complete(studio, prepare(studio))["voice_id"]
    app = FastAPI(); app.state.studio = studio; app.include_router(router)
    with TestClient(app) as http:
        path = "/api/studio/voices/" + identity + "/audition"
        assert http.post(path, json={"text": "arbitrary text"}).status_code == 400
        assert http.post(path, json={}, headers={"Origin": "https://other.test"}).status_code == 403
        atomic_private(studio.config_path, {**studio.configuration(), "api_key": "another-owner"})
        assert http.post(path, json={}).status_code == 422
    assert not [v for v in seen if v[0] == "tts"]


def test_interrupted_reservation_recovers_original_sdk_intent(rig, monkeypatch):
    studio, client, seen = rig
    identity = complete(studio, prepare(studio))["voice_id"]
    original = client.confirm
    def interrupted(*args, **kwargs):
        original(*args, **kwargs); raise OSError("process stopped after saving intent")
    monkeypatch.setattr(client, "confirm", interrupted)
    with pytest.raises(OSError): audition.prepare(studio, identity)
    assert not [v for v in seen if v[0] == "tts"]
    monkeypatch.setattr(client, "confirm", original)
    audition.prepare(studio, identity)
    assert wait_for_audition(studio)["job"]["status"] == "succeeded"
    assert sum(action == "tts" for action, _ in seen) == 1
