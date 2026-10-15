"""Continue an explicit creation with artifact reuse and one aggregate budget."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha


def _audio_key(draft):
    value = draft['input']
    if value.get('soundMode') == 'audio': return ['audio', (value.get('audio') or {}).get('id')]
    return ['voice', draft['text'], value.get('voiceId'), value.get('toneId'), value.get('rate', 1)]


def continue_request(studio, queue, request, previous_id):
    members = queue.creation_members(previous_id)
    previous = members[-1]
    if previous['job_id'] != previous_id or previous['status'] in {'queued', 'running', 'paused'}:
        raise WorkError('请从当前制作记录继续，正在制作的任务无需重新提交')
    draft = request['draft']
    if previous['project_id'] != draft['id'] or previous['kind'] != 'studio_avatar':
        raise WorkError('恢复记录与当前口播项目不一致')
    old = previous.get('frozen_request', {})
    if old.get('key_identity') != request.get('key_identity'):
        raise WorkError('恢复制作需要使用原API账户连接，原调用和费用记录已保留')
    before = old.get('draft', {})
    project = (studio.projects_root / draft['id']).resolve()
    def folder_for(frozen):
        name = frozen.get('render_id')
        if not name or Path(name).name != name: raise WorkError('原制作目录无效')
        path = project / 'renders' / name
        if not path.resolve().is_relative_to(project): raise WorkError('原制作目录越界')
        return path
    def owned(path):
        path = Path(path).resolve()
        if not path.is_relative_to(project) or not path.is_file(): raise WorkError('原制作素材缺失，请恢复原文件')
        return path
    source, target = folder_for(old), folder_for(request)
    if source == target: raise WorkError('内容未改变，请继续原任务')
    state_path = source / 'gateway-state.json'
    state = json.loads(state_path.read_text()) if state_path.is_file() else {'stages': {}, 'prepared': {}}
    same_audio = bool(before) and _audio_key(before) == _audio_key(draft)
    same_avatar = same_audio and before['input'].get('portrait', {}).get('id') == draft['input'].get('portrait', {}).get('id')
    reused = {k: deepcopy(v) for k, v in state['stages'].items() if (same_audio and k in {'tts', 'asr'}) or (same_avatar and k == 'avatar')}
    for stage, value in reused.items():
        value.setdefault('intent_identity', 'call_' + hashlib.sha256((old['id']+':'+stage).encode()).hexdigest()[:32])
    prepared = dict(request['prepared'])
    if same_audio and state.get('prepared', {}).get('audio_path'):
        owned(state['prepared']['audio_path'])
        prepared.update({k: state['prepared'][k] for k in ('audio_path', 'audio_file', 'duration')})
    # Deduplicate the same durable intent across every historical local attempt.
    commitments = {}
    def intent_key(stage):
        return json.dumps(stage.get('intent') or stage.get('intent_identity') or stage.get('job', {}).get('id'), sort_keys=True)
    for member in members:
        path = folder_for(member['frozen_request']) / 'gateway-state.json'
        if not path.is_file(): continue
        for name, raw in json.loads(path.read_text()).get('stages', {}).items():
            stage = dict(raw)
            if not (stage.get('intent') or stage.get('intent_identity') or stage.get('job')):
                stage['intent_identity'] = 'call_' + hashlib.sha256((member['frozen_request']['id']+':'+name).encode()).hexdigest()[:32]
            key = intent_key(stage)
            commitments[key] = max(commitments.get(key, 0), int(stage['quote']['max_charge_micros']))
    copied = {intent_key(v) for v in reused.values()}
    inherited = sum(amount for key, amount in commitments.items() if key not in copied)
    committed = inherited + sum(int(v['quote']['max_charge_micros']) for v in reused.values())
    new_known = sum(int(v['max_charge_micros']) for k, v in request['quotes'].items() if k not in reused)
    if committed + new_known > request['max_charge_micros']:
        raise WorkError('历史原调用及后续报价合计超过本次总上限；已完成内容保留，请调整总上限后继续', 'budget_exceeded')
    request = {**request, 'inherited_charge_micros': inherited,
               'continuation': {'previous_job_id': previous_id, 'creation_id': members[0]['creation_id']}}
    receipt = target / 'continuation.json'
    binding = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    if receipt.is_file():
        if json.loads(receipt.read_text())['fingerprint'] != binding: raise WorkError('恢复请求已冻结，请继续原提交')
        return request
    target.mkdir(parents=True, exist_ok=True)
    atomic_private(target / 'gateway-state.json', {'prepared': prepared, 'stages': reused})
    for name in ('local-asr.json',):
        if same_audio and request.get('asr') == old.get('asr') and (source / name).is_file(): shutil.copy2(source / name, target / name)
    if same_avatar and (source / 'avatar-source.mp4').is_file(): shutil.copy2(owned(source / 'avatar-source.mp4'), target / 'avatar-source.mp4')
    # A presentation-only change retains the actual frame analysis and scene assets.
    plan_path = source / 'storyboard.json'
    if same_audio and draft['text'] == before.get('text') and draft['input'].get('ai') == before['input'].get('ai') and plan_path.is_file():
        plan = json.loads(plan_path.read_text())
        if plan.get('draft_fingerprint') != hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(): raise WorkError('原分镜与冻结内容不一致')
        if all(s.get('asset') for s in plan.get('scenes', [])):
            for scene in plan['scenes']:
                if sha(studio.asset(scene['asset']['id'], draft['id'])) != scene['asset_sha256']: raise WorkError('原分镜素材已改变')
            plan.update(draft_fingerprint=hashlib.sha256(json.dumps(draft, sort_keys=True).encode()).hexdigest(),
                        presentation_reuse={'parent_plan_sha256': sha(plan_path), 'source_job_id': previous_id})
            atomic_private(target / 'storyboard.json', plan)
    atomic_private(receipt, {'fingerprint': binding, 'previous_job_id': previous_id, 'reused_stages': list(reused), 'inherited_charge_micros': inherited})
    return request
