import json
import pytest
from backlot.work_catalog import WorkError


def test_new_native_selection_never_calls_component_fallback(tmp_path,monkeypatch):
    from backlot import studio_motion_director as director
    from backlot import studio_adu_components as components
    from backlot.studio_storyboard import TrialRelay
    draft={'text':'两笔投入。','input':{'motion':{'style':'03-A','layout':'portrait'},'templateExecution':'native'}}
    monkeypatch.setattr('backlot.studio_storyboard.motion_options',lambda d:{'id':'03-A','groups':[]})
    monkeypatch.setattr(TrialRelay,'call',lambda *a,**k:{'choices':[{'message':{'content':json.dumps({'segments':[],'reason':'真实数量不匹配'})}}]})
    monkeypatch.setattr(components,'direct',lambda *a:pytest.fail('must not silently change execution'))
    with pytest.raises(WorkError,match='明确选择组件'):
        director.direct(None,draft,tmp_path)
    assert (tmp_path/'native-direction-blocked.json').is_file()


def test_explicit_component_execution_is_separate_and_keeps_source_lock():
    from backlot.studio_adu_components import supported
    d={'input':{'motion':{'style':'03-A','layout':'portrait'},'templateExecution':'native'}}
    assert not supported(d)
    d['input']['templateExecution']='components';assert supported(d)
    d['input']['motion']['style']='04-A';assert not supported(d)


def test_component_output_cannot_pass_native_completion_receipt():
    from backlot.studio_presentation import verify
    draft={'input':{'motion':{'style':'03-A','layout':'portrait'},'templateExecution':'native'}}
    verify(draft,{'id':'adu:03-A:portrait'},selection_only=True)
    with pytest.raises(WorkError):verify(draft,{'id':'adu:03-A:portrait'})
    with pytest.raises(WorkError,match='不能标记成功'):
        verify(draft,{'id':'adu:03-A:portrait','variant':'source-components-v1'})
    verify(draft,{'id':'adu:03-A:portrait','variant':'native'})
    verify(draft,{'id':'adu:03-A:portrait','variant':'original'})
    with pytest.raises(WorkError):verify(draft,{'id':'adu:03-A:portrait','variant':'unknown'})
    draft['input']['templateExecution']='components'
    verify(draft,{'id':'adu:03-A:portrait','variant':'source-components-v1'})
    with pytest.raises(WorkError):verify(draft,{'id':'adu:03-A:portrait','variant':'native'})
    verify({'template_id':'avatar-safe-circle-v1','input':{'templateExecution':'components'}},
           {'id':'avatar-safe-circle-v1'})


def test_native_motiongit_selection_rejects_component_timeline_before_validation():
    from backlot.studio_motiongit import validate_selection
    draft={'input':{'templateExecution':'native'}}
    with pytest.raises(WorkError,match='不能自动转为组件'):
        validate_selection(draft,{'workflow':'motion-kit','segments':[]},[],{}, {},{})


def test_motiongit_refs_bind_independent_package_identity(monkeypatch):
    from backlot import studio_motiongit as m
    base={k:k for k in ['package_sha256','release_sha256','helper_sha256','schema_sha256','capabilities_sha256','version','template_id','layout']}
    first={**base,'style':'motiongit-610-v2-5-7'}
    second={**base,'style':'motiongit-612-v2-5-7','package_sha256':'different'}
    monkeypatch.setattr(m,'installed',lambda style=m.STYLE:first if style==first['style'] else second)
    assert m.template_ref(first)['style']==first['style']
    assert m.template_ref(first)['fingerprint']!=m.template_ref(second)['fingerprint']
    m.verify_ref(m.template_ref(first))
    with pytest.raises(WorkError):m.verify_ref({**m.template_ref(first),'style':second['style']})


def test_author_catalog_never_treats_announcement_or_old_release_as_new_install(monkeypatch):
    from backlot import studio_motiongit as m
    from backlot.studio_template_registry import pending_packages
    monkeypatch.setattr(m,'configuration',lambda:{m.STYLE:{'template_id':'template-04-dark-console-portrait','version':'2.5.2','production_ready':True}})
    assert len(pending_packages())==13
    assert len(pending_packages('portrait'))==7
    assert len(pending_packages('landscape'))==6
    assert all(p['supported'] is False for p in pending_packages())
