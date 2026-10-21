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


def prepare(root,fixture):
    config=motion.installed('motiongit-626-v0-2-29-open-beta');motion.new_instance(config,root)
    staging=root/'input-staging';staging.mkdir(exist_ok=True)
    old=Path(json.loads(fixture.read_text())['instance'])/'input-staging'
    for name in ['presenter.mp4','narration.wav']:shutil.copy2(old/name,staging/name)
    source=json.loads((old/'params.json').read_text())['timeline']
    value={'mode':'user-media','language':'zh','layout':'portrait','duration':source['duration'],
        'title':'数字人功能测试','presenterLabel':'海客测试','content':{},
        'scenes':[{'id':'B1','title':'数字人测试','duration':9.68,'intent':'neutral-emphasis',
            'basic':{'keyword':'数字人测试','explanation':'人物自然开口\n声音字幕同步'}},
            {'id':'B4','title':'成片检查','duration':source['duration']-9.68,'intent':'summary',
             'basic':{'summary':'成片检查','action':'验证播放、进度和下载'}}],
        'media':{'presenter':{'mode':'video','file':'presenter.mp4'},'voice':{'mode':'file','file':'narration.wav'},'music':{'mode':'none'}},
        'soundEffects':'native','captions':[{'start':c['s'],'end':c['e'],'text':c['text']} for c in source['captions']]}
    from jsonschema import Draft202012Validator
    Draft202012Validator(json.loads(Path(config['schema']).read_text())).validate(value)
    atomic_private(staging/'user.json',value)
    env={k:v for k,v in os.environ.items() if not any(s in k.upper() for s in ['API_KEY','API_SECRET','ACCESS_TOKEN'])}
    env['PATH']=str(Path(sys.executable).parent)+os.pathsep+env.get('PATH','')
    operations=[('compose',['--input',staging/'user.json','--out',staging/'ready.json']),
        ('check-params',['--input',staging/'ready.json']),('plan',['--input',staging/'ready.json','--out',root/'plan.json']),
        ('prepare',['--input',staging/'ready.json','--out',root/'project']),
        ('preview',['--instance',root/'project','--time','4','--out',root/'preview.png'])]
    for op,args in operations:
        result=subprocess.run(['node',config['helper'],'--offline','run',config['package'],'--instance',str(root),
            '--cache',config['cache'],op,*map(str,args)],env=env,capture_output=True,text=True,timeout=600)
        atomic_private(root/(op+'-receipt.json'),{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        print(op,result.returncode,flush=True)
        if result.returncode:return


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True)
    a=p.parse_args();prepare(a.root.resolve(),a.fixture)
