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


def completed_versions(setup, monkeypatch):
    from backlot.work_catalog import WorkCatalog
    studio, draft, queue, client = setup
    project = studio.projects_root / draft['id']
    monkeypatch.setattr('backlot.work_catalog.probe', lambda p: {'duration': 9, 'width': 1080, 'height': 1440 if p.name == 'first.mp4' else 1920, 'has_audio': True})
    catalog = WorkCatalog(studio.projects_root)
    jobs, versions = [], []
    for index, name in enumerate(['first.mp4', 'second.mp4']):
        path = project / name; path.write_bytes(name.encode())
        work = catalog.register(draft['id'], path)
        version = work['versions'][-1]
        job = submit(queue, draft, 20 + index)
        queue.claim_next('worker')
        queue.finish(job['job_id'], 'worker', status='completed', stage='已生成', result={'work_id': work['work_id'], 'output_path': str(path)})
        jobs.append(job); versions.append(version)
    return work, jobs, versions


def test_completed_task_previews_its_own_version_and_ratio_not_the_latest(setup, monkeypatch):
    work, jobs, versions = completed_versions(setup, monkeypatch)
    client = setup[-1]
    task = client.get(f"/api/studio/tasks/{jobs[0]['job_id']}").json()['task']
    assert task['work_id'] == work['work_id']
    assert task['version_id'] == versions[0]['version_id']
    assert task['ratio'] == '3:4'
    assert task['media_url'].endswith('?version=' + versions[0]['version_id'])
    assert task['work_url'] == '/tasks?task=' + jobs[0]['job_id']


def test_scheduled_filter_is_version_specific_and_paginates_real_receipts(setup, monkeypatch):
    work, jobs, versions = completed_versions(setup, monkeypatch)
    studio, _, _, client = setup
    # Only the first version has an acknowledged schedule; a draft for the next
    # version must not label it as scheduled or affect counts.
    with studio.db() as db:
        for index, status in enumerate(['scheduled', 'draft', 'uncertain', 'canceled']):
            plan = {'work_id': work['work_id'], 'version_id': versions[0 if index == 0 else 1]['version_id'], 'status': status}
            db.execute('INSERT INTO studio_calendar VALUES(?,?,?)', (f'plan-{index}', 1, json.dumps(plan)))
    data = client.get('/api/studio/tasks?status=scheduled&limit=1').json()
    assert data['counts']['scheduled'] == 1
    assert data['pagination']['total'] == 1
    assert data['tasks'][0]['id'] == jobs[0]['job_id']
    assert data['tasks'][0]['status_label'] == '已排期'
    assert client.get('/api/studio/tasks?status=scheduled&offset=1').json()['tasks'] == []
    other = client.get(f"/api/studio/tasks/{jobs[1]['job_id']}").json()['task']
    assert other['scheduled'] is False


def test_empty_schedule_and_retired_projects_link_are_safe(setup):
    client = setup[-1]
    response = client.get('/projects?work=work-previous', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == '/tasks?work=work-previous'
    result = client.get('/api/studio/tasks?status=scheduled').json()
    assert result['tasks'] == [] and result['counts']['scheduled'] == 0


def test_task_summary_uses_submission_snapshot_after_draft_changes(setup):
    studio, draft, queue, client = setup
    frozen = {**draft, 'template_id': 'avatar-template3-card-3x4-v001', 'title': '原任务标题', 'text': '提交时的原文'}
    job = queue.submit(project_id=draft['id'], kind='studio_avatar', source='workbench', priority='normal', parent_job_id='snapshot', frozen_request={'draft': frozen, 'private_token': 'not-in-public-response'})
    studio.save_draft({**draft, 'title': '已修改的草稿', 'text': '新的文案'})
    data = client.get(f"/api/studio/tasks/{job['job_id']}").json()
    assert data['task']['title'] == '原任务标题'
    assert data['task']['excerpt'] == '提交时的原文'
    assert data['task']['ratio'] == '3:4'
    assert 'not-in-public-response' not in json.dumps(data)


def waiting_materials(setup):
    from backlot.studio import atomic_private
    studio, draft, queue, client = setup
    job = queue.submit(project_id=draft['id'],kind='studio_avatar',source='workbench',priority='normal',
        parent_job_id='studio-1',frozen_request={'draft':draft,'original_paid_intent':'keep-this-intent'})
    queue.claim_next('worker')
    queue.update_stage(job['job_id'],'worker','分镜素材准备',completed=2,total=7)
    queue.finish(job['job_id'],'worker',status='awaiting_human',stage='请选择有权使用的抖音素材，AI分析是否采用',
        safe_resume_point='studio_avatar_material_rights')
    folder = studio.projects_root / draft['id'] / 'renders/studio-1/ai-requests'
    atomic_private(folder / 'scene-1-candidates.json',{'items':[{'id':'first','title':'第一份'},{'id':'second','title':'第二份'}]})
    atomic_private(folder / 'scene-2-candidates.json',{'items':[{'id':'first','title':'第一份'}]})
    return job,folder


def test_task_material_multiselect_confirms_scope_then_resumes_same_job(setup):
    studio,_,queue,client = setup
    job,folder = waiting_materials(setup)
    data = client.get('/api/studio/tasks?status=needs_action').json()
    assert data['counts']['needs_action'] == 1 and data['counts']['failed'] == 0
    assert data['tasks'][0]['status_label'] == '等待确认素材'
    assert data['tasks'][0]['actions']['retry'] is False
    detail=client.get('/api/studio/tasks/'+job['job_id']).json()['task']
    assert detail['progress']['percent']==29 and detail['progress']['completed']==2
    url = '/api/studio/ai/jobs/' + job['job_id']
    assert len(client.get(url+'/douyin-candidates').json()['items']) == 2
    for selection,rights in [([],True),(['first','first'],True),(['foreign'],True),(['first'],False)]:
        assert client.post(url+'/authorize-douyin',json={'video_ids':selection,'rights_confirmed':rights}).status_code == 422
    assert queue.get(job['job_id'])['status'] == 'awaiting_human'
    response = client.post(url+'/authorize-douyin',json={'video_ids':['first','second'],'rights_confirmed':True})
    assert response.status_code == 200 and response.json()['job_id'] == job['job_id']
    assert queue.get(job['job_id'])['status'] == 'queued'
    assert queue.get(job['job_id'],include_private=True)['frozen_request']['original_paid_intent'] == 'keep-this-intent'
    decisions = json.loads((folder.parent/'source-decisions.json').read_text())
    assert decisions['authorized_video_ids'] == ['first','second'] and decisions['selection_mode'] == 'ai-reviewed'
    assert client.post(url+'/authorize-douyin',json={'video_ids':['first'],'rights_confirmed':True}).status_code == 409


def test_legacy_single_selection_remains_compatible_and_other_human_gates_stay_closed(setup):
    _,_,queue,client = setup
    job,_ = waiting_materials(setup)
    assert client.post('/api/studio/ai/jobs/'+job['job_id']+'/authorize-douyin',json={'video_id':'second','rights_confirmed':True}).status_code == 200
    queue.claim_next('worker')
    queue.finish(job['job_id'],'worker',status='awaiting_human',stage='其他人工审核',safe_resume_point='unrelated_gate')
    with pytest.raises(ProductionQueueConflict): queue.retry(job['job_id'])
