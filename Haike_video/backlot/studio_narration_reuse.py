"""Explicit reuse of a completed TTS prefix; never a synthetic paid checkpoint."""
import hashlib
import json
import math
from pathlib import Path
import subprocess

from backlot.work_catalog import WorkError, sha


def source(studio, draft, selection):
    from backlot.production_queue import ProductionQueue
    if set(selection) != {'task', 'end_seconds'}:
        raise WorkError('配音复用需要原完成任务和明确的原速结束时间')
    job = ProductionQueue(studio.private/'production-queue.sqlite3', studio.projects_root).get(selection['task'], include_private=True)
    request = job['frozen_request']; original = request['draft']
    if job['status'] != 'completed' or original['input'].get('soundMode') != 'voice':
        raise WorkError('只能复用已完成任务的原配音', 'template_mismatch')
    if draft['input'].get('soundMode') != 'voice' or any(draft['input'].get(k, 1 if k == 'rate' else None) != original['input'].get(k, 1 if k == 'rate' else None) for k in ('voiceId', 'toneId', 'rate')):
        raise WorkError('复用配音必须保留原音色和语速', 'template_mismatch')
    if not draft['text'] or not original['text'].startswith(draft['text']):
        raise WorkError('本次原文不是原配音的完整开头，不能复用', 'template_mismatch')
    root = studio.projects_root.resolve(); folder = root/original['id']/'renders'/request['render_id']
    if folder.is_symlink() or not folder.resolve().is_relative_to(root):
        raise WorkError('原配音目录无效', 'template_mismatch')
    state = json.loads((folder/'gateway-state.json').read_text()); stage = state['stages'].get('tts', {})
    quote = request.get('quotes', {}).get('tts') or {}
    if (stage.get('job', {}).get('status') != 'succeeded' or not quote or
            any(stage.get('quote', {}).get(k) != quote.get(k) for k in ('id', 'model', 'execution_route'))):
        raise WorkError('原配音没有匹配的成功回执', 'template_mismatch')
    audio = Path(state['prepared']['audio_path'])
    if audio.is_symlink() or not audio.resolve().is_relative_to(folder.resolve()) or not audio.is_file():
        raise WorkError('原配音文件无效', 'template_mismatch')
    end = selection['end_seconds']
    if type(end) not in (int, float) or not math.isfinite(end) or not 0 < end <= state['prepared']['duration'] or abs(end*25-round(end*25)) > .0001:
        raise WorkError('原声截取必须使用25fps精确时钟', 'template_mismatch')
    return audio, {'schema':'haike-narration-reuse/1', 'selection':selection,
        'source_task':job['job_id'], 'source_audio_sha256':sha(audio), 'source_quote_id':quote['id'],
        'source_intent':stage.get('intent_identity'), 'script_sha256':hashlib.sha256(draft['text'].encode()).hexdigest(),
        'duration':end, 'speed_changed':False, 'new_tts_calls':0}


def prepare(studio, draft, selection, target):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    audio, receipt = source(studio, draft, selection)
    ffmpeg, _ = resolve_ffmpeg_pair()
    result = subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', str(audio), '-t', str(receipt['duration']),
        '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', str(target)], capture_output=True, timeout=60)
    if result.returncode:
        raise WorkError('原配音截取未完成；没有重新配音', 'unavailable')
    return {**receipt, 'audio_sha256':sha(Path(target))}


def verify(studio, draft, receipt, audio):
    _, current = source(studio, draft, receipt['selection'])
    if any(receipt.get(k) != v for k, v in current.items()) or sha(Path(audio)) != receipt['audio_sha256']:
        raise WorkError('复用配音的原回执或文件已改变；未提交新费用', 'template_mismatch')
