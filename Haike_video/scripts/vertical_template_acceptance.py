"""Render current packages against an existing cached technical fixture.

No TTS/avatar/ASR/LLM calls. This proves engine/media compatibility only, never
native-tour coverage or correctness of the production director's new choices.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backlot import studio_motiongit as motion
from backlot.studio import Studio,atomic_private
from backlot.work_catalog import sha


def prepare(root,fixture_path,style,media=None):
    fixture=json.loads(fixture_path.read_text());old=Path(fixture['instance'])
    params=json.loads((old/'input-staging/params.json').read_text())
    cues=[{'startMs':c['s']*1000,'endMs':c['e']*1000,'text':c['text']} for c in params['timeline']['captions']]
    studio=Studio(root/style/'projects');cfg=motion.installed(style)
    d=studio.save_draft({'template_id':'avatar-safe-circle-v1','text':fixture['draft']['text'],'title':'数字人功能测试'})
    source=Studio(old.parents[3]);person=source.asset(fixture['draft']['input']['portrait']['id'],fixture['draft']['id'])
    asset=studio.save_asset(d['id'],'portrait.jpg','image',person.read_bytes())
    d['input'].update(motion={'style':style,'layout':'portrait'},templateExecution='auto',templateRef=motion.template_ref(cfg),
        portrait=asset,ai={'enabled':True,'materials':[]},subtitles=True,music={'mode':'none'})
    folder=studio.projects_root/d['id']/'renders/studio-1';folder.mkdir(parents=True,exist_ok=True)
    instance=folder/'motiongit-final';rows=copy.deepcopy(params['timeline']['segments'])
    for row in rows:row['styleProfile']=cfg['style_profile']
    if media:
        from backlot.studio_render import media_probe
        if media_probe(media)['duration']<rows[1]['t1']-rows[1]['t0']:
            raise ValueError('Source clip is shorter than the test slot')
        asset=studio.save_asset(d['id'],media.name,'video',media.read_bytes())
        rows[1].update(control='media',variant='tilt',props={'src':'asset:'+asset['id'],
            'sourceStart':0,'title':'真实素材槽技术检查'},**{'$framing':{'role':'footage','focus':{'x':.5,'y':.5}}})
    motion.make_plan(studio,d,instance,old/'input-staging/presenter.mp4',old/'input-staging/narration.wav',cues,rows)
    motion.preview_instance(instance)
    result={'draft':d,'instance':str(instance),'preview_sha256':sha(instance/'project/preview.json'),
        'source_video_sha256':sha(old/'input-staging/presenter.mp4'),'source_audio_sha256':sha(old/'input-staging/narration.wav'),
        'scope':'Cached technical fixture; engine compatibility only, not native tour or new director acceptance',
        'generation_calls':0,'remote_calls':0,'segments':len(rows),
        'media_slot_sha256':sha(media) if media else None}
    atomic_private(root/(style+'.json'),result)
    return {k:v for k,v in result.items() if k not in {'draft'}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--fixture',type=Path,required=True);p.add_argument('--styles',nargs='+',required=True)
    p.add_argument('--media',type=Path,help='An inspected local video for a technical slot test, not automatic semantic acceptance')
    args=p.parse_args();root=args.root.resolve();root.mkdir(parents=True,exist_ok=True)
    for style in args.styles:
        try:print(json.dumps({'style':style,**prepare(root,args.fixture,style,args.media)},ensure_ascii=False),flush=True)
        except Exception as e:
            atomic_private(root/(style+'-failure.json'),{'error':str(e),'generation_calls':0})
            print(json.dumps({'style':style,'error':str(e)},ensure_ascii=False),flush=True)
