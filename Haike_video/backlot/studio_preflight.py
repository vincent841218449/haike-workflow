"""Local composition checks and the frozen automatic fallback policy."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess

from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha


def basic_draft(draft):
    value = deepcopy(draft)
    motion = value["input"].pop("motion", None) or {}
    value["input"]["outputLayout"] = motion.get("layout", "portrait")
    value["template_id"] = "avatar-safe-circle-v1"
    value["title"] = value["title"][:15] + "…" if len(value["title"]) > 16 else value["title"]
    value["layout"]["title_size"] = min(value["layout"].get("title_size", 60), 48)
    return value


def prepare(studio, draft, folder, audio, cues, storyboard, caption_cues):
    if not draft["input"].get("motion"):
        return {"mode": "basic", "draft": draft, "notice": ""}
    folder = Path(folder)
    identity = hashlib.sha256(json.dumps([draft, sha(audio), cues, storyboard], sort_keys=True).encode()).hexdigest()
    path = folder / "composition-preflight.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if saved.get("fingerprint") != identity: raise WorkError("制作检查输入已改变，原结果保留")
        return saved
    try:
        from backlot.studio_storyboard import select_motion, motion_draft
        from backlot.studio_motion import plan
        from lib.ffmpeg_locator import resolve_ffmpeg_pair
        selected = select_motion(studio, draft, folder, cues, storyboard)
        ffmpeg, _ = resolve_ffmpeg_pair()
        frames = math.ceil(storyboard["duration"] * 60 - 1e-7)
        # Explicitly internal: a still image checks timing/bindings, never a deliverable avatar.
        placeholder = folder / "internal-layout-check.mp4"
        portrait = studio.asset(draft["input"]["portrait"]["id"], draft["id"])
        result = subprocess.run([ffmpeg, "-v", "error", "-y", "-loop", "1", "-i", str(portrait),
            "-i", str(audio), "-vf", "scale=448:560:force_original_aspect_ratio=decrease,pad=448:560:(ow-iw)/2:(oh-ih)/2,fps=60",
            "-frames:v", str(frames), "-t", str(frames/60), "-c:v", "libx264", "-preset", "ultrafast",
            "-tune", "stillimage", "-pix_fmt", "yuv420p", "-c:a", "aac", str(placeholder)], capture_output=True, timeout=180)
        if result.returncode: raise WorkError("本地模板预检无法读取人物或声音")
        compiled = motion_draft(studio, draft, placeholder, frames, selected, caption_cues)
        report = plan(studio, compiled)
        if not report["report"]["ready"]: raise WorkError("模板动作、素材或时长没有形成完整编排")
        saved = {"mode": "motion", "draft": draft, "notice": "", "report": report, "fingerprint": identity}
    except (WorkError, subprocess.TimeoutExpired) as exc:
        if draft["input"].get("templatePolicy", "auto") == "strict":
            raise WorkError("所选模板与当前内容不兼容；请选择自动兼容或更换模板，声音和素材已保留", "template_incompatible") from exc
        saved = {"mode": "basic", "draft": basic_draft(draft), "fingerprint": identity,
                 "notice": "所选动效未通过完整编排检查，已自动使用基础圆框口播，无需重新配音或生成数字人。",
                 "reason": str(exc)[:1200]}
    atomic_private(path, saved)
    return saved
