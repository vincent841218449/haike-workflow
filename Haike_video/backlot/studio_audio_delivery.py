"""Measure and normalize an encoded local delivery, preserving video packets."""
import json
from pathlib import Path
import shutil
import subprocess

from backlot.studio import atomic_private
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkError, sha
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def measure(path):
    ffmpeg,_=resolve_ffmpeg_pair()
    result=subprocess.run([ffmpeg,'-hide_banner','-i',str(path),'-af',
        'loudnorm=I=-15.5:TP=-1.2:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True,timeout=180)
    try:
        start=result.stderr.rfind('{');value=json.loads(result.stderr[start:result.stderr.find('}',start)+1])
        if result.returncode:raise ValueError()
        return value
    except (ValueError,KeyError):raise WorkError('成片声音测量失败，原视频已保留','unavailable') from None


def normalize(source,target):
    source,target=Path(source),Path(target)
    measured=measure(source);changed=not (-16<=float(measured['input_i'])<=-15 and float(measured['input_tp'])<=-.5)
    if changed:
        ffmpeg,_=resolve_ffmpeg_pair();duration=float(media_probe(source)['video']['duration'])
        graph='loudnorm=I=-15.5:TP=-1.2:LRA=9:linear=true:print_format=json'
        for option,key in [('measured_I','input_i'),('measured_TP','input_tp'),('measured_LRA','input_lra'),('measured_thresh','input_thresh'),('offset','target_offset')]:
            graph+=':'+option+'='+str(float(measured[key]))
        result=subprocess.run([ffmpeg,'-v','error','-y','-i',str(source),'-map','0:v:0','-map','0:a:0',
            '-c:v','copy','-af',graph,'-ar','48000','-c:a','aac','-b:a','192k','-t',str(duration),str(target)],capture_output=True,timeout=180)
        if result.returncode:raise WorkError('成片声音归一化失败，原视频已保留','unavailable')
    else:shutil.copy2(source,target)
    actual=measure(target)
    if not -16.2<=float(actual['input_i'])<=-14.8 or float(actual['input_tp'])>-.5:
        raise WorkError('最终编码响度或峰值仍未通过，原声音与视频已保留','unavailable')
    receipt={'schema':'haike-delivery-audio/1','source_sha256':sha(source),'output_sha256':sha(target),
        'input':measured,'encoded_output':actual,'normalized':changed,'target_lufs':-15.5,'target_true_peak':-1.2,
        'video':'stream-copy; no frame re-encoding','speech_speed':1,'listened':False,'paid_calls':0}
    atomic_private(target.with_suffix('.audio-qa.json'),receipt)
    return receipt
