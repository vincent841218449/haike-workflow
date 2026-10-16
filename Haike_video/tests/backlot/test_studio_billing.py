"""No video aggregate limit; keep stage quotes, legacy permissions and recovery."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.production_queue import ProductionQueue, ProductionQueueConflict
from backlot.studio import Studio, atomic_private
from backlot.studio_api import router
from backlot.studio_avatar import key_identity
from backlot.studio_billing import authorization, check_total
from backlot.work_catalog import WorkError


@pytest.fixture
def rig(tmp_path):
    studio = Studio(tmp_path/'projects')
    draft = studio.save_draft({'template_id':'avatar-safe-circle-v1', 'title':'原视频', 'text':'测试原声。', 'input':{'soundMode':'audio'}})
    project = studio.projects_root/draft['id']; project.mkdir(parents=True)
    (project/'project.json').write_text('{"title":"原视频"}')
    queue = ProductionQueue(tmp_path/'queue.sqlite3', studio.projects_root)
    frozen = {'id':'original-quote','draft':draft,'key_identity':key_identity(studio),'render_id':'studio-1','quotes':{},'prepared':{},'max_charge_micros':10_000_000}
    job = queue.submit(project_id=draft['id'], kind='studio_avatar', source='workbench', priority='normal', parent_job_id='studio-1', frozen_request=frozen)
    queue.claim_next('w')
    job = queue.finish(job['job_id'],'w',status='awaiting_human',stage='预算不足',error={'code':'budget_exceeded'})
    app = FastAPI(); app.state.studio=studio; app.state.works_projects_root=studio.projects_root; app.state.production_queue=queue; app.include_router(router)
    return studio, queue, job, TestClient(app)


def test_no_synthetic_maximum_and_legacy_limits_stay_explicit():
    assert authorization() == {'billing_policy':'actual_usage','max_charge_micros':None}
    check_total(authorization(), 10**15)
    with pytest.raises(WorkError, match='上限'): check_total(authorization(100), 101)
    with pytest.raises(WorkError, match='授权缺失'): check_total({}, 0)
    for invalid in (True,0,-1,'10',float('inf')):
        with pytest.raises(WorkError): authorization(invalid)


@pytest.mark.parametrize('policy',[None,'actual_usage'])
def test_new_http_creation_freezes_actual_usage_without_budget(rig,policy):
    studio, queue, old, client = rig
    d=studio.save_draft({**studio.draft(old['project_id']), 'title':'新版本'})
    data={'id':'new-quote','draft':d,'key_identity':key_identity(studio),'quotes':{'avatar':{'model':'haike/avatar','max_charge_micros':'13_200_000'.replace('_','')}},'prepared':{}}
    with studio.db() as db: db.execute('INSERT INTO studio_quotes VALUES(?,?)', (data['id'],json.dumps(data)))
    body={'revision':d['revision'],'quote_id':data['id'],'confirmed':True,'max_charge_micros':1}
    if policy: body['billing_policy']=policy
    result=client.post(f"/api/studio/drafts/{d['id']}/generate",json=body)
    assert result.status_code==200, result.text
    again=client.post(f"/api/studio/drafts/{d['id']}/generate",json=body)
    assert again.json()['job_id']==result.json()['job_id']
    frozen=queue.get(result.json()['job_id'],include_private=True)['frozen_request']
    assert frozen['billing_policy']=='actual_usage' and frozen['max_charge_micros'] is None
    assert frozen['quotes']['avatar']==data['quotes']['avatar']


def test_continue_original_is_atomic_idempotent_and_preserves_frozen_inputs(rig):
    _, queue, job, _ = rig
    before=queue.get(job['job_id'],include_private=True)['frozen_request']
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:queue.continue_actual_usage(job['job_id'],job['revision']),range(8)))
    assert {r['job_id'] for r in results}=={job['job_id']}
    after=queue.get(job['job_id'],include_private=True)
    frozen=after['frozen_request']; receipt=frozen.pop('billing_policy_changes')
    assert len(receipt)==1 and receipt[0]['previous_max_charge_micros']==10_000_000
    assert frozen=={**before,'billing_policy':'actual_usage','max_charge_micros':None}
    assert after['status']=='queued' and after['revision']==job['revision']+1
    assert len([e for e in queue.events(job['job_id']) if e['event_type']=='billing_authorized'])==1


def test_continue_http_checks_account_confirmation_revision_and_origin(rig):
    studio, queue, job, client=rig
    url=f"/api/studio/tasks/{job['job_id']}/continue"
    body={'confirmed':True,'revision':job['revision']}
    assert client.post(url,json={**body,'confirmed':False}).status_code==422
    assert client.post(url,json=body,headers={'origin':'https://other.example'}).status_code==403
    assert client.post(url,json={**body,'revision':job['revision']-1}).status_code==409
    detail=client.get('/api/studio/tasks/'+job['job_id']).json()['task']
    assert detail['status_label']=='等待继续制作' and detail['actions']['continue'] is True
    atomic_private(studio.config_path,{'base_url':'http://127.0.0.1:12345/v2','api_key':'different-test-account'})
    assert client.post(url,json=body).status_code==409
    atomic_private(studio.config_path,{})
    assert client.post(url,json=body).status_code==200
    assert client.post(url,json=body).status_code==200
    assert queue.get(job['job_id'])['status']=='queued'


def test_continue_cannot_reactivate_a_superseded_creation(rig):
    _,queue,job,_=rig
    frozen=queue.get(job['job_id'],include_private=True)['frozen_request']
    next_job=queue.submit(project_id=job['project_id'],kind='studio_avatar',source='workbench',priority='normal',parent_job_id='new',frozen_request={**frozen,'id':'new-quote','render_id':'new'})
    queue.link_creation(next_job['job_id'],job['job_id'],'regeneration')
    with pytest.raises(ProductionQueueConflict,match='更新'):queue.continue_actual_usage(job['job_id'],job['revision'])
    assert queue.get(job['job_id'],include_private=True)['frozen_request']==frozen


@pytest.mark.parametrize('status,code',[('ambiguous','provider_pending'),('failed','unavailable'),('awaiting_human','audio_script_mismatch'),('completed','')])
def test_continue_does_not_restart_unknown_or_unrelated_states(rig,status,code):
    _,queue,job,_=rig
    queue.continue_actual_usage(job['job_id'],job['revision'])
    queue.claim_next('w')
    changed=queue.finish(job['job_id'],'w',status=status,stage='other',error={'code':code})
    with pytest.raises(ProductionQueueConflict):queue.continue_actual_usage(job['job_id'],changed['revision'])
