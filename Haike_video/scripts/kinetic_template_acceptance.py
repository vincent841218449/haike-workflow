"""Bounded local kinetic fixture: original cached media, no generation services."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backlot import studio_motiongit as motion
from backlot.studio import atomic_private
from backlot.work_catalog import sha


def prepare(root,fixture,timing_result,timing_receipt,tool_version):
    config=motion.installed('motiongit-626-v0-2-29-open-beta');motion.new_instance(config,root)
    staging=root/'input-staging';staging.mkdir(exist_ok=True)
    old=Path(json.loads(fixture.read_text())['instance'])/'input-staging'
    for name in ['presenter.mp4','narration.wav']:shutil.copy2(old/name,staging/name)
    source=json.loads((old/'params.json').read_text())['timeline']
    receipt=json.loads(timing_receipt.read_text())
    if receipt.get('fingerprint',{}).get('audio_sha256')!=sha(staging/'narration.wav'):
        raise ValueError('Actual ASR receipt must bind this exact unchanged narration')
    raw=json.loads(timing_result.read_text());cues=raw.get('segments',[])
    # This is the retained 19.6-second fixture, not a general production director.
    if len(cues)!=5 or source['duration']!=19.6:
        raise ValueError('This diagnostic requires the original five-cue 19.6-second ASR fixture')
    if [{k:c[k] for k in ('start','end','text')} for c in receipt['result']['segments']]!=[{k:c[k] for k in ('start','end','text')} for c in cues]:
        raise ValueError('Retained raw timing result differs from its actual ASR receipt')
    shutil.copy2(timing_result,staging/'actual-asr.json')
    shutil.copy2(timing_receipt,staging/'actual-asr-receipt.json')
    boundary=cues[2]['end']
    value={'mode':'user-media','language':'zh','layout':'portrait','duration':source['duration'],
        'title':'数字人功能测试','presenterLabel':'海客测试','content':{},
        'scenes':[{'id':'B1','title':'数字人测试','duration':boundary,'intent':'neutral-emphasis',
            'basic':{'keyword':'数字人测试','explanation':'人物自然开口\n声音字幕同步'}},
            {'id':'B4','title':'成片检查','duration':source['duration']-boundary,'intent':'summary',
             'basic':{'summary':'成片检查','action':'验证播放、进度和下载'}}],
        'media':{'presenter':{'mode':'video','file':'presenter.mp4'},'voice':{'mode':'file','file':'narration.wav'},'music':{'mode':'none'}},
        'soundEffects':'native','captions':[{k:c[k] for k in ('start','end','text')} for c in cues],
        'captionPosition':{'bottomRatio':.42,'leftRatio':.08,'rightRatio':.16},
        'captionTimingEvidence':{'file':'actual-asr.json','sha256':sha(staging/'actual-asr.json'),
            'sourceMediaSha256':sha(staging/'narration.wav'),'method':'asr-sentence',
            'tool':{'name':'faster-whisper','version':tool_version},'clock':'bound-narration-seconds'},
        'narrationMap':[]}
    for shot,indices in enumerate(([0,1,2],[3,4])):
        value['narrationMap'].append({'shot':shot,'start':0 if shot==0 else boundary,
            'end':boundary if shot==0 else source['duration'],
            'spokenText':''.join(cues[j]['text'] for j in indices),
            'purpose':'neutral-emphasis' if shot==0 else 'summary',
            'timingSource':'provided-captions','captionIndices':indices,
            'beats':[{'at':cues[j]['start'],'until':cues[j]['end'],'spokenText':cues[j]['text'],
                      'timing':'sentence','target':'headline'} for j in indices]})
    from jsonschema import Draft202012Validator
    Draft202012Validator(json.loads(Path(config['schema']).read_text())).validate(value)
    atomic_private(staging/'user.json',value)
    env={k:v for k,v in os.environ.items() if not any(s in k.upper() for s in ['API_KEY','API_SECRET','ACCESS_TOKEN'])}
    env['PATH']=str(Path(sys.executable).parent)+os.pathsep+env.get('PATH','')
    operations=[('check-params',['--input',staging/'user.json']),
        ('plan',['--input',staging/'user.json','--out',root/'plan.json']),
        ('prepare',['--input',staging/'user.json','--out',root/'project'])]+[
        ('preview',['--instance',root/'project','--time',str(t),'--out',root/f'preview-{t}.png']) for t in [4,10,16]]
    for index,(op,args) in enumerate(operations):
        result=subprocess.run(['node',config['helper'],'--offline','run',config['package'],'--instance',str(root),
            '--cache',config['cache'],op,*map(str,args)],env=env,capture_output=True,text=True,timeout=600)
        atomic_private(root/(str(index)+'-'+op+'-receipt.json'),{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        print(op,result.returncode,flush=True)
        if result.returncode:return


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--timing-result',type=Path,required=True,help='Unmodified actual local ASR worker JSON')
    p.add_argument('--timing-receipt',type=Path,required=True,help='Retained actual local ASR cache receipt')
    p.add_argument('--asr-tool-version',required=True,help='Actual version of the invoked faster-whisper environment')
    a=p.parse_args();prepare(a.root.resolve(),a.fixture,a.timing_result,a.timing_receipt,a.asr_tool_version)
