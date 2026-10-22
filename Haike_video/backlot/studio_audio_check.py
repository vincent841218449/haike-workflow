"""Uploaded-audio content preflight and read-only generated-audio recovery."""
from __future__ import annotations
import difflib
import hashlib
import json
import math
import re
import threading
from decimal import Decimal, InvalidOperation
from pathlib import Path
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha

VERSION = 'audio-content-check/2'
_guard = threading.Lock()
_locks = {}
_digits = dict(zip('零〇一二两三四五六七八九', [0,0,1,2,2,3,4,5,6,7,8,9]))


def _number(raw):
    try:
        if not any(x in raw for x in '十百千万亿'):
            value = Decimal(''.join(str(_digits.get(c,c)) for c in raw.replace('点','.')))
        else:
            for large,scale in (('亿',100000000),('万',10000)):
                if large in raw:
                    left,right=raw.rsplit(large,1)
                    return format((Decimal(_number(left or '一'))*scale+Decimal(_number(right or '零'))).normalize(),'f')
            total = section = number = Decimal(0)
            token = ''
            for c in raw:
                if c not in '十百千万亿': token += str(_digits.get(c,c)).replace('点','.'); continue
                number = Decimal(token or '0'); token = ''
                unit = Decimal({'十':10,'百':100,'千':1000,'万':10000,'亿':100000000}[c])
                if unit < 10000: section += (number or 1)*unit
                else: total += (section+number)*unit; section=Decimal(0)
            value = total+section+Decimal(token or '0')
        return format(value.normalize(),'f')
    except (InvalidOperation, ValueError): return raw


def normalized(text):
    text = re.sub(r'(\d+(?:\.\d+)?)\s*[%％]',r'百分之\1',text)
    text = text.replace('×','乘').replace('✕','乘')
    text = re.sub(r'[0-9零〇一二两三四五六七八九十百千万亿]+(?:[.点][0-9零〇一二两三四五六七八九]+)?', lambda m:_number(m[0]), text.casefold())
    # Punctuation between two numbers is a boundary, never concatenation (7、24 != 724).
    text = re.sub(r'(?<=\d)[，,、；;：:\s]+(?=\d)','/',text)
    text = re.sub(r'(?<!\d)\.|\.(?!\d)','',text)
    return re.sub(r'[^\w\u4e00-\u9fff./]','',text)


def assess(text, cues):
    spoken=''.join(c.get('text','') for c in cues)
    written, heard=normalized(text), normalized(spoken)
    matcher=difflib.SequenceMatcher(None,written,heard,autojunk=False)
    matched=sum(b.size for b in matcher.get_matching_blocks())
    differences=[]
    spans=[];prefix=''
    for cue in cues:
        start=len(normalized(prefix));prefix+=cue.get('text','')
        spans.append((start,len(normalized(prefix)),cue.get('startMs')))
    for op,a,b,c,d in matcher.get_opcodes():
        if op=='equal': continue
        observed=next((at for start,end,at in spans if start<=c<end),None)
        differences.append({'kind':op,'written':written[a:b][:120],'spoken':heard[c:d][:120],
                            'start_ms':observed})
    # “一整个小区” is whole-area emphasis, not an amount/quota. ASR may
    # render its unstressed yi as 以, or omit it. Keep actual counts, money,
    # dates and units strict (including “一个名额” and “两个小区”).
    numbers=lambda s:[m[0] for m in re.finditer(r'\d+(?:[./]\d+)?',s)
                      if not (m[0]=='1' and s[m.end():].startswith('整个'))]
    critical=[]
    if numbers(written)!=numbers(heard): critical.append({'kind':'number','written':numbers(written),'spoken':numbers(heard)})
    negative=lambda s:len(re.findall(r'没有|不会|不能|不可|不要|不得|不是|不|没|未|无',s))
    if negative(written)!=negative(heard) or any(negative(d['written']) or negative(d['spoken']) for d in differences):
        critical.append({'kind':'negation','written':negative(written),'spoken':negative(heard)})
    units=lambda s:re.findall(r'百分之|\d+(?:\.\d+)?(?:美元|人民币|元|年|个月|月|天|日|小时|分钟|秒|克|公斤|千克|米|公里)',s)
    if units(written)!=units(heard): critical.append({'kind':'unit','written':units(written),'spoken':units(heard)})
    coverage=matched/max(1,len(written)); precision=matched/max(1,len(heard)); similarity=matcher.ratio()
    missing=max((len(d['written']) for d in differences if d['kind']=='delete'),default=0)
    probabilities=[c['confidence'] for c in cues if isinstance(c.get('confidence'),(int,float))]
    uncertain=bool(probabilities) and (not all(map(math.isfinite,probabilities)) or sum(probabilities)/len(probabilities)<.55)
    if not written or not heard or similarity<.7 or (missing>=16 and coverage<.9): status='blocked'
    elif critical or similarity<.9 or min(coverage,precision)<.9 or uncertain: status='review'
    else: status='passed'
    return {'schema':VERSION,'status':status,'script_chars':len(text),'recognized_chars':len(spoken),
            'script_excerpt':text[:160],'recognized_excerpt':spoken[:160], 'recognized_text':spoken,
            'similarity':round(similarity,4),'coverage':round(coverage,4),'precision':round(precision,4),
            'differences':differences[:12],'critical_differences':critical,
            'message':{'passed':'录音与文案已匹配','review':'录音内容需要核对，请查看关键差异；尚未提交数字人生成',
                       'blocked':'录音与文案不一致，请核对录音，或按文案配音；尚未提交数字人生成'}[status]}


def generated_clock_ready(project, request):
    """Read-only recovery gate: original generated audio + bound offline clock.

    No quoting, transcribing, downloading or generation occurs here. Re-entering
    the same producer retains its TTS intent and prepared audio checkpoint.
    Recognition content is not an approval gate for script-driven TTS.
    """
    try:
        draft=request.get('draft') or {}
        if draft.get('input',{}).get('soundMode')!='voice': return False
        name=request.get('render_id')
        if not isinstance(name,str) or Path(name).name!=name: return False
        project=Path(project).resolve();folder=project/'renders'/name
        if folder.is_symlink() or not folder.resolve().is_relative_to(project): return False
        state=json.loads((folder/'gateway-state.json').read_text())
        prepared=state['prepared'];audio=Path(prepared['audio_path'])
        if request.get('narration_reuse'):
            from backlot.studio import Studio
            from backlot.studio_narration_reuse import verify
            verify(Studio(project.parent),draft,request['narration_reuse'],audio)
            owner=project
        else:
            tts=state.get('stages',{}).get('tts',{})
            q=tts.get('quote') or {};original=request.get('quotes',{}).get('tts') or {}
            if (tts.get('job',{}).get('status')!='succeeded' or q.get('execution_route')!='local-system-voice'
                or any(q.get(k)!=original.get(k) for k in ('id','model','execution_route'))): return False
            owner=folder.resolve()
        if audio.is_symlink() or not audio.resolve().is_relative_to(owner) or not audio.is_file(): return False
        saved=json.loads((folder/'local-asr.json').read_text())
        if (request.get('asr',{}).get('provider')!='local-whisper'
            or saved.get('fingerprint')!={'audio_sha256':sha(audio),'engine_identity':request['asr']['identity']}): return False
        from backlot.studio_asr import validate_result
        validate_result(saved['result'],prepared['duration'])
        return True
    except (OSError,ValueError,KeyError,TypeError,WorkError):
        return False


def _binding(studio,draft):
    from backlot.studio_asr import snapshot
    from backlot.studio_avatar import key_identity
    if draft['input'].get('soundMode')!='audio': raise WorkError('当前使用音色配音，无需核对上传录音')
    audio=studio.asset((draft['input'].get('audio') or {}).get('id'),draft['id'])
    engine=snapshot(studio)
    return {'schema':VERSION,'audio_sha256':sha(audio),'text_sha256':hashlib.sha256(draft['text'].encode()).hexdigest(),
            'engine':engine,'account':key_identity(studio)},audio


def _paths(studio,draft,binding):
    root=studio.projects_root/draft['id']/'assets/audio-checks'
    digest=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()
    return root,root/(digest+'.json')


def saved_check(studio,draft):
    try:
        binding,_=_binding(studio,draft);_,path=_paths(studio,draft,binding)
        data=json.loads(path.read_text())
        return data if data['binding']==binding else None
    except (OSError,ValueError,KeyError,WorkError): return None


def check_audio(studio,draft):
    from backlot import studio_asr
    from backlot.studio_avatar import prepare_audio, clock_captions
    from lib.bailian_speech import operation_lock, BailianSpeechError
    binding,audio=_binding(studio,draft);root,path=_paths(studio,draft,binding)
    with _guard: lock=_locks.setdefault(str(root),threading.Lock())
    with lock:
        cached=saved_check(studio,draft)
        if cached: return cached
        if binding['engine']['provider']!='local-whisper':
            raise WorkError('制作前核对需要本地字幕服务，请管理员启用；未提交收费调用','unavailable')
        root.mkdir(parents=True,exist_ok=True)
        clock_id=hashlib.sha256(json.dumps([binding['audio_sha256'],binding['engine']],sort_keys=True).encode()).hexdigest()
        clock=root/clock_id;clock.mkdir(exist_ok=True)
        try:
            with operation_lock(clock/'check.lock'):
                canonical=clock/'narration.wav'
                clock_receipt=clock/'clock.json'
                if clock_receipt.is_file():
                    cached_clock=json.loads(clock_receipt.read_text())
                    if not canonical.is_file() or sha(canonical)!=cached_clock['canonical_sha256']:
                        raise WorkError('核对音轨已改变，请管理员恢复原文件；未提交收费调用','audio_check_stale')
                    duration,result=cached_clock['duration'],cached_clock['result']
                else:
                    duration=prepare_audio(audio,canonical)
                    result=studio_asr.transcribe(studio,binding['engine'],canonical,clock,duration)
                    atomic_private(clock_receipt,{'duration':duration,'result':result,'canonical_sha256':sha(canonical)})
                cues=clock_captions(result,duration)
                report=assess(draft['text'],cues)
                # One local retry, independent of the expected script, only for uncertain recognition.
                if report['status']=='review' and not report['critical_differences']:
                    retry=studio_asr.recheck(studio,binding['engine'],canonical,clock,duration)
                    if retry:
                        other=assess(draft['text'],clock_captions(retry,duration))
                        if other['status']=='passed':
                            report={**other,'recognition':'local-recheck'}
                            # Preserve both recognitions; production must use the clock that passed.
                            atomic_private(clock_receipt,{'duration':duration,'result':result,'rechecked_result':retry,
                                           'canonical_sha256':sha(canonical)})
                    report['local_recheck_attempted']=True
                report.update(binding=binding,id=path.stem,audio_id=draft['input']['audio']['id'],
                              duration_seconds=duration,draft_revision=draft['revision'],charge_micros=0,
                              clock_folder=clock.name)
                if _binding(studio,draft)[0]!=binding:
                    raise WorkError('核对期间录音或引擎已改变，请重新核对；未提交收费调用','audio_check_stale')
                atomic_private(path,report)
        except BailianSpeechError:
            raise WorkError('这份录音正在核对，请稍后重试；未提交收费调用','conflict') from None
        return report


def require_pass(studio,draft,report):
    binding,_=_binding(studio,draft)
    saved=saved_check(studio,draft)
    if not report or report.get('binding')!=binding or not saved or saved['id']!=report.get('id'):
        raise WorkError('文案、录音或字幕引擎已改变，请重新核对；未提交收费调用','audio_check_stale')
    if saved['status']!='passed':
        raise WorkError(saved['message'],'audio_script_mismatch' if saved['status']=='blocked' else 'audio_check_review')


def production_clock(studio,draft,report,audio,duration):
    """Reuse verified free recognition, including its bounded recheck, before avatar spending."""
    from backlot.studio_asr import verify_engine,validate_result
    require_pass(studio,draft,report)
    verify_engine(studio,report['binding']['engine'])
    root,_=_paths(studio,draft,report['binding'])
    clock=json.loads((root/report['clock_folder']/'clock.json').read_text())
    if sha(Path(audio))!=clock['canonical_sha256'] or abs(duration-clock['duration'])>.001:
        raise WorkError('制作音轨与已核对录音不一致，请重新核对；未提交新调用','audio_check_stale')
    result=clock['rechecked_result'] if report.get('recognition')=='local-recheck' else clock['result']
    return validate_result(result,duration)
