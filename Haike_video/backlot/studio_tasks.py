"""Public creation history projected from the existing durable production queue."""
from urllib.parse import quote

from backlot.work_catalog import WorkError

KINDS = {"graphic": ("studio_graphic",), "avatar": ("studio_avatar",), "motion": ("studio_motion",)}
STATUSES = {"all": None, "active": ("queued", "running"), "queued": ("queued",),
            "needs_action": ("paused", "awaiting_human", "ambiguous"), "failed": ("failed",),
            "completed": ("completed",), "cancelled": ("cancelled",)}
LABELS = {"queued": "排队中", "running": "制作中", "paused": "已暂停", "awaiting_human": "等待确认",
          "ambiguous": "结果待核对", "failed": "制作失败", "completed": "已完成 · 待审核", "cancelled": "已取消"}
TYPES = {"studio_graphic": ("graphic", "图文视频"), "studio_avatar": ("avatar", "数字人口播"),
         "studio_motion": ("motion", "动效口播")}


def task_view(studio, job):
    category, label = TYPES.get(job["kind"], ("other", "视频制作"))
    route = "/graphic" if category == "graphic" else "/avatar" if category in {"avatar", "motion"} else "/projects"
    edit_url = route + "?draft=" + quote(job["project_id"], safe="") + ("&mode=motion" if category == "motion" else "") if category != "other" else route
    progress = job.get("progress") or {}
    observed = progress.get("basis") == "steps" and progress.get("total", 0) > 0
    complete = job["status"] == "completed"
    percent = 100 if complete else round(progress["ratio"] * 100) if observed else None
    error = job.get("error") or {}
    result = job.get("result") or {}
    work_id = result.get("work_id")
    title = job.get("project_title") or job.get("title") or label
    # Drafts may be archived; queue history remains readable without modifying them.
    try:
        draft = studio.draft(job["project_id"])
        if draft.get("template_id") == "avatar-motion-adu-v1" or draft.get("input", {}).get("motion"):
            label = "数字人口播 · 动效" if category == "avatar" else label
    except WorkError:
        pass
    return {
        "id": job["job_id"], "project_id": job["project_id"], "title": title,
        "type": category, "type_label": label, "status": job["status"],
        "status_label": "正在取消后续制作" if job.get("cancel_requested") and not complete else LABELS.get(job["status"], job["status"]),
        "stage": job.get("stage") or LABELS.get(job["status"], "等待处理"),
        "progress": {"percent": percent, "completed": progress.get("completed", 0) if observed else int(complete),
                     "total": progress.get("total", 0) if observed else int(complete),
                     "basis": "steps" if observed else "task" if complete else "unknown"},
        "created_at": job.get("created_at"), "updated_at": job.get("updated_at"),
        "started_at": job.get("started_at"), "finished_at": job.get("finished_at"),
        "queue_position": job.get("queue_position"), "wait_reason": job.get("wait_reason"),
        "error": str(error.get("message") or "") if isinstance(error, dict) else str(error),
        "notice": "视频已生成，作品登记尚未完成，请保留原任务并检查作品页。" if result.get("work_registration_error") else "",
        "edit_url": edit_url, "work_url": "/projects?work=" + quote(work_id, safe="") if work_id else None,
        "actions": {"retry": job["status"] == "failed" and bool(job.get("retryable")),
                    "pause": job["status"] == "queued", "resume": job["status"] == "paused",
                    "cancel": job["status"] in {"queued", "running", "paused", "awaiting_human"} and not job.get("cancel_requested")},
    }


def list_tasks(studio, queue, *, status="all", task_type="all", limit=30, offset=0):
    kinds = KINDS.get(task_type)
    page = queue.list(kinds=kinds, statuses=STATUSES[status], limit=limit, offset=offset)
    summary = queue.list(kinds=kinds, limit=1)
    counts = {"all": summary["pagination"]["total"], "active": summary["active_count"] + summary["queued_count"],
              "queued": summary["queued_count"], "needs_action": summary["paused_count"] + summary["waiting_count"],
              "failed": summary["failure_count"], "completed": summary["completed_count"], "cancelled": summary["cancelled_count"]}
    return {"tasks": [task_view(studio, job) for job in page["tasks"]], "counts": counts,
            "pagination": page["pagination"], "execution": "local", "poll_after_ms": 3000}


def detail(studio, queue, job_id):
    events = []
    for index, item in enumerate(queue.events(job_id)):
        data = item.get("detail") or {}
        events.append({"id": f"{job_id}:{index}", "type": item["event_type"], "at": item["created_at"],
                       "stage": data.get("stage"), "from": item.get("from_status"), "to": item.get("to_status"),
                       "progress": data.get("progress")})
    return {"task": task_view(studio, queue.get(job_id)), "events": events}
