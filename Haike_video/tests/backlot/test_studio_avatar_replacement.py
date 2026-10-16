"""An explicit human reissue replaces one unknown stage, never the whole video."""
import json

import pytest

from backlot.production_queue import ProductionQueue, ProductionQueueConflict
from backlot.studio import atomic_private
from backlot.studio_avatar import run_avatar
from tests.backlot.test_studio_resilience import rig


def pending(rig):
    studio, project, request, gateway, events = rig
    request.update(billing_policy='actual_usage', max_charge_micros=None)
    gateway.status = 'submission_unknown'
    assert run_avatar(project, request, gateway)['status'] == 'ambiguous'
    queue = ProductionQueue(project.parent.parent / 'queue.sqlite3', studio.projects_root)
    (project / 'project.json').write_text('{"title":"原视频"}')
    job = queue.submit(project_id=project.name, kind='studio_avatar', source='codex',
                       priority='normal', parent_job_id='original', frozen_request=request)
    queue.claim_next('w')
    queue.finish(job['job_id'], 'w', status='ambiguous', stage='原回执待核对',
                 error={'code':'provider_pending'}, safe_resume_point='studio_avatar_provider')
    job = queue.get(job['job_id'])
    state = json.loads((project / 'renders/test/gateway-state.json').read_text())
    # No supplier task number or usable media, exactly like the live incident.
    state['stages']['avatar']['job'].update(upstream_id=None, result=None)
    atomic_private(project / 'renders/test/gateway-state.json', state)
    return queue, job, state


def authorize(queue, job, state, **overrides):
    args = dict(revision=job['revision'], previous_intent=state['stages']['avatar']['intent'],
                approval_ref='human-reply-one', maximum=100)
    args.update(overrides)
    return queue.replace_avatar(job['job_id'], **args)


def test_explicit_reissue_keeps_same_job_and_original_frozen_inputs(rig):
    queue, job, state = pending(rig)
    before = queue.get(job['job_id'], include_private=True)['frozen_request']
    result = authorize(queue, job, state)
    repeated = authorize(queue, job, state)
    after = queue.get(job['job_id'], include_private=True)['frozen_request']
    assert result['job_id'] == repeated['job_id'] == job['job_id']
    assert result['status'] == 'queued' and len(queue.list()['tasks']) == 1
    assert {k:v for k,v in after.items() if k != 'avatar_replacements'} == before
    assert len(after['avatar_replacements']) == 1
    assert after['avatar_replacements'][0]['previous_job_id'] == 'original-avatar-job'
    assert after['avatar_replacements'][0]['previous_intent'] == state['stages']['avatar']['intent']


@pytest.mark.parametrize('change', ['stale', 'wrong_intent', 'has_result'])
def test_reissue_cannot_replace_a_changed_or_already_resolved_request(rig, change):
    queue, job, state = pending(rig)
    overrides = {}
    if change == 'stale': overrides['revision'] = job['revision'] - 1
    if change == 'wrong_intent': overrides['previous_intent'] = 'call_' + 'f' * 32
    if change == 'has_result':
        state['stages']['avatar']['job'].update(media_artifact_available=True,
                                               result={'video_url':'https://supplier.example/ready.mp4'})
        atomic_private(rig[1] / 'renders/test/gateway-state.json', state)
    with pytest.raises(ProductionQueueConflict): authorize(queue, job, state, **overrides)
    assert queue.get(job['job_id'])['status'] == 'ambiguous'


def test_reissue_polls_one_new_intent_and_retains_old_unknown_billing(rig):
    queue, job, old = pending(rig)
    authorize(queue, job, old)
    request = queue.get(job['job_id'], include_private=True)['frozen_request']
    _, project, _, gateway, events = rig
    gateway.quote = lambda model, inputs, ref: {'id':'replacement-quote','model':model,'max_charge_micros':100}
    for _ in range(2): assert run_avatar(project, request, gateway)['status'] == 'ambiguous'
    calls = [e for e in events if e[:2] == ('confirm','haike/avatar')]
    assert len(calls) == 2 and calls[0][2] != calls[1][2]
    state = json.loads((project / 'renders/test/gateway-state.json').read_text())
    assert state['stage_history'][0]['stage'] == old['stages']['avatar']
    assert state['stages']['asr'] == old['stages']['asr']
    gateway.status = 'succeeded'
    assert run_avatar(project, request, gateway)['status'] == 'completed'
    assert len([e for e in events if e[:2] == ('confirm','haike/avatar')]) == 2


def test_reissue_quote_change_stops_before_confirming_a_new_charge(rig):
    queue, job, old = pending(rig)
    authorize(queue, job, old)
    request = queue.get(job['job_id'], include_private=True)['frozen_request']
    _, project, _, gateway, events = rig
    gateway.quote = lambda *args: {'id':'higher-quote','model':'haike/avatar','max_charge_micros':101}
    result = run_avatar(project, request, gateway)
    assert result['status'] == 'awaiting_human' and result['error']['code'] == 'quote_changed'
    assert len([e for e in events if e[:2] == ('confirm','haike/avatar')]) == 1
