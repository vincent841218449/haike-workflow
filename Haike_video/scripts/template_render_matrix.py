"""Resumable, offline render regression for installed avatar template bindings.

Uses the real registered queue producers. Native cases are explicitly declared
visual fixtures, not an assertion that the fixed choreography fits any script.
No gateway, transcription, model, collection or publication is permitted.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot.studio import Studio, atomic_private
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio_motion import capabilities, runtime, plan, freeze, TEMPLATE_ID
from backlot.studio_template_registry import legacy_ref, package_paths
from backlot.work_catalog import sha
from backlot.studio_render import media_probe
from lib.checkpoint import init_project
from lib.ffmpeg_locator import resolve_ffmpeg_pair

GROUPS = {
    '01-A': ['decompose-and-consolidate'],
    '01-B': ['decompose-and-consolidate'],
    '01-C': ['decompose-and-consolidate'],
    '01-D': ['decompose-and-consolidate'],
    '01-E': ['three-items-consolidate'],
    '02-A': ['apparent-tension-to-value'],
    '02-B': ['cards-to-network'],
    '03-A': ['independent-artifact-review'],
    '04-A': ['fusion-success', 'delivery-reading-complete'],
    '05-A': ['feedback-to-update-natural-end'],
    '06-A': ['basic-keyword'],
}


def read(path):
    return json.loads(Path(path).read_text())


def manifest_group(group):
    manifest = read(package_paths(runtime())[group['selection']])
    return next(g for g in manifest['scenes'] if g['id'] == group['id'].split(':')[1])


def fixture_text(field, labels):
    """Short source-derived labels; deliberately never retain author demo copy."""
    key = field.get('inputPath', field['id'])
    value = labels.get(key, labels.get('default','本地验收'))
    if 'icon' in key: value = '◇'
    if 'presenter' in key or 'brand' in key: value = '海客创作'
    if 'before' in key: value = '等结算'
    if 'after' in key: value = '仍在等'
    if field.get('inputTemplate'): value = '// 01 · '+labels.get('default','本地验收')
    return value[:field.get('maxChars', 32)]


def prepare(root, source, *, styles=None, include_basics=True):
    from PIL import Image
    root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
    studio = Studio(root/'projects')
    queue = ProductionQueue(root/'queue.sqlite3', studio.projects_root)
    source = source.resolve(); data = read(source)
    video, audio = Path(data['source_video']), Path(data['source_audio'])
    for path in [video, audio]:
        if not path.is_file(): raise ValueError('Missing existing master: '+str(path))
    source_root = Path(__file__).resolve().parents[1]
    asr = read(video.parent/'local-asr.json')['result']
    from backlot.studio_avatar import captions, source_captions
    speech_cues=source_captions(data['draft'],captions(asr,media_probe(audio)['duration']))
    identity = {str(p):sha(p) for p in [video,audio]}
    atomic_private(root/'source-lock.json', {'schema':'offline-template-matrix/1','files':identity,
        'source_input':str(source),'scope':'Full basic films and authored-motion excerpt fixtures; not arbitrary-story semantic approval.',
        'paid_calls_allowed':0,'network_allowed':False})
    texture=root/'grain.png'
    if not texture.exists():
        import random
        rng=random.Random(4188)
        image=Image.new('RGB',(256,256));image.putdata([(v,v,v) for v in [rng.randint(80,180) for _ in range(256*256)]])
        image.save(texture)
    cases = read(root/'cases.json') if (root/'cases.json').is_file() else []
    blocked = [row for row in cases if row['status']=='plan-blocked']
    if blocked:atomic_private(root/'blocked-plans.json',blocked)
    cases = [row for row in cases if row['status']!='plan-blocked']
    existing={row['key'] for row in cases}
    for layout in ['portrait','landscape']:
        caps=capabilities(layout)
        for style, ids in GROUPS.items():
            if styles and style not in styles:continue
            ids=data.get('group_overrides',{}).get(style,ids)
            key=f'{style}-{layout}'
            if key in existing or (style=='06-A' and layout!='portrait'): continue
            groups=[next(g for g in caps['groups'] if g['id']==style+':'+id and layout in g['layouts']) for id in ids]
            manifests=[manifest_group(g) for g in groups]
            frames=[round(g['duration']['sourceSeconds']*60) for g in groups]
            if style=='06-A':frames=[360]
            duration=sum(frames)/60
            clip_start=float(data.get('clip_starts',{}).get(style,0))
            # A technical fixture is still a finished speech excerpt. End in a
            # real sentence gap, using only permitted native hold time.
            if not clip_start and any(c['startMs']/1000 < duration < c['endMs']/1000 for c in speech_cues):
                if not groups[-1]['duration'].get('maxHoldFrames'):raise ValueError('Fixture ends inside speech with no native hold capacity')
                ends=[math.ceil((c['endMs']/1000+.08)*60)/60 for c in speech_cues if c['endMs']/1000>=duration]
                duration=next(t for t in ends if not any(c['startMs']/1000<t<c['endMs']/1000 for c in speech_cues))
                frames[-1]=round(duration*60)-sum(frames[:-1])
            clip=root/'clips'/f'{key}-{round(clip_start*60)}-{sum(frames)}.mp4';clip.parent.mkdir(exist_ok=True)
            ffmpeg,_=resolve_ffmpeg_pair()
            if not clip.exists():
                subprocess.run([ffmpeg,'-v','error','-y','-ss',str(clip_start),'-i',str(video),'-ss',str(clip_start),'-i',str(audio),'-map','0:v:0','-map','1:a:0',
                    '-t',str(duration),'-vf','fps=60','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac',str(clip)],check=True,capture_output=True)
            actual=round(float(media_probe(clip)['video']['duration'])*60)/60
            if abs(actual-duration)>.02: raise ValueError('Fixture clock changed')
            excerpt=[]
            for cue in speech_cues:
                if cue['endMs']/1000<=clip_start or cue['startMs']/1000>=clip_start+duration:continue
                item={**cue,'startMs':max(0,cue['startMs']-clip_start*1000),'endMs':min(duration*1000,cue['endMs']-clip_start*1000)}
                if cue['startMs']/1000<clip_start:
                    observed=[w for seg in asr['segments'] for w in seg['words'] if clip_start<=w['start'] and w['end']<=cue['endMs']/1000]
                    quote=''.join(w['text'] for w in observed)
                    if not quote or quote not in data['draft']['text']:raise ValueError('Excerpt start has no unambiguous source quote')
                    item['text']=quote
                if cue['endMs']/1000>clip_start+duration:raise ValueError('Fixture cuts a spoken caption')
                excerpt.append(item)
            text=''.join(c['text'] for c in excerpt)
            d=studio.save_draft({'template_id':TEMPLATE_ID,'title':'模板验收 · '+key,'text':text})
            asset=studio.save_asset(d['id'],'existing-master-excerpt.mp4','video',clip.read_bytes())
            image=studio.save_asset(d['id'],'presenter.png','image',(source_root.parent/'prototypes/haike-avatar-generator/public/assets/presenter.png').read_bytes())
            grain=studio.save_asset(d['id'],'grain.png','image',texture.read_bytes())
            footage=Path(data['evidence_video'])
            evidence=studio.save_asset(d['id'],'existing-evidence.mp4','video',footage.read_bytes())
            segments=[];cursor=0
            for index,(g,m,frame_count) in enumerate(zip(groups,manifests,frames)):
                end=(cursor+frame_count)/60
                part=text if len(groups)==1 else ''.join(c['text'] for c in excerpt if cursor/60<=c['startMs']/1000<end)
                values={}
                for f in g['fields']:
                    if f['type']=='talk': continue
                    if f['type'] in {'text','dynamicText'}: values[f['id']]=fixture_text(f,data.get('fixture_labels',{}))
                    elif f['type']=='image':
                        file=data.get('fixture_images',{}).get(f['id'])
                        supplied=studio.save_asset(d['id'],Path(file).name,'image',Path(file).read_bytes()) if file else None
                        values[f['id']]={'asset':supplied or (grain if 'grain' in f['id'] else image)}
                    elif f['type']=='video':values[f['id']]={'asset':evidence,'offset':0}
                    elif f['type']=='number':
                        value=data.get('fixture_labels',{}).get(f.get('inputPath',f['id']))
                        if type(value) not in (int,float):raise ValueError('Explicit fixture number required: '+f['id'])
                        values[f['id']]=value
                    else:raise ValueError('Unsupported offline fixture field '+str(f))
                origin=m['source']['start'];anchors={g['cueRoles'][cue['id']]:round(cue['at']-origin,4) for cue in m.get('cues',[]) if cue['id'] in g['cueRoles']}
                segments.append({'group':g['id'],'text':part,'end':end,'values':values,'anchors':anchors})
                cursor+=frame_count
            if ''.join(s['text'] for s in segments)!=text:raise ValueError('Fixture transcript partition changed')
            d=studio.save_draft({**d,'input':{'source':asset,'motionLayout':layout,'style':style,
                'music':{'mode':'none'},'face':{'mode':'fixed','cx':.5,'cy':.35,'h':.55},
                'captions':[{'start':c['startMs']/1000,'end':c['endMs']/1000,'text':c['text']} for c in excerpt],
                'segments':segments}})
            result=plan(studio,d)
            row={'key':key,'draft_id':d['id'],'template_ref':legacy_ref(style,layout),'plan':result,'scope':'visual-excerpt-fixture','source_excerpt':[clip_start,clip_start+duration],'duration':duration,'status':'plan-blocked'}
            if result['report']['ready']:
                init_project(d['id'],title=d['title'],pipeline_type='animated-explainer',pipeline_dir=studio.projects_root)
                job=queue.submit(project_id=d['id'],kind='studio_motion',source='workbench',priority='normal',
                    parent_job_id='studio-'+str(d['revision']),idempotency_key='matrix:'+key,
                    frozen_request=freeze(studio,d,result['id'],True))
                row.update(job_id=job['job_id'],status='queued')
            cases.append(row);atomic_private(root/'cases.json',cases)
            print(json.dumps({'key':key,'status':row['status'],'report':result['report'] if not result['report']['ready'] else 'ready'},ensure_ascii=False),flush=True)
    for template in (['avatar-safe-circle-v1','avatar-full-width-v2','avatar-template3-card-3x4-v001'] if include_basics else []):
        key=template
        if key in existing:continue
        d=studio.save_draft({'template_id':template,'title':data['draft']['title'][:16],'text':data['draft']['text'],
            'layout':{'title_size':48,'accent':'#316dd6'},'input':{'soundMode':'audio','subtitles':True}})
        project=studio.projects_root/d['id'];folder=project/'renders/studio-1';folder.mkdir(parents=True,exist_ok=True)
        shutil.copy2(video,folder/'avatar-source.mp4');shutil.copy2(audio,folder/'narration.wav')
        from backlot.studio_avatar import key_identity
        request={'id':'local-matrix:'+key,'workflow_version':1,'local_recomposition':True,'draft':d,
            'key_identity':key_identity(studio),'render_id':'studio-1','max_charge_micros':0,'quotes':{},
            'prepared':{'audio_path':str(folder/'narration.wav'),'duration':media_probe(audio)['duration'],'audio_file':'existing-local'},
            'asr':{'provider':'gateway'}}
        atomic_private(folder/'gateway-state.json',{'prepared':request['prepared'],'stages':{
            'asr':{'job':{'id':'existing-local-asr','status':'succeeded','result':asr},'provenance':'reused-local-asr; not a supplier receipt'}}})
        init_project(d['id'],title='模板验收 · '+key,pipeline_type='avatar-spokesperson',pipeline_dir=studio.projects_root)
        job=queue.submit(project_id=d['id'],kind='studio_avatar',source='workbench',priority='normal',parent_job_id='studio-1',
            idempotency_key='matrix:'+key,frozen_request=request)
        cases.append({'key':key,'draft_id':d['id'],'job_id':job['job_id'],'status':'queued','scope':'full-existing-narration','duration':request['prepared']['duration']})
        atomic_private(root/'cases.json',cases)
    return cases


def prepare_basics(root, source):
    """Full narration + frozen existing B-roll, with no relay configuration."""
    root=root.resolve();root.mkdir(parents=True,exist_ok=True);data=read(source)
    studio=Studio(root/'projects');queue=ProductionQueue(root/'queue.sqlite3',studio.projects_root)
    video,audio=Path(data['source_video']),Path(data['source_audio']);original=Studio(Path(__file__).resolve().parents[1]/'projects')
    asr=read(video.parent/'local-asr.json')['result'];story=read(video.parent/'storyboard.json');cases=[]
    for template in ['avatar-safe-circle-v1','avatar-full-width-v2','avatar-template3-card-3x4-v001']:
        d=studio.save_draft({'template_id':template,'title':data['draft']['title'][:16],'text':data['draft']['text'],
            'layout':{'title_size':48,'accent':'#316dd6'},'input':{'soundMode':'audio','subtitles':True,
            'ai':{'enabled':True,'allow_images':False,'materials':[]}}})
        folder=studio.projects_root/d['id']/'renders/studio-1';folder.mkdir(parents=True)
        shutil.copy2(video,folder/'avatar-source.mp4');shutil.copy2(audio,folder/'narration.wav')
        cached=deepcopy(story);mapping={}
        for scene in cached['scenes']:
            override={**data.get('basic_scene_overrides',{}).get(scene['id'],{}),
                **data.get('basic_template_overrides',{}).get(template,{}).get(scene['id'],{})}
            if override.get('presentation')=='text':
                scene.update(presentation='text');scene.pop('asset',None);scene.pop('asset_sha256',None)
                continue
            old=override.get('asset_id') or scene['asset']['id']
            if old not in mapping:
                path=original.asset(old,data['draft']['id'])
                mapping[old]=studio.save_asset(d['id'],path.name,'video' if path.suffix.lower() in {'.mp4','.mov'} else 'image',path.read_bytes())
            provenance=scene['asset'].get('provenance',{}) if not override else {
                'source':'local-reuse','source_project_id':data['draft']['id'],'source_asset_id':old,
                'sha256':sha(original.asset(old,data['draft']['id']))}
            scene['asset']={**mapping[old],'provenance':provenance}
            scene['asset_sha256']=sha(studio.asset(scene['asset']['id'],d['id']))
            scene['framing']=override.get('framing',{'role':'footage'})
        cached['draft_fingerprint']=hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
        atomic_private(folder/'storyboard.json',cached)
        from backlot.studio_avatar import key_identity
        request={'id':'local-matrix-with-media:'+template,'workflow_version':1,'local_recomposition':True,'draft':d,
            'key_identity':key_identity(studio),'render_id':'studio-1','max_charge_micros':0,'quotes':{},
            'prepared':{'audio_path':str(folder/'narration.wav'),'duration':media_probe(audio)['duration'],'audio_file':'existing-local'},
            'asr':{'provider':'gateway'}}
        atomic_private(folder/'gateway-state.json',{'prepared':request['prepared'],'stages':{
            'asr':{'job':{'id':'existing-local-asr','status':'succeeded','result':asr},'provenance':'reused-local-asr; not a supplier receipt'}}})
        init_project(d['id'],title='素材回归 · '+template,pipeline_type='avatar-spokesperson',pipeline_dir=studio.projects_root)
        job=queue.submit(project_id=d['id'],kind='studio_avatar',source='workbench',priority='normal',parent_job_id='studio-1',
            idempotency_key='matrix-with-media:'+template,frozen_request=request)
        cases.append({'key':template,'draft_id':d['id'],'job_id':job['job_id'],'status':'queued','scope':'full-existing-narration-and-B-roll','duration':request['prepared']['duration']})
        atomic_private(root/'cases.json',cases)


def run(root):
    root=root.resolve();projects=root/'projects';queue=ProductionQueue(root/'queue.sqlite3',projects)
    class NoGateway:
        def __getattr__(self,name):raise RuntimeError('Network/supplier forbidden in render matrix: '+name)
    def blocked(*args,**kwargs):raise RuntimeError('Network forbidden during offline render matrix')
    socket.create_connection=blocked
    socket.socket.connect=blocked
    from backlot.studio_avatar import run_avatar
    worker=ProductionQueueWorker(queue,projects)
    worker.handlers['studio_avatar']=lambda job:run_avatar(projects/job['project_id'],job['frozen_request'],NoGateway(),on_progress=worker._stage_reporter(job))
    while True:
        cases=read(root/'cases.json'); pending=[r for r in cases if r.get('job_id') and queue.get(r['job_id'])['status']=='queued']
        if not pending:break
        print('RENDER '+pending[0]['key'],flush=True);worker.run_once()
        for row in cases:
            if row.get('job_id'):
                job=queue.get(row['job_id']);row.update(status=job['status'],stage=job['stage'],result=job.get('result'))
        atomic_private(root/'cases.json',cases)
        print(json.dumps([{k:r.get(k) for k in ('key','status','stage')} for r in cases],ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','prepare-basics','run']);parser.add_argument('root',type=Path)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--styles',nargs='*');parser.add_argument('--skip-basics',action='store_true')
    args=parser.parse_args()
    if args.action!='run' and not args.source:parser.error('--source is required; no private episode is a shared default')
    if args.action=='prepare':prepare(args.root,args.source,styles=args.styles,include_basics=not args.skip_basics)
    elif args.action=='prepare-basics':prepare_basics(args.root,args.source)
    else:run(args.root)
