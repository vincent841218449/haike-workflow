"""Local checks preserve the selected visual style, including automatic variants."""
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


def prepare(studio, draft, folder, audio, cues, storyboard, caption_cues, *, legacy_variant=False):
    if not draft["input"].get("motion"):
        return {"mode": "basic", "draft": draft, "notice": ""}
    if draft['input']['motion']['style'].startswith('motiongit-'):
        from backlot.studio_motiongit import prepare as prepare_motiongit
        return prepare_motiongit(studio,draft,folder,audio,cues,storyboard,caption_cues)
    folder = Path(folder)
    direction_path=folder/'native-direction.json'
    if direction_path.is_file() and json.loads(direction_path.read_text()).get('workflow')=='adu-source-components-v1':
        if draft['input'].get('templateExecution') == 'native':
            raise WorkError('所选为原生镜头组，组件自适应不能通过制作检查', 'template_mismatch')
        from backlot.studio_adu_components import prepare as components
        from backlot.studio_render import media_probe
        return components(draft,folder,audio,cues,media_probe(audio)['duration'],caption_cues)
    identity = hashlib.sha256(json.dumps([draft, sha(audio), cues, storyboard], sort_keys=True).encode()).hexdigest()
    path = folder / "composition-preflight.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if saved.get("fingerprint") != identity: raise WorkError("制作检查输入已改变，原结果保留")
        if saved.get('mode') == 'basic':
            raise WorkError('旧检查曾将所选模板替换为基础口播；请保留原素材重新安排所选模板', 'template_incompatible')
        if saved.get('mode') == 'instrument':
            if not legacy_variant: raise WorkError('旧自有仪器台效果不是所选 ADu 原生模板，请创建本地重排版本', 'template_mismatch')
            from backlot.studio_presentation import instrument_plan
            if instrument_plan(draft,storyboard) != saved.get('presentation'):
                raise WorkError('所选仪器台组件或分镜已更新，需重新检查；原声音与素材保留', 'template_incompatible')
        return saved
    from backlot.studio_presentation import instrument_plan
    if legacy_variant and draft['input']['motion']['style'] == '04-A' and draft['input'].get('templatePolicy','auto') != 'strict':
        saved={'mode':'instrument', 'draft':draft, 'notice':'已按仪器台演示的自动口播版编排，保留所选风格和全部原文。',
               'presentation':instrument_plan(draft,storyboard), 'fingerprint':identity}
        atomic_private(path,saved)
        return saved
    try:
        from backlot.studio_storyboard import select_motion, motion_draft
        from backlot.studio_motion import plan
        from lib.ffmpeg_locator import resolve_ffmpeg_pair
        initial_selection = select_motion(studio, draft, folder, cues, storyboard)
        ffmpeg, _ = resolve_ffmpeg_pair()
        frames = math.ceil(storyboard["duration"] * 60 - 1e-7)
        # Explicitly internal: a still image checks timing/bindings, never a deliverable avatar.
        placeholder = folder / "internal-layout-check.mp4"
        portrait = studio.asset(draft["input"]["portrait"]["id"], draft["id"])
        diagnostics = None
        for attempt in range(3):
            try:
                selected = initial_selection if attempt == 0 else select_motion(studio, draft, folder, cues, storyboard, attempt=attempt, diagnostics=diagnostics)
                if not placeholder.exists():
                    result = subprocess.run([ffmpeg, "-v", "error", "-y", "-loop", "1", "-i", str(portrait),
                        "-i", str(audio), "-vf", "scale=448:560:force_original_aspect_ratio=decrease,pad=448:560:(ow-iw)/2:(oh-ih)/2,fps=60",
                        "-frames:v", str(frames), "-t", str(frames/60), "-c:v", "libx264", "-preset", "ultrafast",
                        "-tune", "stillimage", "-pix_fmt", "yuv420p", "-c:a", "aac", str(placeholder)], capture_output=True, timeout=180)
                    if result.returncode: raise WorkError("本地模板预检无法读取人物或声音")
                compiled = motion_draft(studio, draft, placeholder, frames, selected, caption_cues)
                report = plan(studio, compiled)
                if not report['report']['ready']:
                    diagnostics = json.dumps(report['report'], ensure_ascii=False)
                    raise WorkError('模板动作、素材或时长没有形成完整编排：' + diagnostics[:1500])
                if attempt:
                    atomic_private(folder / 'motion-selection.json', json.loads((folder / f'motion-selection-attempt-{attempt}.json').read_text()))
                break
            except WorkError as exc:
                if exc.code == 'unavailable' or attempt == 2 or not (folder / 'native-direction.json').is_file(): raise
                diagnostics = str(exc)
        saved = {"mode": "motion", "draft": draft, "notice": "", "report": report, "fingerprint": identity}
    except (WorkError, subprocess.TimeoutExpired) as exc:
        raise WorkError('所选模板暂不能完整表达本期内容；已保留模板、声音与素材，不会自动换风格。原因：'+str(exc)[:300], 'template_incompatible') from exc
    atomic_private(path, saved)
    return saved
