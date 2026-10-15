"""Real SQLite queue transitions and HTTP projections; no supplier calls."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.production_queue import ProductionQueue, ProductionQueueConflict, ProductionQueueError
from backlot.studio import Studio
from backlot.studio_api import router


@pytest.fixture
def setup(tmp_path):
    studio = Studio(tmp_path / "projects")
    draft = studio.save_draft({"template_id": "graphic-news-v2", "title": "制作进度验收", "text": "测试", "input": {}})
    project = studio.projects_root / draft["id"]
    project.mkdir(parents=True)
    (project / "project.json").write_text(json.dumps({"title": draft["title"]}))
    queue = ProductionQueue(tmp_path / "queue.sqlite3", studio.projects_root)
    app = FastAPI()
    app.state.studio = studio
    app.state.works_projects_root = studio.projects_root
    app.state.production_queue = queue
    app.include_router(router)
    return studio, draft, queue, TestClient(app)


def submit(queue, draft, n=1, kind="studio_graphic"):
    return queue.submit(project_id=draft["id"], kind=kind, source="workbench", priority="normal",
                        parent_job_id=f"studio-{n}", frozen_request={"confirmed": True})


def test_observed_progress_is_durable_owned_and_preserved_on_failure(setup):
    studio, draft, queue, _ = setup
    job = submit(queue, draft)
    queue.claim_next("worker")
    queue.update_stage(job["job_id"], "worker", "合成第3段", completed=2, total=5)
    reopened = ProductionQueue(queue.db_path, studio.projects_root)
    assert reopened.get(job["job_id"])["progress"]["completed"] == 2
    assert reopened.get(job["job_id"])["progress"]["ratio"] == .4
    with pytest.raises(ProductionQueueConflict):
        queue.update_stage(job["job_id"], "another-worker", "假进度", completed=5, total=5)
    with pytest.raises(ProductionQueueError):
        queue.update_stage(job["job_id"], "worker", "错误计数", completed=6, total=5)
    queue.finish(job["job_id"], "worker", status="failed", stage="场景合成失败", retryable=True)
    assert reopened.get(job["job_id"])["progress"]["ratio"] == .4


def test_task_filters_paginate_without_dropping_completed_history(setup):
    _, draft, queue, client = setup
    for i in range(5):
        j = submit(queue, draft, i)
        queue.claim_next("worker")
        queue.finish(j["job_id"], "worker", status="completed", stage="已合成，待审核")
    submit(queue, draft, 10, "studio_avatar")
    page = client.get("/api/studio/tasks?status=completed&type=graphic&limit=2&offset=2")
    assert page.status_code == 200
    data = page.json()
    assert len(data["tasks"]) == 2
    assert data["pagination"] == {"offset": 2, "limit": 2, "total": 5, "has_more": True}
    assert data["counts"]["completed"] == 5
    assert all(t["progress"]["percent"] == 100 for t in data["tasks"])


def test_running_unknown_progress_is_not_an_invented_percentage(setup):
    _, draft, queue, client = setup
    job = submit(queue, draft)
    queue.claim_next("worker")
    response = client.get("/api/studio/tasks?status=active").json()
    task = response["tasks"][0]
    assert task["id"] == job["job_id"]
    assert task["progress"]["percent"] is None
    assert "正在" in task["stage"]
    assert not task["actions"].get("retry")


def test_failed_nonretryable_task_returns_to_original_draft_and_hides_private_input(setup):
    _, draft, queue, client = setup
    job = submit(queue, draft, kind="studio_avatar")
    queue.claim_next("worker")
    queue.finish(job["job_id"], "worker", status="failed", stage="音频与文案不一致",
                 error={"message": "核对原文与声音，未提交数字人", "api_key": "must-not-leak"}, retryable=False)
    response = client.get(f'/api/studio/tasks/{job["job_id"]}')
    assert response.status_code == 200
    task = response.json()["task"]
    assert task["edit_url"] == f'/avatar?draft={draft["id"]}'
    assert task["actions"]["retry"] is False
    assert task["error"] == "核对原文与声音，未提交数字人"
    assert "must-not-leak" not in json.dumps(response.json())
    assert response.json()["events"]


def test_invalid_filters_fail_explicitly(setup):
    client = setup[-1]
    assert client.get("/api/studio/tasks?status=imagined").status_code == 422
    assert client.get("/api/studio/tasks?offset=-1").status_code == 422
