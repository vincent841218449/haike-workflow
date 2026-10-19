"""Offline automatic-template integration QA with an explicitly supplied cached episode.

No generation/ASR/LLM credentials or calls. Isolated Studio and unified render
queue. Prepare actual previews, inspect them, then render with their exact SHA.
"""
import argparse
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot import studio_motiongit as motion, studio_template_auto as automatic
from backlot.studio import Studio, atomic_private
from backlot.studio_avatar import captions, source_captions
from backlot.work_catalog import sha


def prepare(root, style, source, text, portrait):
    studio = Studio(root / style / 'projects')
    config = motion.installed(style)
    draft = studio.save_draft({'template_id':'avatar-safe-circle-v1',
        'title':'自动模板声画回归（缓存素材测试）','text':text})
    person = studio.save_asset(draft['id'], 'portrait.jpg', 'image', portrait.read_bytes())
    draft['input'].update(motion={'style':style,'layout':config['layout']},
        templateExecution='auto', templateRef=motion.template_ref(config), subtitles=True,
        portrait=person, ai={'enabled':True,'materials':[]}, music={'mode':'none'})
    folder = studio.projects_root / draft['id'] / 'renders/studio-1'
    folder.mkdir(parents=True,exist_ok=True)
    from backlot.studio_render import media_probe
    audio = source / 'narration.wav'; video = source / 'avatar-source.mp4'
    duration = media_probe(audio)['duration']
    asr = json.loads((source / 'local-asr.json').read_text())['result']
    cues = source_captions(draft, captions(asr,duration))
    automatic.precheck(studio,draft,folder)
    board = automatic.storyboard(studio,draft,folder,duration)
    selected = motion.select(studio,draft,folder,cues,board,caption_cues=cues)
    instance = folder / 'motiongit-final'
    motion.make_plan(studio,draft,instance,video,audio,cues,selected)
    motion.preview_instance(instance)
    result={'draft':draft,'instance':str(instance),'source_video_sha256':sha(video),
        'source_audio_sha256':sha(audio),'preview_sha256':sha(instance/'project/preview.json'),
        'scope':'cached 19.6s presenter/narration; automatic author components, not a new avatar or native sample replay',
        'generation_calls':0,'remote_calls':0,'segments':len(selected)}
    atomic_private(root/(style+'.json'),result)
    return {k:v for k,v in result.items() if k!='draft'}


def render(root,style,review_sha):
    from backlot.production_queue import ProductionQueue
    from backlot.production_queue_worker import ProductionQueueWorker
    from lib.checkpoint import init_project
    fixture=json.loads((root/(style+'.json')).read_text())
    instance=Path(fixture['instance']);folder=instance.parent;project=folder.parent.parent
    if fixture['preview_sha256']!=review_sha or sha(instance/'project/preview.json')!=review_sha:
        raise ValueError('Preview changed; inspect current images first')
    atomic_private(instance/'visual-review.json',{'approved':True,'issues':[],
        'preview_sha256':review_sha,'scope':'agent-inspected representative cached-media QA frames','listened':False})
    init_project(project.name,title=fixture['draft']['title'],pipeline_type='animated-explainer',pipeline_dir=project.parent)
    studio=Studio(project.parent);request=motion.freeze_job(studio,fixture['draft'],folder,instance)
    queue=ProductionQueue(root/style/'queue.sqlite3',project.parent)
    job=queue.submit(project_id=project.name,kind='studio_motion',source='workbench',priority='normal',
        parent_job_id='automatic-matrix-'+style,idempotency_key='automatic-matrix:'+style+':'+review_sha,frozen_request=request)
    if job['status']=='queued':ProductionQueueWorker(queue,project.parent).run_once()
    job=queue.get(job['job_id'])
    result={'style':style,'status':job['status'],'stage':job['stage'],'job_id':job['job_id'],'generation_calls':0}
    if job['status']=='completed':
        qa=json.loads((folder/'qa.json').read_text());output=folder/'motion-preview.mp4';archive=folder/'editable-project.zip'
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert json.loads(z.read('delivery.json'))['output_sha256']==sha(output)
        result.update(output=str(output),archive=str(archive),output_sha256=sha(output),
            archive_sha256=sha(archive),presentation=qa['presentation'],streams=qa['output'],audio_delivery=qa['audio_delivery'])
    atomic_private(root/(style+'-result.json'),result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('style')
    p.add_argument('--source',type=Path);p.add_argument('--text-file',type=Path);p.add_argument('--portrait',type=Path)
    p.add_argument('--render-reviewed')
    a=p.parse_args();root=a.root.resolve();root.mkdir(parents=True,exist_ok=True)
    result=render(root,a.style,a.render_reviewed) if a.render_reviewed else prepare(root,a.style,a.source.resolve(),a.text_file.read_text().strip(),a.portrait.resolve())
    print(json.dumps(result,ensure_ascii=False))
