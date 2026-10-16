from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backlot.production_queue import ProductionQueue
from backlot import production_queue_worker as worker_mod
from backlot.production_queue_worker import ProductionQueueWorker


def _setup(tmp_path: Path) -> tuple[ProductionQueue, Path]:
    projects = tmp_path / "projects"
    for project_id in ("alpha", "beta"):
        project_dir = projects / project_id
        project_dir.mkdir(parents=True)
        (project_dir / "project.json").write_text(
            json.dumps({"id": project_id, "title": project_id}), encoding="utf-8"
        )
    return ProductionQueue(tmp_path / "queue.sqlite3", projects), projects


def _submit(queue: ProductionQueue, project_id: str, parent_job_id: str, kind: str) -> dict:
    return queue.submit(
        project_id=project_id,
        kind=kind,
        source="codex",
        priority="normal",
        parent_job_id=parent_job_id,
        frozen_request={"confirmed": True},
    )


def test_crash_after_automatic_basic_render_recovers_actual_fallback_file(tmp_path):
    queue, projects = _setup(tmp_path)
    job = queue.submit(project_id='alpha',kind='studio_avatar',source='workbench',priority='normal',parent_job_id='r',
        frozen_request={'render_id':'r','draft':{'input':{'motion':{'style':'04-A'}}}})
    folder = projects/'alpha/renders/r';folder.mkdir(parents=True)
    (folder/'composition-preflight.json').write_text('{"mode":"basic"}')
    (folder/'qa.json').write_text('{}');(folder/'avatar-preview.mp4').write_bytes(b'checked-video')
    worker = ProductionQueueWorker(queue,projects)
    result = worker.inspect_parent(queue.get(job['job_id'],include_private=True))
    assert result['status']=='completed' and result['result']['output_path'].endswith('avatar-preview.mp4')


def test_new_avatar_crash_revalidates_frozen_job_before_adopting_files(tmp_path):
    queue,projects=_setup(tmp_path)
    job=queue.submit(project_id='alpha',kind='studio_avatar',source='workbench',priority='normal',parent_job_id='original',
        frozen_request={'workflow_version':5,'render_id':'original','draft':{'input':{'motion':{'style':'03-A'}}}})
    folder=projects/'alpha/renders/original';folder.mkdir(parents=True)
    (folder/'qa.json').write_text('{}')
    (folder/'motion-preview.mp4').write_bytes(b'interrupted-or-foreign-output')
    worker=ProductionQueueWorker(queue,projects)
    outcome=worker.inspect_parent(queue.get(job['job_id'],include_private=True))
    assert outcome['status']=='queued'
    assert 'result' not in outcome
    assert queue.get(job['job_id'],include_private=True)['frozen_request']['render_id']=='original'


def test_worker_dispatches_only_registered_kind_and_continues_after_failure(tmp_path: Path) -> None:
    queue, projects = _setup(tmp_path)
    first = _submit(queue, "alpha", "RP-fail", "review_preview")
    second = _submit(queue, "beta", "ARP-ok", "avatar_review_preview")
    calls: list[str] = []

    def fail(job: dict) -> dict:
        calls.append(job["parent_job_id"])
        raise RuntimeError("isolated fake failure")

    def complete(job: dict) -> dict:
        calls.append(job["parent_job_id"])
        return {"status": "completed", "stage": "等待人工观看", "result": {"preview": "fake.mp4"}}

    worker = ProductionQueueWorker(
        queue,
        projects,
        handlers={"review_preview": fail, "avatar_review_preview": complete},
        worker_id="test-worker",
    )
    assert worker.run_once()["status"] == "failed"
    assert worker.run_once()["status"] == "completed"
    assert calls == ["RP-fail", "ARP-ok"]
    assert queue.get(first["job_id"])["status"] == "failed"
    assert queue.get(second["job_id"])["result"] == {"preview": "fake.mp4"}


def test_cancellation_stops_at_progress_before_another_paid_stage(tmp_path):
    queue,projects=_setup(tmp_path)
    job=_submit(queue,'alpha','cancel-before-avatar','studio_avatar')
    paid=[]
    worker=ProductionQueueWorker(queue,projects,worker_id='test-cancel-worker')
    def run(current):
        queue.cancel(current['job_id'])
        worker._stage_reporter(current)('准备下一笔数字人请求',1,5)
        paid.append('must not submit')
        return {'status':'completed','stage':'should never finish'}
    worker.handlers={'studio_avatar':run}
    assert worker.run_once()['status']=='cancelled'
    assert paid==[] and queue.get(job['job_id'])['status']=='cancelled'


def test_worker_maps_waiting_and_ambiguous_without_retrying(tmp_path: Path) -> None:
    queue, projects = _setup(tmp_path)
    waiting = _submit(queue, "alpha", "RP-wait", "review_preview")
    ambiguous = _submit(queue, "beta", "ARP-ambiguous", "avatar_review_preview")
    outcomes = {
        "RP-wait": {"status": "awaiting_human", "stage": "试听声音样板"},
        "ARP-ambiguous": {"status": "ambiguous", "stage": "核对 RunningHub 提交结果"},
    }
    worker = ProductionQueueWorker(
        queue,
        projects,
        handlers={
            "review_preview": lambda job: outcomes[job["parent_job_id"]],
            "avatar_review_preview": lambda job: outcomes[job["parent_job_id"]],
        },
        worker_id="test-worker",
    )

    assert worker.run_once()["status"] == "awaiting_human"
    assert worker.run_once()["status"] == "ambiguous"
    assert queue.get(waiting["job_id"])["retryable"] is False
    assert queue.get(ambiguous["job_id"])["wait_reason"]


def test_expired_lease_is_reconciled_from_parent_state_without_new_parent_id(tmp_path: Path) -> None:
    queue, projects = _setup(tmp_path)
    task = _submit(queue, "alpha", "RP-stable", "review_preview")
    claimed = queue.claim_next("dead-worker")
    assert claimed and claimed["parent_job_id"] == "RP-stable"
    with sqlite3.connect(queue.db_path) as connection:
        connection.execute(
            "UPDATE production_jobs SET lease_expires_at='2000-01-01T00:00:00.000000Z' WHERE job_id=?",
            (task["job_id"],),
        )
        connection.commit()

    worker = ProductionQueueWorker(
        queue,
        projects,
        handlers={"review_preview": lambda job: {"status": "completed", "stage": "完成"}},
        worker_id="replacement-worker",
    )
    worker.inspect_parent = lambda job: {"status": "queued", "stage": "等待从原安全点恢复"}  # type: ignore[method-assign]
    reconciled = worker.reconcile_expired()

    assert reconciled[0]["status"] == "queued"
    assert reconciled[0]["parent_job_id"] == "RP-stable"
    assert worker.run_once()["status"] == "completed"
    assert queue.get(task["job_id"])["attempt_count"] == 2


def test_full_preview_exception_marks_project_child_failed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    queue, projects = _setup(tmp_path)
    failed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        worker_mod,
        "read_workbench",
        lambda _project: {"automation": {"preview_render": {"status": "generating"}}},
    )
    monkeypatch.setattr(
        worker_mod,
        "generate_full_preview_render",
        lambda _project: (_ for _ in ()).throw(RuntimeError("fake render failure")),
    )
    monkeypatch.setattr(
        worker_mod,
        "mark_full_preview_render_failed",
        lambda project, error: failed.append((project.name, str(error))),
    )
    worker = ProductionQueueWorker(queue, projects, worker_id="test-worker")

    try:
        worker._run_full_preview({"project_id": "alpha", "frozen_request": {"confirmed": True}})
    except RuntimeError as exc:
        assert str(exc) == "fake render failure"
    else:
        raise AssertionError("expected fake render failure")

    assert failed == [("alpha", "fake render failure")]
