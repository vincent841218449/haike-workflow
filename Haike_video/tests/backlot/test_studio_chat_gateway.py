import base64
import json

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
