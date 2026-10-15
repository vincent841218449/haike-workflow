"""Selected visual identity is a production invariant, not a fallback hint."""
import pytest
import hashlib
import json

from backlot.studio_preflight import prepare
from backlot.work_catalog import WorkError


def test_default_automatic_policy_preserves_selected_motion(tmp_path, monkeypatch):
    audio = tmp_path/'narration.wav'; audio.write_bytes(b'original-audio')
    draft = {'id':'test','template_id':'avatar-safe-circle-v1','title':'故事','layout':{},
             'input':{'motion':{'style':'04-A','layout':'portrait'},'templatePolicy':'auto'}}
    def incompatible(*args): raise WorkError('当前故事没有三步流程，不能套用固定组')
    monkeypatch.setattr('backlot.studio_storyboard.select_motion', incompatible)
    draft['text']='原故事'
    storyboard={'status':'ready','duration':3,'scenes':[{'id':'scene-1','start':0,'end':3,'text':'原故事','asset':{'id':'asset'},'asset_sha256':'frozen'}]}
    value=prepare(None,draft,tmp_path,audio,[],storyboard,[])
    assert value['mode']=='instrument' and value['draft']==draft
    assert value['presentation']['id']=='adu:04-A:portrait'
    assert value['presentation']['variant']=='narrative-v1'


def test_unavailable_native_template_never_silently_falls_back(tmp_path,monkeypatch):
    audio=tmp_path/'narration.wav';audio.write_bytes(b'audio')
    draft={'input':{'motion':{'style':'03-A','layout':'portrait'}}}
    def invalid(*args):raise WorkError('原生动作不适合当前原文')
    monkeypatch.setattr('backlot.studio_storyboard.select_motion',invalid)
    with pytest.raises(WorkError,match='不会自动换风格') as error:prepare(None,draft,tmp_path,audio,[],{},[])
    assert error.value.code=='template_incompatible'


def test_old_cross_template_fallback_cache_cannot_be_resumed_as_selected_template(tmp_path):
    from backlot.work_catalog import sha
    audio=tmp_path/'narration.wav';audio.write_bytes(b'audio')
    draft={'input':{'motion':{'style':'04-A','layout':'portrait'}}}
    fingerprint=hashlib.sha256(json.dumps([draft,sha(audio),[],{}],sort_keys=True).encode()).hexdigest()
    (tmp_path/'composition-preflight.json').write_text(json.dumps({'mode':'basic','fingerprint':fingerprint}))
    with pytest.raises(WorkError,match='旧检查'):prepare(None,draft,tmp_path,audio,[],{},[])


def test_render_identity_cannot_claim_another_selected_template():
    from backlot.studio_presentation import verify
    draft={'input':{'motion':{'style':'04-A','layout':'portrait'}}}
    with pytest.raises(WorkError,match='实际渲染模板'):
        verify(draft,{'id':'avatar-safe-circle-v1'})


def test_instrument_preserves_required_materials_and_complete_script():
    from backlot.studio_presentation import instrument_plan
    draft={'template_id':'avatar-safe-circle-v1','text':'原故事','input':{
        'motion':{'style':'04-A','layout':'portrait'},'ai':{'materials':[{'id':'required','mode':'must'}]}}}
    scene={'id':'scene-1','text':'原故事','start':0,'end':3,'asset':{'id':'other'},'asset_sha256':'frozen'}
    storyboard={'status':'ready','duration':3,'scenes':[scene]}
    with pytest.raises(WorkError,match='必须使用'):instrument_plan(draft,storyboard)
    scene['asset']['id']='required'
    assert instrument_plan(draft,storyboard)['scene_ids']==['scene-1']
    scene['text']='删掉原文'
    with pytest.raises(WorkError,match='完整保留原文'):instrument_plan(draft,storyboard)
