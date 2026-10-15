"""Public creation history projected from the existing durable production queue."""
from urllib.parse import quote
import json
from pathlib import Path

from math import gcd
from backlot.work_catalog import WorkCatalog, WorkError
from backlot.studio import TEMPLATES

KINDS = {"graphic": ("studio_graphic",), "avatar": ("studio_avatar",), "motion": ("studio_motion",)}
STATUSES = {"all": None, "active": ("queued", "running"), "queued": ("queued",),
            "needs_action": ("paused", "awaiting_human", "ambiguous"), "failed": ("failed",),
            "completed": ("completed",), "scheduled": ("completed",), "cancelled": ("cancelled",)}
LABELS = {"queued": "排队中", "running": "制作中", "paused": "已暂停", "awaiting_human": "需要补充输入",
          "ambiguous": "结果待核对", "failed": "制作失败", "completed": "已完成", "cancelled": "已取消"}
TYPES = {"studio_graphic": ("graphic", "图文视频"), "studio_avatar": ("avatar", "数字人口播"),
         "studio_motion": ("motion", "动效口播")}


def task_view(studio, job, scheduled_paths=()):
    category, label = TYPES.get(job["kind"], ("other", "视频制作"))
    route = "/graphic" if category == "graphic" else "/avatar" if category in {"avatar", "motion"} else "/tasks"
    edit_url = route + "?draft=" + quote(job["project_id"], safe="") + ("&mode=motion" if category == "motion" else "") if category != "other" else route
    progress = job.get("progress") or json.loads(job.get('progress_json') or '{}')
    observed = progress.get("basis") == "steps" and progress.get("total", 0) > 0
    complete = job["status"] == "completed"
    percent = 100 if complete else round(progress["ratio"] * 100) if observed else None
    error = job.get("error") or {}
    # A legacy failure keeps its raw queue status; only its repair link gains
    # the structured input classification used by new creations.
    if not error.get('code') and job['kind'] == 'studio_avatar' and job['status'] == 'failed' and '文案不一致' in str(job.get('stage', '')):
        error = {**error, 'code':'audio_script_mismatch'}
    provider_wait = job['status'] == 'ambiguous' and error.get('code') == 'provider_pending'
    input_issue = error.get('code') in {'audio_script_mismatch', 'template_incompatible', 'budget_exceeded'}
    if input_issue:
        edit_url += '&resume_task=' + quote(job['job_id'], safe='') + ('#creation-voice' if error['code'] == 'audio_script_mismatch' else '#more-fields')
    elif job['kind']=='studio_avatar':
        edit_url += '&resume_task=' + quote(job['job_id'],safe='')
    material_confirmation = job['kind'] == 'studio_avatar' and job['status'] in {'failed','awaiting_human'} and '抖音' in (job.get('stage') or '')
    result = job.get("result") or {}
    work_id = result.get("work_id")
    title = job.get("project_title") or job.get("title") or label
    ratio, template_name, version_id, media_url, approved, excerpt = None, "", None, None, False, ""
    # Drafts may be archived; queue history remains readable without modifying them.
    try:
        draft = (job.get('frozen_request') or {}).get('draft') or studio.draft(job["project_id"])
        excerpt = str(draft.get('text') or '')[:180]
        title = draft.get('title') or title
        template = next((t for t in TEMPLATES if t['id'] == draft.get('template_id')), {})
        ratio, template_name = template.get('ratio'), template.get('name', '')
        if draft.get('input', {}).get('motion'):
            ratio = '16:9' if draft['input']['motion'].get('layout') == 'landscape' else '9:16'
        if draft.get("template_id") == "avatar-motion-adu-v1" or draft.get("input", {}).get("motion"):
            label = "数字人口播 · 动效" if category == "avatar" else label
        if result.get('composition_mode') == 'basic' and draft.get('input', {}).get('motion'):
            label = '数字人口播'
            template_name = next((t['name'] for t in TEMPLATES if t['id'] == result.get('effective_template_id')), '基础圆框口播')
        if result.get('presentation'):
            actual=result['presentation']
            template_name=actual['name']+(' · '+actual['variant_name'] if actual.get('variant_name') else '')
    except WorkError:
        pass
    if work_id:
        try:
            work = WorkCatalog(studio.projects_root).get(work_id)
            version = next((v for v in work['versions'] if result.get('output_path') in v['paths']), None)
            if version:
                version_id = version['version_id']
                media = version['media']
                width, height = int(media.get('width', 0)), int(media.get('height', 0))
                if width > 0 and height > 0:
                    divisor = gcd(width, height); ratio = f'{width // divisor}:{height // divisor}'
                media_url = f'/api/works/{quote(work_id, safe="")}/media?version={quote(version_id, safe="")}'
                approved = work.get('final_version_id') == version_id
        except WorkError:
            pass
    scheduled = complete and result.get('output_path') in scheduled_paths
    return {
        "id": job["job_id"], "project_id": job["project_id"], "title": title, "excerpt": excerpt,
        "type": category, "type_label": label, "status": job["status"],
        "status_label": "等待供应商返回" if provider_wait else "等待确认素材" if material_confirmation else "已排期" if scheduled else "已完成 · 已选发布版本" if complete and approved else "正在取消后续制作" if job.get("cancel_requested") and not complete else LABELS.get(job["status"], job["status"]),
        "ratio": ratio, "template_name": template_name, "work_id": work_id,
        "presentation": {k:v for k,v in result.get('presentation',{}).items() if k in {'id','name','variant_name'}},
        "requested_presentation": {k:v for k,v in (result.get('requested_presentation') or job.get('frozen_request',{}).get('presentation') or {}).items() if k in {'id','name'}},
        "version_id": version_id, "media_url": media_url, "scheduled": scheduled,
        "stage": "视频制作完成，可直接播放和下载" if complete and not result.get('work_registration_error') else job.get("stage") or LABELS.get(job["status"], "等待处理"),
        "progress": {"percent": percent, "completed": progress.get("completed", 0) if observed else int(complete),
                     "total": progress.get("total", 0) if observed else int(complete),
                     "basis": "steps" if observed else "task" if complete else "unknown"},
        "created_at": job.get("created_at"), "updated_at": job.get("updated_at"),
        "started_at": job.get("started_at"), "finished_at": job.get("finished_at"),
        "queue_position": job.get("queue_position"), "wait_reason": job.get("wait_reason"),
        "error": "" if provider_wait else str(error.get("message") or "") if isinstance(error, dict) else str(error),
        "error_code": error.get('code'), "provider_wait": provider_wait,
        "max_charge_micros": (job.get('frozen_request') or {}).get('max_charge_micros'),
        "notice": "视频已生成，成片登记尚未完成，请保留原任务并检查制作记录。" if result.get("work_registration_error") else result.get('notice') or "",
        "edit_url": edit_url, "work_url": "/tasks?task=" + quote(job['job_id'], safe="") if work_id else None,
        "actions": {"retry": job["status"] == "failed" and bool(job.get("retryable")) and not material_confirmation,
                    "pause": job["status"] == "queued", "resume": job["status"] == "paused",
                    "cancel": (job["status"] in {"queued", "running", "paused", "awaiting_human"} or provider_wait) and not job.get("cancel_requested"),
                    "edit_label": "按文案配音或替换录音" if error.get('code') == 'audio_script_mismatch' else "调整总费用上限" if error.get('code') == 'budget_exceeded' else "调整模板策略" if input_issue else "返回制作项目"},
    }


def creation_view(studio, queue, job, scheduled):
    value = task_view(studio, job, scheduled)
    members = queue.creation_members(job['job_id'])
    latest = members[-1]
    value.update(creation_id=members[0]['creation_id'], attempt_count=len(members),
                 current_task_id=latest['job_id'], is_current=latest['job_id'] == job['job_id'])
    if latest['job_id'] != job['job_id']:
        value['edit_url']=task_view(studio,latest,scheduled)['edit_url']
    success = next((m for m in reversed(members) if m['status'] == 'completed' and m.get('result', {}).get('work_id')), None)
    value['latest_success_id'] = success['job_id'] if success else None
    pending = False
    # Billing receipts do not decide whether a playable artifact is complete.
    for member in members:
        render = member.get('frozen_request', {}).get('render_id')
        if not render or Path(render).name != render: continue
        path = studio.projects_root / member['project_id'] / 'renders' / render / 'gateway-state.json'
        try:
            stages = json.loads(path.read_text()).get('stages', {})
            pending |= any(s.get('job', {}).get('reconciliation_pending') is True or s.get('job', {}).get('status') == 'submission_unknown' for s in stages.values())
        except (OSError, ValueError): pass
    value['billing_pending'] = pending
    return value


def scheduled_output_paths(studio):
    # Drafts and unknown publishing receipts never masquerade as an active schedule.
    paths = set()
    catalog = WorkCatalog(studio.projects_root)
    for plan in studio.calendar():
        if plan.get('status') not in {'scheduled', 'running'} or not plan.get('work_id'):
            continue
        try:
            work = catalog.get(plan['work_id'])
            version = next((v for v in work['versions'] if v['version_id'] == plan.get('version_id')), None)
            if version: paths.update(version['paths'])
        except WorkError:
            continue
    return tuple(paths)


def list_tasks(studio, queue, *, status="all", task_type="all", limit=30, offset=0):
    kinds = KINDS.get(task_type)
    scheduled = scheduled_output_paths(studio)
    page = queue.list(kinds=kinds, statuses=STATUSES[status], limit=limit, offset=offset, collapse_creations=True,
                      include_provider_waits=status=='active', exclude_provider_waits=status=='needs_action',
                      result_output_paths=scheduled if status == 'scheduled' else None)
    summary = queue.list(kinds=kinds, limit=1, collapse_creations=True)
    counts = {"all": summary["pagination"]["total"], "active": summary["active_count"] + summary["queued_count"] + summary['provider_wait_count'],
              "queued": summary["queued_count"], "needs_action": summary["paused_count"] + summary["waiting_count"] - summary['provider_wait_count'],
              "failed": summary["failure_count"], "completed": summary["completed_count"], "cancelled": summary["cancelled_count"]}
    counts['scheduled'] = queue.list(kinds=kinds, statuses=('completed',), result_output_paths=scheduled, limit=1, collapse_creations=True)['pagination']['total']
    return {"tasks": [creation_view(studio, queue, {**queue.get(job['job_id'], include_private=True), **job}, scheduled) for job in page["tasks"]], "counts": counts,
            "pagination": page["pagination"], "execution": "local", "poll_after_ms": 3000}


def detail(studio, queue, job_id):
    events = []
    for index, item in enumerate(queue.events(job_id)):
        data = item.get("detail") or {}
        events.append({"id": f"{job_id}:{index}", "type": item["event_type"], "at": item["created_at"],
                       "stage": data.get("stage"), "from": item.get("from_status"), "to": item.get("to_status"),
                       "progress": data.get("progress")})
    scheduled = scheduled_output_paths(studio)
    task = creation_view(studio, queue, queue.get(job_id, include_private=True), scheduled)
    attempts = [dict(task_view(studio, m, scheduled), relation=m.get('relation'), current=m['job_id'] == task['current_task_id']) for m in queue.creation_members(job_id)]
    return {"task": task, "events": events, "attempts": attempts}
