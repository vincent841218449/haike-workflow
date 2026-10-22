"""Local, isolated official-package checks; never calls generation or publishes.

Prepare first, inspect actual previews, then run --render-reviewed with the
specific preview receipt SHA. No package is enabled by this technical fixture.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backlot import studio_motiongit as motion
from backlot.studio import Studio,atomic_private
from backlot.work_catalog import sha


def prepare(root,style):
    config=motion.installed(style)
    project=root/'projects'/('studio-check-'+style)
    instance=project/'renders/studio-1/motiongit-final'
    instance.parent.mkdir(parents=True,exist_ok=True)
    motion.new_instance(config,instance)
    atomic_private(instance/'haike-workflow.json',{'workflow':'motion-kit'})
    inputs=instance/'input-staging';inputs.mkdir(exist_ok=True)
    caps=json.loads(Path(config['capabilities']).read_text())
    profile=motion.component_profile(config,caps)
    params={'workflow':'motion-kit','timeline':{'layout':config['layout'],'duration':6,
        'sourceStart':0,'voiceover':'','music':'','ending':'cut','styleProfile':profile,
        'hud':False,'segments':[{'control':'title','t0':0,'t1':6,
            'props':{'line1':'模板功能检查','line2':'原包动作与声音'},'styleProfile':profile,
            'presenter':'hide','transition':'cut'}],'captions':[]}}
    atomic_private(inputs/'params.json',params)
    env=dict(os.environ);env['PATH']=config.get('media_bin','')+os.pathsep+str(Path(sys.executable).parent)+os.pathsep+env.get('PATH','')
    setup=subprocess.run(['node',config['helper'],'run',config['package'],'--instance',str(instance),
        '--cache',config['cache'],'setup','--workflow','motion-kit'],capture_output=True,text=True,env=env,timeout=600)
    atomic_private(instance/'setup-receipt.json',{'returncode':setup.returncode,'stdout':setup.stdout,'stderr':setup.stderr})
    if setup.returncode:raise RuntimeError('官方运行环境未通过；诊断保存在私有实例')
    motion.command(config,instance,'check-params',inputs/'params.json','--inputs',inputs,log=instance/'check-params.log')
    if not motion.plan_exists(instance):
        motion.command(config,instance,'plan',inputs/'params.json','--inputs',inputs,'--out',instance/'plan',log=instance/'plan.log')
    motion.preview_instance(instance)
    atomic_private(instance/'clock-alignment.json',{'technical_fixture':True,'duration':6,'speech_speed':1,'person_freeze':False})
    return {'style':style,'instance':str(instance),'preview_sha256':sha(instance/'project/preview.json'),
        'scope':'6-second component fixture; no narration, presenter, BGM or full native choreography',
        'paid_calls':0,'production_enabled':False}


def render(root,style,review_sha):
    from backlot.production_queue import ProductionQueue
    from backlot.production_queue_worker import ProductionQueueWorker
    from lib.checkpoint import init_project
    project=root/'projects'/('studio-check-'+style);folder=project/'renders/studio-1';instance=folder/'motiongit-final'
    preview=instance/'project/preview.json'
    if sha(preview)!=review_sha:raise ValueError('预览已改变，不能借用旧核验')
    config=motion.instance_config(instance)
    receipt={'approved':True,'issues':[],'preview_sha256':review_sha,
        'scope':'agent-inspected sampled technical frames only','listened':False}
    atomic_private(instance/'visual-review.json',receipt)
    draft={'id':project.name,'title':'模板功能检查（技术样本）','text':'模板功能检查，原包动作与声音。',
        'input':{'motion':{'style':style,'layout':config['layout']},'templateExecution':'components'}}
    init_project(project.name,title=draft['title'],pipeline_type='animated-explainer',pipeline_dir=root/'projects')
    studio=Studio(root/'projects');request=motion.freeze_job(studio,draft,folder,instance)
    q=ProductionQueue(root/'queue.sqlite3',root/'projects')
    job=q.submit(project_id=project.name,kind='studio_motion',source='workbench',priority='normal',parent_job_id='matrix-'+style,
        idempotency_key='motiongit-local-matrix:'+style+':'+review_sha,frozen_request=request)
    if job['status']=='failed':job=q.retry(job['job_id'])
    if job['status']=='queued':ProductionQueueWorker(q,root/'projects').run_once()
    result=q.get(job['job_id']);atomic_private(folder/'matrix-job.json',result)
    return {'style':style,'job_id':job['job_id'],'status':result['status'],'stage':result['stage']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('style')
    p.add_argument('--render-reviewed',metavar='PREVIEW_SHA256');a=p.parse_args();root=a.root.resolve()
    print(json.dumps(render(root,a.style,a.render_reviewed) if a.render_reviewed else prepare(root,a.style),ensure_ascii=False))
