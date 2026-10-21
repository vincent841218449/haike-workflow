import copy
import pytest
from backlot import studio_template_execution as execution,studio_template_auto as legacy
from backlot.work_catalog import WorkError


def contract_fixture():
    controls={k:{'minDur':3} for k in ['title','quote','media','steps','compare','number']}
    schema={'properties':{'timeline':{'properties':{'segments':{'items':{'oneOf':[
        {'properties':{'control':{'const':k}}} for k in controls]}}}}}}
    caps={'controls':controls,'styleProfiles':{'defaultProfile':'paper','profiles':{'paper':{}}}}
    c={k:k for k in ['package_sha256','release_sha256','helper_sha256','schema_sha256','capabilities_sha256']}
    c.update(version='2.7.11',template_id='template-02-expanded-portrait',layout='portrait',style='motiongit-608-v2-7-11',validated_execution_modes=['components'])
    return c,schema,caps


def test_new_auto_contract_exposes_real_declared_controls_and_rejects_unverified_package():
    c,schema,caps=contract_fixture();value=execution.contract(c,schema,caps)
    assert set(value['controls'])==set(caps['controls'])
    assert value['compiler']==execution.VERSION and value['compiler']!=legacy.VERSION
    assert value['template_ref']['style']==c['style']
    with pytest.raises(WorkError):execution.contract({**c,'validated_execution_modes':[]},schema,caps)


def test_frozen_old_snapshot_is_exact_legacy_compiler_not_migrated(monkeypatch):
    d={'input':{'motion':{'style':'motiongit-612-v2-5-7'}}}
    frozen={'compiler':legacy.VERSION,'compiler_sha256':'unchanged-source'}
    monkeypatch.setattr(legacy,'snapshot',lambda draft:frozen)
    assert execution.snapshot(d) is frozen


def test_new_director_keeps_original_template_text_and_source_clock(monkeypatch,tmp_path):
    from backlot import studio_motiongit as author
    d={'text':'不是承诺收益。','input':{'templateExecution':'auto','motion':{'style':'motiongit-608-v2-7-11'},'templateRef':{'fingerprint':'source'}}}
    before=copy.deepcopy(d);cues=[{'startMs':150,'endMs':4200,'text':d['text']}]
    def selected(studio,current,folder,clock,board,**kw):
        assert current['input']['templateExecution']=='components'
        assert current['input']['templateRef']==d['input']['templateRef'] and current['text']==d['text']
        assert clock is cues and kw['caption_cues'] is cues
        return ['source-grounded-timeline']
    monkeypatch.setattr(author,'select',selected)
    assert execution.select(None,d,tmp_path,cues,{},cues)==['source-grounded-timeline']
    assert d==before


def test_poster_auto_director_uses_author_integrated_palette_variants(monkeypatch,tmp_path):
    from backlot import studio_motiongit as author
    from backlot.studio_motiongit_poster import AUTO_EXPRESSIONS
    d={'text':'用户原文','input':{'templateExecution':'auto','motion':{'style':'motiongit-624-v2-7-10'}}}
    monkeypatch.setattr(execution,'snapshot',lambda d:{'component_scope':AUTO_EXPRESSIONS})
    def selected(*args,**kwargs):
        assert kwargs['component_scope']==AUTO_EXPRESSIONS
        assert 'highlight' not in kwargs['component_scope']
        return []
    monkeypatch.setattr(author,'select',selected)
    assert execution.select(None,d,tmp_path,[],{},[])==[]


def test_unintegrated_poster_variant_is_rejected_even_if_model_or_cache_selects_it():
    from backlot.studio_motiongit import validate_component_scope
    from backlot.studio_motiongit_poster import AUTO_EXPRESSIONS
    for segment in [{'control':'highlight','variant':'underline'},
                    {'control':'kinetic','variant':'beat'},{'control':'kinetic'}]:
        with pytest.raises(WorkError,match='已适配'):
            validate_component_scope({'segments':[segment]},AUTO_EXPRESSIONS)
    validate_component_scope({'segments':[{'control':'kinetic','variant':'wave'}]},AUTO_EXPRESSIONS)
