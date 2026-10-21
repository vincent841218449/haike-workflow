"""Unpaid cached-media integration fixture for the three portrait adapters.

The director responses here are explicit test fixtures, not live model calls.
Actual source bindings, compilation, signed runner, previews and queue exports
are exercised. A test registry never enables a release on the live server.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backlot import studio_motiongit as motion,studio_template_execution as execution
from backlot.studio import Studio,atomic_private
from backlot.studio_template_auto import storyboard
from backlot.studio_storyboard import TrialRelay
from backlot.work_catalog import sha


def lines(text):
    # Technical Chinese fixture only; retain every source character.
    result=[]
    while text:
        limit=min(len(text),16)
        candidates=[i+1 for i,c in enumerate(text[:limit]) if c in '，。；：、,?？']
        at=candidates[-1] if candidates else limit
        result.append(text[:at]);text=text[at:]
    if len(result)==1:
        source=result[0];cuts=[i+1 for i,c in enumerate(source[:-1]) if c in '，。；：、,?？']
        if not cuts:raise ValueError('Fixture needs two complete phrase lines')
        at=min(cuts,key=lambda n:abs(n-len(source)/2));result=[source[:at],source[at:]]
    if len(result)>5:raise ValueError('Fixture exceeds the real control capacity')
    return result


def prepare(root,fixture_path,style):
    fixture=json.loads(fixture_path.read_text());old=Path(fixture['instance'])
    params=json.loads((old/'input-staging/params.json').read_text())['timeline']
    cues=[{'startMs':c['s']*1000,'endMs':c['e']*1000,'text':c['text'],'clock':'sentence'} for c in params['captions']]
    studio=Studio(root/style/'projects');cfg=motion.installed(style)
    d=studio.save_draft({'template_id':'avatar-safe-circle-v1','text':fixture['draft']['text'],'title':'缓存声画接入验证'})
    source=Studio(old.parents[3]);person=source.asset(fixture['draft']['input']['portrait']['id'],fixture['draft']['id'])
    if style.startswith('motiongit-626-'):
        import shutil
        destination=studio.private/'studio-asr/config.json';destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(__file__).resolve().parents[1]/'.backlot/studio-asr/config.json',destination)
    asset=studio.save_asset(d['id'],'portrait.jpg','image',person.read_bytes())
    d['input'].update(motion={'style':style,'layout':'portrait'},templateExecution='auto',templateRef=motion.template_ref(cfg),
        portrait=asset,ai={'enabled':True,'materials':[]},subtitles=True,music={'mode':'none'})
    folder=studio.projects_root/d['id']/'renders/studio-1';folder.mkdir(parents=True,exist_ok=True)
    execution.precheck(studio,d,folder);board=storyboard(studio,d,folder,params['duration'])
    rows=[]
    for i,(a,b) in enumerate([(0,1),(2,4),(5,6)]):
        text=''.join(c['text'] for c in cues[a:b+1])
        row={'control':'kinetic','variant':'wave','text':text,'from_cue':a,'to_cue':b,
             'props':{'lines':lines(text)},'anchors':[],'support':[text],'purpose':'neutral-emphasis'}
        if style.startswith('motiongit-614-'):
            if i==0:row.update(control='keyword',variant='slam',props={'word':'数字人功能测试','sub':['人物能否自然开口']})
            if i==1:row.update(control='quote',variant='card',props={'text':cues[a]['text'],'who':'口播原文'})
            if i==2:row['props']={'lines':['进度拖动','和文件下载，','让每一步','都有实际结果。']}
        rows.append(row)
    original=TrialRelay.call;calls=[]
    def fixture_response(self,key,payload):
        calls.append(key)
        if 'review' in key:return {'choices':[{'message':{'content':json.dumps({'approved':True,'issues':[]})}}]}
        if style.startswith('motiongit-626-'):
            selected={'scenes':[
                {'id':'B1','title':'数字人功能测试','from_cue':0,'to_cue':2,'purpose':'neutral-emphasis',
                 'basic':{'keyword':'数字人测试','explanation':'人物能否自然开口\n声音和字幕是否同步'},'support':[cues[0]['text']]},
                {'id':'B4','title':'成片检查','from_cue':3,'to_cue':6,'purpose':'summary',
                 'basic':{'summary':'成片检查','action':'验证播放、进度和下载'},'support':[cues[4]['text']]}]}
            return {'choices':[{'message':{'content':json.dumps(selected,ensure_ascii=False)}}]}
        supplied=json.loads(payload['messages'][-1]['content'])
        expected=execution.snapshot(d)['controls']
        if set(supplied['controls'])!=set(expected):raise ValueError('Director did not receive the exact author main-layer component scope')
        if 'native_recipes' in supplied:raise ValueError('Automatic component request contains an incompatible native recipe route')
        return {'choices':[{'message':{'content':json.dumps({'workflow':'motion-kit','segments':rows},ensure_ascii=False)}}]}
    try:
        TrialRelay.call=fixture_response
        from backlot.studio_preflight import prepare as preflight
        composition=preflight(studio,d,folder,old/'input-staging/narration.wav',cues,board,cues)
    finally:TrialRelay.call=original
    if composition['mode']!='motiongit':raise ValueError('Production preflight switched the selected renderer')
    selected=composition['segments'];instance=folder/'motiongit-final'
    motion.make_plan(studio,d,instance,old/'input-staging/presenter.mp4',old/'input-staging/narration.wav',cues,selected)
    motion.preview_instance(instance)
    result={'draft':d,'instance':str(instance),'preview_sha256':sha(instance/'project/preview.json'),
        'source_video_sha256':sha(old/'input-staging/presenter.mp4'),'source_audio_sha256':sha(old/'input-staging/narration.wav'),
        'scope':'Real production preflight with explicit stub director; actual cached media and signed runner. No native full-tour or live-model claim.',
        'generation_calls':0,'remote_calls':0,'stub_director_calls':calls,'segments':len(selected['scenes']) if isinstance(selected,dict) else len(selected)}
    atomic_private(root/(style+'.json'),result)
    return {k:v for k,v in result.items() if k!='draft'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--fixture',type=Path,required=True);p.add_argument('--styles',nargs='+',required=True)
    a=p.parse_args();root=a.root.resolve();root.mkdir(parents=True,exist_ok=True)
    registry=copy.deepcopy(motion.configuration())
    for style in a.styles:registry[style]['validated_execution_modes']=['native'] if style.startswith('motiongit-626-') else ['components']
    atomic_private(root/'test-registry.json',registry);os.environ['HAIKE_MOTIONGIT_REGISTRY']=str(root/'test-registry.json')
    for style in a.styles:
        try:print(json.dumps(prepare(root,a.fixture,style),ensure_ascii=False),flush=True)
        except Exception as e:print(type(e).__name__,str(e),flush=True);raise
