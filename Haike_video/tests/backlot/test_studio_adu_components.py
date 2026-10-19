from copy import deepcopy

import pytest
from backlot.studio_adu_components import supported, validate
from backlot.work_catalog import WorkError


def test_same_pack_components_keep_selected_style_and_layout_lock():
    draft = {"input": {"motion": {"style": "03-A", "layout": "portrait"}}}
    assert supported(draft)
    draft["input"]["templatePolicy"] = "strict"
    assert supported(draft)
    draft["input"].update(templatePolicy="auto", motion={"style": "04-A"})
    assert not supported(draft)
    draft["input"]["motion"] = {"style": "03-A", "layout": "landscape"}
    assert not supported(draft)
    draft["input"].update(
        motion={"style": "03-A", "layout": "portrait"},
        ai={"materials": [{"id": "owned"}]},
    )
    assert not supported(draft)
    draft["input"].update(ai={}, music={"mode": "track"})
    assert not supported(draft)


def test_component_semantics_preserve_source_and_refuse_invented_values():
    draft = {"text": "500万买来等待。20万买来现金流。"}
    parts = [
        {
            "text": draft["text"],
            "heading": "两笔账",
            "emphasis": ["500万", "20万"],
            "layout": "compare",
        }
    ]
    assert validate(draft, parts) == parts
    bad = deepcopy(parts)
    bad[0]["emphasis"][1] = "保证6个月回本"
    with pytest.raises(WorkError, match="真实原文"):
        validate(draft, bad)
    bad = deepcopy(parts)
    bad[0]["text"] = "20万买来现金流。500万买来等待。"
    with pytest.raises(WorkError, match="原文顺序"):
        validate(draft, bad)


def test_component_target_cannot_lose_its_nonpromise_qualifier():
    draft = {"text": "我们的目标是6个月——注意是目标，不是承诺。"}
    part = {
        "text": draft["text"],
        "heading": "目标说明",
        "layout": "quote",
        "emphasis": ["我们的目标是6个月"],
    }
    with pytest.raises(WorkError, match="非承诺"):
        validate(draft, [part])
    part["emphasis"] = ["我们的目标是6个月——注意是目标，不是承诺"]
    assert validate(draft, [part])


def test_delivery_decodes_actual_mp4_and_rejects_incomplete_or_wrong_clock(tmp_path):
    import subprocess

    from backlot.studio_adu_components import verify_delivery
    from lib.ffmpeg_locator import resolve_ffmpeg_pair

    try:
        ffmpeg, _ = resolve_ffmpeg_pair()
    except (RuntimeError, FileNotFoundError):
        pytest.skip("FFmpeg unavailable")
    output = tmp_path / "delivery.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=1080x1920:r=60:d=0.2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-t",
            "0.2",
            str(output),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    plan = {"frames": 12, "duration": 0.2}
    assert verify_delivery(output, plan)["full_decode"] is True
    with pytest.raises(WorkError, match="帧数"):
        verify_delivery(output, {**plan, "frames": 13})
    broken = tmp_path / "interrupted.mp4"
    data = output.read_bytes()
    broken.write_bytes(data[: len(data) // 2])
    with pytest.raises(WorkError):
        verify_delivery(broken, plan)


def test_template_and_budget_input_pauses_do_not_replay_the_old_frozen_request(tmp_path):
    from backlot.production_queue import ProductionQueue, ProductionQueueConflict

    projects = tmp_path / "projects"
    (projects / "p").mkdir(parents=True)
    (projects / "p/project.json").write_text('{"id":"p","title":"test"}')
    queue = ProductionQueue(tmp_path / "queue.sqlite3", projects)

    def waiting(code):
        job = queue.submit(
            project_id="p",
            kind="studio_avatar",
            source="codex",
            priority="normal",
            parent_job_id=code,
            frozen_request={"same": "frozen"},
        )
        queue.claim_next("worker")
        queue.finish(
            job["job_id"],
            "worker",
            status="awaiting_human",
            stage="修复模板后核验",
            error={"code": code},
            safe_resume_point="studio_avatar_input",
        )
        return job

    job = waiting("template_incompatible")
    with pytest.raises(ProductionQueueConflict,match='制作页'):
        queue.retry(job["job_id"])
    assert queue.get(job["job_id"], include_private=True)["frozen_request"] == {
        "same": "frozen"
    }
    queue.cancel(job["job_id"])
    budget = waiting("budget_exceeded")
    with pytest.raises(ProductionQueueConflict):
        queue.retry(budget["job_id"])


def test_provider_wait_can_pause_and_resume_original_request(tmp_path):
    from backlot.production_queue import ProductionQueue

    root = tmp_path / "projects"
    (root / "p").mkdir(parents=True)
    (root / "p/project.json").write_text('{"id":"p"}')
    queue = ProductionQueue(tmp_path / "queue.sqlite3", root)
    job = queue.submit(
        project_id="p",
        kind="studio_avatar",
        source="codex",
        priority="normal",
        parent_job_id="original",
        frozen_request={"provider_task": "same-id"},
    )
    queue.claim_next("worker")
    queue.finish(
        job["job_id"],
        "worker",
        status="ambiguous",
        stage="供应商运行中",
        error={"code": "provider_pending"},
        safe_resume_point="studio_avatar_provider",
    )
    assert queue.pause(job["job_id"])["status"] == "paused"
    assert queue.resume(job["job_id"])["status"] == "queued"
    assert queue.get(job["job_id"], include_private=True)["frozen_request"] == {
        "provider_task": "same-id"
    }
