"""Local AI-app producer with frozen inputs, segment checkpoints and real receipts.

Only newly frozen requests opt in. Previously accepted gateway calls continue
through their original SDK; changing the local default never migrates a paid job.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
import wave
from array import array
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

from backlot.studio import atomic_private
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkError, sha

PROFILE_PATH = Path(__file__).resolve().parents[1] / 'config/runninghub/infinitetalk_ai_app_2006270540499128322.json'


def configuration(studio):
    from backlot.ai_text import _read_env_file, _effective_value
    path = studio.private / 'haike-api/avatar.local.json'
    try: options = json.loads(path.read_text())
    except FileNotFoundError: options = {}
    except (ValueError, OSError): raise WorkError('本地数字人配置损坏，请恢复原配置') from None
    enabled = options.get('enabled') is True
    mode = options.get('billing_mode', 'provider_default')
    if mode not in {'provider_default', 'rh_coins'}: raise WorkError('本地数字人扣费方式无效')
    _, values = _read_env_file(studio.projects_root.parent / '.env.secrets.local')
    keys = {name:_effective_value(name, values) for name in ('RUNNINGHUB_API_KEY','RUNNINGHUB_COINS_API_KEY')}
    key = keys['RUNNINGHUB_COINS_API_KEY' if mode == 'rh_coins' else 'RUNNINGHUB_API_KEY']
    profile = json.loads(PROFILE_PATH.read_text())
    def identity(value): return hashlib.sha256(json.dumps(['https://www.runninghub.cn',value]).encode()).hexdigest()
    return {'enabled':enabled, 'ready':enabled and bool(key), 'key':key, 'identity':identity(key), 'profile':profile,
            'billing_mode':mode, 'credentials':{identity(value):value for value in keys.values() if value}}


def execution_key(config, execution):
    """Resolve the frozen credential, independently of the current default."""
    key = config.get('credentials',{}).get(execution.get('identity'))
    if not key and execution.get('identity') == config['identity']: key = config['key']
    if not key: raise WorkError('原数字人凭据不可用，请恢复原密钥；不会换密钥重提原请求')
    return key


def snapshot(studio):
    c = configuration(studio)
    if not c['enabled']: return None
    if not c['ready']: raise WorkError('请先配置本机 RunningHub 会员密钥' if c['billing_mode']=='rh_coins' else '新数字人应用尚未配置本机 RunningHub 密钥，已保留文案和素材')
    return {'route':'local-runninghub-ai-app', 'identity':c['identity'], 'profile':c['profile'],
            'profile_sha256':hashlib.sha256(json.dumps(c['profile'],sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'billing_policy':'actual_usage', 'billing_source':'local-provider', 'billing_mode':c['billing_mode'],
            'billing_notice':('数字人使用会员密钥，按 RunningHub 实际 RH 币消耗记录；不自动切回人民币钱包。' if c['billing_mode']=='rh_coins'
                              else '数字人按 RunningHub 实际用量结算；RH币与钱包金额分别记录，不按估价重复扣款。')}


def public_status(studio):
    c=configuration(studio)
    return {'enabled':c['enabled'],'ready':c['ready'],'name':c['profile']['name'],
            'app_id':c['profile']['app_id'],'instance_type':c['profile']['instance_type'],
            'max_segment_seconds':c['profile']['max_segment_frames']/25,
            'billing_source':'local-provider','billing_policy':'actual_usage','billing_mode':c['billing_mode']}


def verify_execution(studio, execution):
    c=configuration(studio)
    profile=execution.get('profile') or {}
    digest=hashlib.sha256(json.dumps(profile,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if execution.get('profile_sha256')!=digest or profile.get('app_id')!='2006270540499128322' or profile.get('base_url')!='https://www.runninghub.cn' or execution.get('billing_mode','provider_default') not in {'provider_default','rh_coins'}:
        raise WorkError('数字人配置或凭据已改变，请恢复原配置继续原任务')
    execution_key(c, execution)


def validate_submission_reissue(state, authorization, state_sha256):
    """Bind one human authorization to one exact, still unknown submission."""
    execution=authorization.get('execution') or {}
    if (not authorization.get('approval_ref') or type(authorization.get('chunk_index')) is not int
        or authorization.get('expected_state_sha256')!=state_sha256
        or authorization.get('state_id')!=state.get('id')
        or execution.get('billing_mode')!='rh_coins'
        or execution.get('profile')!=(state.get('execution') or {}).get('profile')
        or state.get('submission_reissues') or state.get('status')!='submission_unknown'
        or state.get('output_sha256')):
        raise WorkError('原未知请求或重提授权已改变，未提交新的收费调用')
    chunks=state.get('chunks',[])
    pending=[c for c in chunks if c.get('status')!='succeeded']
    if (not pending or pending[0].get('index')!=authorization['chunk_index']
        or pending[0].get('status')!='submission_unknown'
        or any(c.get('status')!='queued' or c.get('task_id') for c in pending[1:])
        or any(pending[0].get(k) for k in ('task_id','results','video_file','video_sha256'))):
        raise WorkError('原分段已有任务号或结果，不能按未知请求重新生成')
    return chunks.index(pending[0])


def _apply_submission_reissue(state, authorization, path):
    """Journal before submit; replaying consent never resets an accepted attempt."""
    existing=state.get('submission_reissues',[])
    if existing:
        if len(existing)==1 and existing[0]['authorization']==authorization: return False
        raise WorkError('本任务已使用一次未知分段重提授权，未再次提交')
    position=validate_submission_reissue(state,authorization,sha(path))
    original=state['chunks'][position]
    archived={**original,'execution':original.get('execution') or state['execution'],
              'replaced_by_approval_ref':authorization['approval_ref']}
    state.setdefault('unknown_attempts',[]).append(archived)
    state['chunks'][position]={k:original[k] for k in ('index','start_frame','end_frame')}
    state['chunks'][position].update(status='queued',execution=authorization['execution'],
                                    reissue_approval_ref=authorization['approval_ref'])
    state['submission_reissues']=[{'authorization':authorization,'applied_at':datetime.now(timezone.utc).isoformat()}]
    state.update(status='running',message='已记录一次RH币重提授权，原未知请求及成功片段保留')
    return True


def frame_segments(total_frames, cues, maximum=1125):
    """Prefer sentence ends; every sample and every frame belongs to one segment."""
    if type(total_frames) is not int or total_frames < 1 or not 1 <= maximum <= 1250:
        raise WorkError('数字人分段时钟无效')
    boundaries = sorted({round(c['endMs'] / 1000 * 25) for c in cues if isinstance(c.get('endMs'),(int,float))})
    result, start = [], 0
    while start < total_frames:
        end = min(start + maximum,total_frames)
        if end < total_frames:
            choices = [n for n in boundaries if start + min(750,maximum) <= n <= end]
            if choices: end = choices[-1]
        result.append({'start_frame':start,'end_frame':end})
        start = end
    return result


def _split_audio(audio, path, start, end):
    with wave.open(str(audio),'rb') as source:
        if source.getparams()[:3] != (1,2,24000): raise WorkError('数字人需要24kHz单声道PCM16主音轨')
        source.setpos(start * 960)
        samples = source.readframes((end-start)*960)
        if len(samples) != (end-start)*960*2: raise WorkError('数字人分段超出原音轨，不会补词或截断原文')
        with wave.open(str(path),'wb') as target:
            target.setnchannels(1); target.setsampwidth(2); target.setframerate(24000)
            target.writeframes(samples)


def long_failure_recoverable(state):
    """One bounded recovery for a confirmed long-running failure, never pending.

    805 alone does not prove a timeout. Combined with 55+ minutes of runtime,
    shorter remaining inputs are a conservative recovery with the same app and
    quality. Keep the failed request and unknown billing; never call it free.
    """
    if state.get('recovery') or state.get('status') != 'failed': return False
    chunks=state.get('chunks',[])
    failed=[c for c in chunks if c.get('status')=='failed']
    if len(failed)!=1: return False
    chunk=failed[0]
    if not chunk.get('task_id') or str(chunk.get('error_code'))!='805': return False
    if chunk['end_frame']-chunk['start_frame']<=625: return False
    if any(c is not chunk and c.get('status')!='succeeded'
           and (c.get('status')!='queued' or c.get('task_id')) for c in chunks): return False
    try:
        elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(chunk['submitted_at'])).total_seconds()
    except (KeyError,TypeError,ValueError): return False
    return elapsed>=3300


def _shorten_failed_inputs(state, cache, audio, cues):
    if not long_failure_recoverable(state): return False
    original=state['chunks']
    if (original[0]['start_frame']!=0 or original[-1]['end_frame']!=state['total_frames']
        or any(a['end_frame']!=b['start_frame'] for a,b in zip(original,original[1:]))):
        raise WorkError('原数字人分段时钟不完整，未提交恢复调用')
    chunks=[];index=max(c['index'] for c in original)+1
    for chunk in original:
        if chunk['status']=='succeeded' or chunk['end_frame']-chunk['start_frame']<=625:
            chunks.append(chunk);continue
        start,end=chunk['start_frame'],chunk['end_frame']
        count=(end-start+624)//625
        maximum=(end-start+count-1)//count
        local_cues=[{'endMs':c['endMs']-start*40} for c in cues]
        for part in frame_segments(end-start,local_cues,maximum):
            new={'index':index,'status':'queued','start_frame':start+part['start_frame'],
                 'end_frame':start+part['end_frame']}
            _split_audio(audio,cache/f'audio-{index:03d}.wav',new['start_frame'],new['end_frame'])
            chunks.append(new);index+=1
    failed=[c for c in original if c['status']=='failed']
    state.update(chunks=chunks,failed_attempts=[*state.get('failed_attempts',[]),*failed],
        recovery={'reason':'terminal_805_after_55m','at':datetime.now(timezone.utc).isoformat(),
                  'max_segment_frames':625,'previous_chunks':original},status='running',
        message='原数字人分段已明确失败，已保留原记录并自动改为短分段继续；原配音与已完成片段复用')
    return True


def _reference_correlation(path, reference, frames):
    """Verify the entire original audio at zero offset before trimming a tail."""
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg,_=resolve_ffmpeg_pair()
    count=frames*960
    try:
        with wave.open(str(reference),'rb') as source:
            if source.getparams()[:3]!=(1,2,24000) or source.getnframes()!=count:
                raise WorkError('分段原音轨时钟不一致，未接受供应商额外时长')
            original=source.readframes(count)
        decoded=subprocess.run([ffmpeg,'-v','error','-i',str(path),'-vn','-t',str(frames/25),
                                '-ac','1','-ar','24000','-f','s16le','-'],capture_output=True,timeout=60)
    except (OSError,wave.Error,subprocess.SubprocessError):
        raise WorkError('供应商视频无法核对原音轨，已保留原结果') from None
    if decoded.returncode or len(decoded.stdout)!=len(original):
        raise WorkError('供应商视频缺少完整原音轨，已保留原结果')
    a=array('h');a.frombytes(original)
    b=array('h');b.frombytes(decoded.stdout)
    if sys.byteorder!='little': a.byteswap();b.byteswap()
    def correlation(x,y):
        aa=sum(v*v for v in x);bb=sum(v*v for v in y)
        return sum(u*v for u,v in zip(x,y))/math.sqrt(aa*bb) if aa and bb else 0
    score=correlation(a,b)
    # Whole-track similarity alone can conceal a local lead-in or lost ending.
    quarters=[correlation(a[start:end],b[start:end]) for start,end in
              [(i*count//4,(i+1)*count//4) for i in range(4)]
              if any(a[start:end])]
    if score<.98 or not quarters or min(quarters)<.95:
        raise WorkError('供应商额外时长无法与原音轨从开头完整对应，已保留原结果')
    return score


def _verify_clip(path, frames, reference=None, final_segment=False):
    info = media_probe(path)
    video = info.get('video')
    stream_duration=float(video.get('duration',info['duration'])) if video else 0
    if not video or abs(stream_duration-frames/25) > .5:
        extra=stream_duration-frames/25
        # Short terminal outputs can carry up to 2 seconds of provider tail.
        # This never relaxes ordinary segment timing or audio alignment.
        padding_limit=2.0 if final_segment and frames<=250 else 1.2
        if not video or reference is None or not .5<extra<=padding_limit+1e-6:
            raise WorkError('数字人分段结果与原语音时长不一致，已保留供应商原结果')
        score=_reference_correlation(path,reference,frames)
        info['tail_padding']={'seconds':round(extra,6),'audio_correlation':score,
                              'limit_seconds':padding_limit,'final_segment':final_segment,
                              'source_frames':frames,'policy':'original_audio_zero_offset'}
    return info


def _stitch(folder, state, audio, target):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    clips = []
    for chunk in state['chunks']:
        source = folder / chunk['video_file']
        if sha(source) != chunk['video_sha256']: raise WorkError('原数字人分段缓存已改变，请恢复原文件')
        path = folder / f"aligned-{chunk['index']:03d}.mp4"
        frames = chunk['end_frame']-chunk['start_frame']
        cmd = [ffmpeg,'-v','error','-y','-i',str(source),'-vf','fps=25,tpad=stop_mode=clone:stop_duration=1',
               '-frames:v',str(frames),'-an','-c:v','libx264','-pix_fmt','yuv420p',str(path)]
        r = subprocess.run(cmd,capture_output=True,timeout=180)
        if r.returncode: raise WorkError('数字人分段无法对齐，原结果已保留')
        clips.append(path)
    # File names are generated in this directory, never provider-controlled paths.
    listing = folder / 'concat.txt'
    listing.write_text(''.join(f"file '{p.name}'\n" for p in clips))
    temporary = folder / 'joined.mp4'
    duration = state['total_frames']/25
    r = subprocess.run([ffmpeg,'-v','error','-y','-f','concat','-safe','1','-i',str(listing),'-i',str(audio),
        '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-t',str(duration),'-movflags','+faststart',str(temporary)],capture_output=True,timeout=180)
    if r.returncode: raise WorkError('数字人分段拼接未完成，已生成片段全部保留')
    info = _verify_clip(temporary,state['total_frames'])
    if not info.get('audio'): raise WorkError('数字人拼接结果缺少主音轨')
    r = subprocess.run([ffmpeg,'-v','error','-i',str(temporary),'-f','null','-'],capture_output=True,timeout=180)
    if r.returncode: raise WorkError('数字人拼接结果解码未通过')
    temporary.replace(target)


def _advance(studio, execution, folder, audio, portrait, cues, *, on_progress=None, client, billing_execution=None, client_for_execution=None, submission_reissue=None):
    """Advance durable segments sequentially; a lost submit is never replayed."""
    from lib.bailian_speech import operation_lock
    from backlot.studio_avatar import download_result
    folder, audio, portrait = Path(folder), Path(audio), Path(portrait)
    cache = folder / 'avatar-app'; cache.mkdir(exist_ok=True)
    path = cache / 'state.json'
    target = folder / 'avatar-source.mp4'
    verify_execution(studio,execution)
    if billing_execution:
        verify_execution(studio,billing_execution)
        if billing_execution['profile']!=execution['profile']: raise WorkError('切换扣费方式不能改变原应用与制作参数')
    if any(not p.resolve().is_relative_to(studio.projects_root.resolve()) for p in (folder,audio,portrait)):
        raise WorkError('数字人输入不属于当前本地项目')
    with operation_lock(cache / 'state.lock'):
        duration = media_probe(audio)['duration']
        frames = round(duration*25)
        if not 0 < frames <= 3000: raise WorkError('数字人口播主音轨需要在120秒内')
        binding = {'execution':execution,'audio_sha256':sha(audio),'portrait_sha256':sha(portrait),'total_frames':frames}
        if path.is_file():
            state = json.loads(path.read_text())
            if any(state[k] != v for k,v in binding.items()): raise WorkError('原数字人输入已改变，未提交新的收费调用')
        else:
            chunks = frame_segments(frames,cues,execution['profile']['max_segment_frames'])
            state = {**binding,'id':'localavatar-'+uuid4().hex,'status':'queued','chunks':[dict(c,index=i,status='queued') for i,c in enumerate(chunks)]}
            for c in state['chunks']:
                _split_audio(audio,cache/f"audio-{c['index']:03d}.wav",c['start_frame'],c['end_frame'])
            atomic_private(path,state)
        def save(): atomic_private(path,state)
        if submission_reissue:
            verify_execution(studio,submission_reissue.get('execution') or {})
            if billing_execution!=submission_reissue.get('execution'):
                raise WorkError('未知分段重提必须使用已授权的RH币扣费配置')
            if _apply_submission_reissue(state,submission_reissue,path): save()
        def result():
            attempts=[*state.get('failed_attempts',[]),*state.get('unknown_attempts',[]),*state['chunks']]
            ids = [c['task_id'] for c in attempts if c.get('task_id')]
            current=next((c for c in state['chunks'] if c['status']!='succeeded'),None)
            current_id=current.get('task_id') if current is not None else ids[-1] if ids else None
            unknown = state['status'] == 'submission_unknown'
            receipts=[c['billing'] for c in attempts if c.get('billing')]
            known=len(receipts)==len(attempts) and all(any(r.get('provider_usage',{}).get(k) is not None for k in ('consume_money','consume_coins')) for r in receipts)
            return {'id':state['id'],
                    'status':state['status'], 'upstream_id':current_id, 'upstream_ids':ids,
                    'billing_source':'local-provider', 'cost_status':'provider_usage_recorded' if known else 'supplier_bill_pending',
                    'billing_policy':'actual_usage', 'billing_notice':execution['billing_notice'],
                    'usage_receipts':receipts,
                    'message':state.get('message'), 'media_artifact_available':state['status']=='succeeded',
                    'requires_reconciliation':unknown, 'result':{'video_path':str(target)} if state['status']=='succeeded' else None}
        if state['status']=='succeeded':
            if not target.is_file() or sha(target)!=state['output_sha256']: raise WorkError('数字人缓存缺失或已改变，不会重新付费生成')
            return result()
        for position,chunk in enumerate(state['chunks']):
            if chunk['status']=='succeeded': continue
            unknown_message=f'数字人第 {position+1}/{len(state["chunks"])} 段提交回执不明，需核对原请求；已完成片段保留，未重复提交'
            if chunk['status'] in {'submitting','submission_unknown'}:
                state.update(status='submission_unknown',message=unknown_message)
                chunk['status']='submission_unknown'; save(); return result()
            if chunk['status']=='failed' and not chunk.get('task_id'):
                state.update(status='failed',message='数字人应用未完成当前分段，已完成片段与原配音保留'); save(); return result()
            if billing_execution and chunk['status']=='queued' and not chunk.get('task_id'):
                if (chunk.get('execution') or execution)!=billing_execution:
                    if chunk.get('audio_file'):
                        chunk.setdefault('previous_uploads',[]).append({'audio_file':chunk.pop('audio_file'),
                            'identity':(chunk.get('execution') or execution)['identity']})
                    chunk['execution']=billing_execution;save()
            current_execution=chunk.get('execution') or execution
            verify_execution(studio,current_execution)
            if current_execution['profile']!=execution['profile']: raise WorkError('数字人分段参数与原应用不一致，未提交调用')
            transport=client_for_execution(current_execution) if client_for_execution else client
            if on_progress: on_progress(f"数字人分段 {position+1}/{len(state['chunks'])}：正在生成")
            if not chunk.get('task_id'):
                if hasattr(transport,'ensure_billing_mode'):
                    from tools.avatar.runninghub_avatar import RunningHubAvatarError
                    try: transport.ensure_billing_mode(current_execution.get('billing_mode','provider_default'))
                    except RunningHubAvatarError as exc: raise WorkError(str(exc),'unavailable') from None
                # Uploaded files may belong to the old key's namespace.
                if current_execution!=execution:
                    uploads=state.setdefault('credential_uploads',{}).setdefault(current_execution['identity'],{})
                else: uploads=state
                if not uploads.get('image_file'): uploads['image_file']=transport.upload(portrait); save()
                if not chunk.get('audio_file'):
                    chunk['audio_file']=transport.upload(cache/f"audio-{chunk['index']:03d}.wav"); save()
                if on_progress: on_progress(f"数字人分段 {position+1}/{len(state['chunks'])}：输入已就绪")
                chunk.update(status='submitting',submitted_at=datetime.now(timezone.utc).isoformat()); save()
                try:
                    receipt = transport.submit(uploads['image_file'],chunk['audio_file'])
                    if receipt.get('task_id'):
                        chunk.update(task_id=receipt['task_id'],status='running'); save()
                    chunk['submit_receipt']={'at':datetime.now(timezone.utc).isoformat(),
                        'http_status':receipt.get('http_status'),'status':receipt.get('status'),
                        'error_code':receipt.get('error_code'),'task_id':receipt.get('task_id')}
                    save()
                    if not chunk.get('task_id') and receipt['status']=='FAILED':
                        chunk.update(status='failed',error_code=receipt.get('error_code'))
                        message=('RunningHub 钱包余额不足，原配音和已完成分段保留' if str(receipt.get('error_code'))=='416'
                                 else '数字人应用拒绝请求，请检查本机密钥权限、应用及额度')
                        state.update(status='failed',message=message); save(); return result()
                    if not chunk.get('task_id'): raise ValueError('missing task id')
                except Exception as exc:
                    chunk['submission_diagnostic']={'phase':'submit','exception_type':type(exc).__name__,
                                                    'at':datetime.now(timezone.utc).isoformat()}
                    if chunk.get('task_id'):
                        state.update(status='running',message='数字人任务号已保留，系统将继续查询原请求');save();return result()
                    chunk['status']='submission_unknown'; state.update(status='submission_unknown',message=unknown_message); save(); return result()
            # Query failures retain the checkpointed task ID and only query again.
            try: queried=transport.poll(chunk['task_id'])
            except Exception:
                state.update(status='running',message='数字人原分段查询暂时中断，系统将继续查询'); save(); return result()
            if queried['task_id'] != chunk['task_id']: raise WorkError('数字人查询回执编号不一致，未关联其他任务')
            if queried.get('billing'): chunk['billing']=queried['billing']
            if queried['status'] in {'FAILED','FAIL','CANCELLED','CANCELED','ERROR'}:
                chunk.update(status='failed',error_code=queried.get('error_code'),provider_status=queried['status'],
                             failure_details=queried.get('failure_details',{}))
                code=str(queried.get('error_code') or '未提供')
                state.update(status='failed',message=f'RunningHub 数字人第 {position+1} 段生成失败（错误码 {code}），原配音和已完成分段保留')
                save()
                if queried['status'] in {'FAILED','FAIL','ERROR'} and _shorten_failed_inputs(state,cache,audio,cues):
                    save()
                return result()
            if queried['status'] not in {'SUCCESS','SUCCEEDED','COMPLETED'}:
                done=sum(c['status']=='succeeded' for c in state['chunks'])
                state.update(status='running',message=f"数字人第 {position+1}/{len(state['chunks'])} 段正在生成，已完成 {done} 段"); save(); return result()
            chunk['results']=queried['videos']; save()
            chunk['phase']='downloading'
            candidates=[]
            for i,video in enumerate(chunk['results']):
                candidate=cache/f"video-{chunk['index']:03d}-{i:02d}.mp4"
                reference=cache/f"audio-{chunk['index']:03d}.wav"
                frames=chunk['end_frame']-chunk['start_frame']
                try:
                    # Revalidate bytes previously rejected by an older timing
                    # contract before fetching the same paid result again.
                    if not candidate.is_file():
                        for archived in sorted(cache.glob(candidate.stem+'.invalid*.mp4')):
                            try: _verify_clip(archived,frames,reference,position==len(state['chunks'])-1)
                            except WorkError: continue
                            shutil.copyfile(archived,candidate);break
                    if not candidate.is_file(): download_result(video['url'],candidate)
                except WorkError as exc:
                    if exc.code != 'unavailable': raise
                    continue
                except OSError:
                    continue
                try: info=_verify_clip(candidate,frames,reference,position==len(state['chunks'])-1)
                except WorkError:
                    # Retain bad bytes, then retry the original paid result.
                    invalid=candidate.with_suffix('.invalid.mp4')
                    if invalid.exists(): invalid=candidate.with_suffix('.invalid-'+uuid4().hex[:8]+'.mp4')
                    candidate.replace(invalid)
                    continue
                candidates.append((info['video']['width']*info['video']['height'],candidate,info))
            if not candidates:
                chunk['download_failures']=chunk.get('download_failures',0)+1
                state.update(status='running',message=f"数字人第 {position+1} 段已生成，正在重新查询并下载原结果")
                save()
                if chunk['download_failures']>=3:
                    raise WorkError('数字人原结果连续三次下载或解码未通过，原任务号和片段保留；请修复下载连接后继续原任务', 'unavailable')
                return result()
            _,selected,info=max(candidates,key=lambda v:v[0])
            if info.get('tail_padding'): chunk['tail_padding']=info['tail_padding']
            chunk.update(status='succeeded',video_file=selected.name,video_sha256=sha(selected)); save()
        _stitch(cache,state,audio,target)
        state.update(status='succeeded',output_sha256=sha(target),message=None); save()
        return result()


def produce(studio, execution, folder, audio, portrait, cues, *, on_progress=None, client=None, billing_execution=None, submission_reissue=None):
    args=(studio,execution,folder,audio,portrait,cues)
    if client is not None:return _advance(*args,on_progress=on_progress,client=client,billing_execution=billing_execution,submission_reissue=submission_reissue)
    from contextlib import ExitStack
    from tools.avatar.runninghub_ai_app import RunningHubAIAppClient
    config=configuration(studio)
    with ExitStack() as stack:
        clients={}
        def transport(value):
            identity=(value['identity'],value['profile_sha256'])
            if identity not in clients:
                clients[identity]=stack.enter_context(RunningHubAIAppClient(execution_key(config,value),value['profile']))
            return clients[identity]
        return _advance(*args,on_progress=on_progress,client=None,billing_execution=billing_execution,client_for_execution=transport,submission_reissue=submission_reissue)
