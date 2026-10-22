"""Retain actual local alignment evidence for the unchanged user narration."""
import json
import os
from pathlib import Path
import subprocess
from backlot.studio import atomic_private
from backlot.studio_template_registry import digest
from backlot.work_catalog import WorkError,sha


def engine(studio):
    from backlot.studio_asr import configuration,status
    if not status(studio)['ready']:raise WorkError('本地字幕时间对齐环境尚未配置，尚未提交配音或数字人费用','unavailable')
    return configuration(studio)


def align(studio,audio,cues,folder):
    c=engine(studio);folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    worker=Path(__file__).resolve().parents[1]/'scripts/studio_alignment_worker.py'
    fingerprint=digest([sha(Path(audio)),cues,c,sha(worker)])
    receipt=folder/'alignment-receipt.json';output=folder/'alignment.json'
    if receipt.is_file():
        saved=json.loads(receipt.read_text())
        if saved['fingerprint']!=fingerprint or not output.is_file() or sha(output)!=saved['output_sha256']:
            raise WorkError('已保存的本地时间轴输入已改变，原声和旧结果保留','template_mismatch')
    else:
        atomic_private(folder/'source-cues.json',cues)
        env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false'}
        try:
            result=subprocess.run([c['python'],str(worker),'--model-dir',c['model_dir'],'--audio',str(audio),
                '--cues',str(folder/'source-cues.json'),'--output',str(output)],capture_output=True,env=env,timeout=600)
        except (OSError,subprocess.TimeoutExpired) as exc:
            (folder/'alignment-error.log').write_text(str(exc))
            raise WorkError('本地字幕时间轴暂未完成，原声已保留；可继续原任务，不会重新配音','unavailable') from exc
        if result.returncode:
            (folder/'alignment-error.log').write_bytes(result.stderr)
            raise WorkError('本地字幕时间轴尚未生成，原声已保留；未调用收费识别服务','template_incompatible')
        atomic_private(receipt,{'fingerprint':fingerprint,'output_sha256':sha(output),'source_audio_sha256':sha(Path(audio)),
            'worker_sha256':sha(worker),'generation_calls':0,'remote_calls':0})
    data=json.loads(output.read_text())
    if data.get('sourceMediaSha256')!=sha(Path(audio)) or len(data.get('segments',[]))!=len(cues):
        raise WorkError('本地时间轴未绑定当前完整原声','template_mismatch')
    return output,data
