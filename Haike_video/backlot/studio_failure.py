"""Persist useful stage/stack evidence without exception text or local variables."""

import traceback
from pathlib import Path
from uuid import uuid4

from backlot.studio import atomic_private, timestamp


def outcome(folder, stage, error):
    reference = "failure-" + uuid4().hex[:12]
    name = type(error).__name__
    frames = [
        {
            "file": Path(frame.filename).name,
            "line": frame.lineno,
            "function": frame.name,
        }
        for frame in traceback.extract_tb(error.__traceback__)
    ]
    atomic_private(
        Path(folder) / "failure.json",
        {
            "id": reference,
            "at": timestamp(),
            "stage": stage,
            "error_type": name,
            "frames": frames,
        },
    )
    message = f"{stage}未完成（{name}）；已保存诊断记录 {reference}，原素材和调用保留，请管理员修复该步骤后恢复原任务"
    return {
        "status": "failed",
        "stage": stage + "未完成",
        "error": {
            "code": "internal_failure",
            "type": name,
            "message": message,
            "diagnostic_ref": reference,
        },
        "retryable": True,
        "safe_resume_point": "studio_avatar",
    }
