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
    # Rendering kind describes the worker, not the UI in which the user created it.
    # Automatic native recompositions keep the simple avatar draft and inputs.
    try:
        draft = (job.get('frozen_request') or {}).get('draft') or studio.draft(job["project_id"])
    except WorkError:
        draft = None
    manual_motion = category == 'motion' and (draft is None or draft.get('template_id') == 'avatar-motion-adu-v1')
    motion_input=(draft or {}).get('input',{})
    motiongit_editor = manual_motion and str(motion_input.get('style') or (motion_input.get('motion') or {}).get('style','')).startswith('motiongit-')
    route = "/graphic" if category == "graphic" else "/avatar" if category in {"avatar", "motion"} else "/tasks"
    edit_url = route + "?draft=" + quote(job["project_id"], safe="") + ("&mode=motiongit" if motiongit_editor else "&mode=motion" if manual_motion else "") if category != "other" else route
    progress = job.get("progress") or json.loads(job.get('progress_json') or '{}')
    observed = progress.get("basis") == "steps" and progress.get("total", 0) > 0
    complete = job["status"] == "completed"
    percent = 100 if complete else round(progress["ratio"] * 100) if observed else None
    error = job.get("error") or {}
    # Preserve raw history, projecting recoverable input issues consistently
    # in the list, filters and details instead of presenting a production crash.
    if not error.get('code') and job['kind'] == 'studio_avatar' and job['status'] == 'failed' and '文案不一致' in str(job.get('stage', '')):
        error = {**error, 'code':'audio_script_mismatch'}
    provider_wait = job['status'] == 'ambiguous' and error.get('code') == 'provider_pending'
    audio_issue = error.get('code') in {'audio_script_mismatch','audio_check_review','audio_check_stale'}
    generated_audio_issue = audio_issue and not complete and motion_input.get('soundMode')=='voice'
    generated_audio_ready = False
    if generated_audio_issue and error.get('code')=='audio_check_review' and job['status']=='awaiting_human':
        from backlot.studio_audio_check import generated_clock_ready
        generated_audio_ready=generated_clock_ready(studio.projects_root/job['project_id'],job.get('frozen_request') or {})
    template_issue = (category == 'avatar' and not complete and job['status'] in {'failed','awaiting_human'}
                      and error.get('code') == 'template_incompatible')
    template_draft_updated = False
    if template_issue and draft:
        try:
            current = studio.draft(job['project_id'])
            template_draft_updated = (current.get('revision',0) > draft.get('revision',0)
                and current['input'].get('templateExecution') == 'auto' and bool(current['input'].get('motion')))
        except WorkError:
            pass
    input_issue = audio_issue or error.get('code') in {'template_incompatible', 'budget_exceeded'}
    display_status='awaiting_human' if audio_issue and job['status']=='failed' else job['status']
    if input_issue:
        edit_url += '&resume_task=' + quote(job['job_id'], safe='') + ('#creation-voice' if audio_issue else '' if template_issue else '#more-fields')
        if audio_issue:edit_url=edit_url.replace('#creation-voice','&repair=voice#creation-voice')
        if generated_audio_issue:edit_url=edit_url.replace('&repair=voice#creation-voice','')
    elif job['kind']=='studio_avatar':
        edit_url += '&resume_task=' + quote(job['job_id'],safe='')
    material_confirmation = job['kind'] == 'studio_avatar' and job['status'] in {'failed','awaiting_human'} and '抖音' in (job.get('stage') or '')
    result = job.get("result") or {}
    work_id = result.get("work_id")
    title = job.get("project_title") or job.get("title") or label
    ratio, template_name, version_id, media_url, approved, excerpt = None, "", None, None, False, ""
    # Drafts may be archived; queue history remains readable without modifying them.
    try:
        if draft is None: raise WorkError('原草稿已归档')
        excerpt = str(draft.get('text') or '')[:180]
        title = draft.get('title') or title
        template = next((t for t in TEMPLATES if t['id'] == draft.get('template_id')), {})
        ratio, template_name = template.get('ratio'), template.get('name', '')
        if draft.get('input', {}).get('motion'):
            ratio = '16:9' if draft['input']['motion'].get('layout') == 'landscape' else '9:16'
            requested = (job.get('frozen_request') or {}).get('presentation') or {}
            template_name = requested.get('name') or draft['input']['motion'].get('style', '')
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
        "id": job["job_id"], "revision": job.get('revision'), "project_id": job["project_id"], "title": title, "excerpt": excerpt,
        "type": category, "type_label": label, "status": display_status, "raw_status":job['status'],
        "status_label": "待继续制作" if generated_audio_ready else "配音对时待处理" if generated_audio_issue else "待按新方案制作" if template_draft_updated else "待调整制作方案" if template_issue else "等待选择音色" if audio_issue and not complete else "等待继续制作" if error.get('code') == 'budget_exceeded' and job['status'] == 'awaiting_human' else "等待供应商返回" if provider_wait else "等待确认素材" if material_confirmation else "已排期" if scheduled else "已完成 · 已选发布版本" if complete and approved else "正在取消后续制作" if job.get("cancel_requested") and not complete else LABELS.get(job["status"], job["status"]),
        "ratio": ratio, "template_name": template_name, "work_id": work_id,
        "presentation": {k:v for k,v in result.get('presentation',{}).items() if k in {'id','name','variant_name'}},
        "requested_presentation": {k:v for k,v in (result.get('requested_presentation') or job.get('frozen_request',{}).get('presentation') or {}).items() if k in {'id','name'}},
        "version_id": version_id, "media_url": media_url, "scheduled": scheduled,
        "stage": "原配音已生成，字幕对时复核已通过。可复用原配音继续，不会重新配音；数字人阶段仍按原任务执行。" if generated_audio_ready else "后台声音核对未通过，当前已停止制作。已选音色保留，请核对原配音；无需重新选择音色。" if generated_audio_issue else "原任务停在旧版模板校验。新版自动制作草稿已保存，未重新制作；请返回制作页核对后再提交。" if template_draft_updated else "原模板输入需要调整。请返回制作页保存制作方案后继续；直接重试只会重复原来的校验。" if template_issue else "选择音色后，将按原文案配音。原文案、素材及制作记录已保留。" if audio_issue and not complete else "视频制作完成，可直接播放和下载" if complete and not result.get('work_registration_error') else job.get("stage") or LABELS.get(job["status"], "等待处理"),
        "progress": {"percent": percent, "completed": progress.get("completed", 0) if observed else int(complete),
                     "total": progress.get("total", 0) if observed else int(complete),
                     "basis": "steps" if observed else "task" if complete else "unknown"},
        "created_at": job.get("created_at"), "updated_at": job.get("updated_at"),
        "started_at": job.get("started_at"), "finished_at": job.get("finished_at"),
        "queue_position": job.get("queue_position"), "wait_reason": job.get("wait_reason"),
        "error": "" if provider_wait or audio_issue else str(error.get("message") or "") if isinstance(error, dict) else str(error),
        "error_code": error.get('code'), "provider_wait": provider_wait,
        "audio_issue":audio_issue,
        "template_issue":template_issue, "template_draft_updated":bool(template_draft_updated),
        "max_charge_micros": (job.get('frozen_request') or {}).get('max_charge_micros'),
        "billing_policy": (job.get('frozen_request') or {}).get('billing_policy', 'limited'),
        "notice": "视频已生成，成片登记尚未完成，请保留原任务并检查制作记录。" if result.get("work_registration_error") else result.get('notice') or "",
        "edit_url": edit_url, "work_url": "/tasks?task=" + quote(job['job_id'], safe="") if work_id else None,
        "actions": {"retry": generated_audio_ready or (job["status"] == "failed" and bool(job.get("retryable")) and not material_confirmation and not audio_issue and not template_issue),
                    "retry_label":"复用原配音继续" if generated_audio_ready else "继续原任务",
                    "continue": job['kind'] == 'studio_avatar' and job['status'] == 'awaiting_human' and error.get('code') == 'budget_exceeded' and not job.get('cancel_requested'),
                    "pause": job["status"] == "queued" or provider_wait, "resume": job["status"] == "paused",
                    "cancel": (job["status"] in {"queued", "running", "paused", "awaiting_human"} or provider_wait) and not job.get("cancel_requested"),
                    "edit_label": "查看制作内容" if generated_audio_issue else "查看已修复草稿" if template_draft_updated else "调整制作方案" if template_issue else "选择音色并配音" if audio_issue else "返回制作项目" if error.get('code') == 'budget_exceeded' else "调整模板策略" if input_issue else "返回制作项目"},
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
    pending, current_pending = False, False
    # Billing receipts do not decide whether a playable artifact is complete.
    for member in members:
        render = member.get('frozen_request', {}).get('render_id')
        if not render or Path(render).name != render: continue
        path = studio.projects_root / member['project_id'] / 'renders' / render / 'gateway-state.json'
        try:
            saved=json.loads(path.read_text())
            def unresolved(s):
                j=s.get('job',{})
                return j.get('reconciliation_pending') is True or j.get('status')=='submission_unknown' or j.get('status')=='succeeded' and j.get('cost_status')=='supplier_bill_pending'
            active=list(saved.get('stages',{}).values())
            archived=[h['stage'] for h in saved.get('stage_history',[])]
            current_pending |= member['job_id']==latest['job_id'] and any(unresolved(s) for s in active)
            pending |= any(unresolved(s) for s in [*active,*archived])
        except (OSError, ValueError): pass
    value['billing_pending'] = pending
    value['billing_pending_scope'] = 'current' if current_pending else 'previous_attempt' if pending else None
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
                      project_input_issues=True,
                      include_provider_waits=status=='active', exclude_provider_waits=status=='needs_action',
                      result_output_paths=scheduled if status == 'scheduled' else None)
    summary = queue.list(kinds=kinds, limit=1, collapse_creations=True,project_input_issues=True)
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
