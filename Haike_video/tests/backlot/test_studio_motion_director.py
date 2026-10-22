"""Regression coverage for false native identity, semantic invention and spending order."""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backlot.studio_motion_director import compile_evidence, direct, validate_semantics
from backlot.studio_presentation import verify_native
from backlot.work_catalog import WorkError


@pytest.fixture
def content():
    text = '文案和声音汇聚，输出视频。'
    group = {'id':'04-A:fusion-success', 'intents':['merge'], 'phases':['inputs','merge','output'],
             'counts':{'inputs':{'min':2,'max':2}}, 'fields':[{'id':'title','type':'text'}]}
    evidence = {'intent':{'value':'merge','quote':text},
                'phases':[{'name':'inputs','quote':'文案和声音'}, {'name':'merge','quote':'汇聚'}, {'name':'output','quote':'输出视频'}],
                'counts':{'inputs':[{'name':'文案','quote':'文案'}, {'name':'声音','quote':'声音'}]},
                'support':{'title':['文案和声音','输出视频']}}
    return text, group, evidence


def test_counts_come_from_distinct_actual_entities(content):
    text, group, evidence = content
    assert validate_semantics(text, group, evidence) == evidence
    evidence['counts']['inputs'] *= 2
    with pytest.raises(WorkError, match='真实数量'): validate_semantics(text, group, evidence)


def test_template_minimum_cannot_be_used_as_source_fact(content):
    _, group, evidence = content
    story = '十四个月的结算款，小区门口三十平方米，九万八。'
    with pytest.raises(WorkError, match='原文'): validate_semantics(story, group, evidence)
    evidence['counts']['inputs'] = 2
    with pytest.raises(WorkError, match='数量依据'): validate_semantics(content[0], group, evidence)


def test_evidence_partitions_source_without_gaps_or_overlapping_ownership(content):
    text, group, evidence = content
    compiled, units, facts = compile_evidence(text, group, evidence, 'hash', 7, {'title':'本期汇聚'})
    assert ''.join(u['text'] for u in units) == text
    assert units[0]['start'] == 7 and units[-1]['end'] == len(text) + 7
    assert all(a['end'] == b['start'] for a,b in zip(units, units[1:]))
    assert compiled['counts'] == {'inputs':2}
    assert compiled['ownershipRefs'] == [u['id'] for u in units]
    assert compiled['supportingRefs']['title'] != compiled['ownershipRefs']
    assert facts['phases']['merge']


def test_same_display_id_cannot_hide_a_non_native_adapter(monkeypatch):
    ref = {'runtime':'adu-legacy', 'style':'04-A','layout':'portrait'}
    monkeypatch.setattr('backlot.studio_template_registry.verify_ref', lambda value: None)
    with pytest.raises(WorkError, match='并非所选'):
        verify_native({'id':'adu:04-A:portrait','adapter':'studio-instrument-v1','template_ref':ref}, ref, rendered=True)
    with pytest.raises(WorkError, match='实际计划'):
        verify_native({'adapter':'adu-motion-video','template_ref':ref}, ref, rendered=True)


def test_independent_semantic_rejection_is_not_promoted_to_ready(tmp_path, monkeypatch, content):
    text, group, evidence = content
    draft = {'text':text,'input':{'motion':{'style':'04-A','layout':'portrait'}}}
    monkeypatch.setattr('backlot.studio_storyboard.motion_options', lambda d:{'id':'04-A','groups':[group]})
    calls=[]
    results=[{'segments':[{'text':text,'group':group['id'],'semantics':evidence}], 'reason':'双输入汇聚'},
             {'approved':False,'issues':['输出视频不是成功交付的证据']}]
    def call(self, stage, payload):
        calls.append(stage)
        return {'choices':[{'message':{'content':json.dumps(results[len(calls)-1])}}]}
    monkeypatch.setattr('backlot.studio_storyboard.TrialRelay.call',call)
    with pytest.raises(WorkError, match='语义检查未通过'): direct(None,draft,tmp_path)
    assert len(calls)==2
    assert json.loads((tmp_path/'native-direction.json').read_text())['review']['approved'] is False
    with pytest.raises(WorkError, match='内部检查'): direct(None,draft,tmp_path)
    assert len(calls)==2


def test_new_native_job_checks_whole_script_before_any_paid_stage(tmp_path, monkeypatch):
    from backlot.studio_avatar import run_avatar
    from backlot.studio import Studio
    studio=Studio(tmp_path/'projects')
    draft=studio.save_draft({'template_id':'avatar-safe-circle-v1','text':'讨欠款的故事','input':{'motion':{'style':'04-A','layout':'portrait'}}})
    monkeypatch.setattr('backlot.studio_avatar.key_identity',lambda s:'same')
    monkeypatch.setattr('backlot.studio_presentation.verify_native',lambda *a,**k:None)
    def incompatible(*args): raise WorkError('没有双输入合并关系','template_incompatible')
    monkeypatch.setattr('backlot.studio_motion_director.direct',incompatible)
    sdk=SimpleNamespace(quote=lambda *a:pytest.fail('must not quote a new stage'),confirm=lambda *a:pytest.fail('must not charge'))
    request={'key_identity':'same','render_id':'native-test','prepared':{},'draft':draft,
             'workflow_version':4,'template_ref':{'runtime':'adu-legacy'},'presentation':{'id':'adu:04-A:portrait'}}
    result=run_avatar(studio.projects_root/draft['id'],request,sdk)
    assert result['status']=='awaiting_human' and result['error']['code']=='template_incompatible'
    assert not (studio.projects_root/draft['id']/'renders/native-test/gateway-state.json').exists()


def test_output_receipt_checks_bytes_and_exact_plan(tmp_path, monkeypatch):
    from backlot.studio_motion_qa import cached_result
    from backlot.work_catalog import sha
    monkeypatch.setattr('backlot.studio_motion_qa.verify_ref',lambda ref:None)
    video=tmp_path/'motion-preview.mp4';video.write_bytes(b'version-one')
    qa={'source':{'plan_sha256':'plan'},'presentation':{'template_ref':{},'plan_sha256':'plan','output_sha256':sha(video)}}
    (tmp_path/'qa.json').write_text(json.dumps(qa))
    assert cached_result(tmp_path)['presentation']['plan_sha256']=='plan'
    video.write_bytes(b'another-version')
    with pytest.raises(WorkError, match='成片字节'): cached_result(tmp_path)
