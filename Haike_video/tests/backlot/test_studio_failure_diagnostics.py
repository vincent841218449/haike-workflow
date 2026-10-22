import json
from types import SimpleNamespace

from backlot.studio import Studio
from backlot.studio_avatar import run_avatar


def test_unexpected_template_failure_records_safe_stage_and_trace(
    tmp_path, monkeypatch
):
    studio = Studio(tmp_path / "projects")
    draft = studio.save_draft(
        {
            "template_id": "avatar-safe-circle-v1",
            "text": "完整原文",
            "input": {"motion": {"style": "03-A", "layout": "portrait"}},
        }
    )
    monkeypatch.setattr("backlot.studio_avatar.key_identity", lambda s: "same")
    monkeypatch.setattr(
        "backlot.studio_presentation.verify_native", lambda *a, **k: None
    )

    def broken(*a):
        raise RuntimeError("Bearer private-secret-must-not-leak")

    monkeypatch.setattr("backlot.studio_motion_director.direct", broken)
    request = {
        "key_identity": "same",
        "render_id": "failure-test",
        "prepared": {},
        "draft": draft,
        "workflow_version": 4,
        "template_ref": {"runtime": "adu-legacy"},
        "presentation": {"id": "adu:03-A:portrait"},
    }
    result = run_avatar(studio.projects_root / draft["id"], request, SimpleNamespace())
    assert result["error"]["code"] == "internal_failure"
    assert (
        "原生模板编排" in result["error"]["message"]
        and "RuntimeError" in result["error"]["message"]
    )
    diagnostic = json.loads(
        (
            studio.projects_root / draft["id"] / "renders/failure-test/failure.json"
        ).read_text()
    )
    assert diagnostic["error_type"] == "RuntimeError" and diagnostic["frames"]
    assert "private-secret" not in json.dumps([result, diagnostic])
