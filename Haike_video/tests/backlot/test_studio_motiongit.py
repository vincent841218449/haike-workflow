"""The signed runner is local-only; media clocks and source versions are binding."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from backlot import studio_motiongit as m
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError,sha


def test_template_material_never_inherits_a_different_package_profile():
    caps={'styleProfiles':{'defaultProfile':'paper','profiles':{'paper':{'description':'暖纸绿色墨水'}}}}
    assert m.component_profile({},caps)=='paper'
    assert m.component_profile({'style_profile':'paper'},caps,'paper')=='paper'
    with pytest.raises(WorkError,match='不属于当前模板'):
        m.component_profile({'style_profile':'console'},caps)
    with pytest.raises(WorkError):m.component_profile({},caps,'dark')


@pytest.mark.parametrize('layout,geometry',[('portrait','720:1280'),('landscape','1280:720')])
def test_native_mother_preserves_selected_aspect_instead_of_padding_into_portrait(layout,geometry):
    assert m.mother_filter(layout)==f'scale={geometry}:force_original_aspect_ratio=decrease,pad={geometry}:(ow-iw)/2:(oh-ih)/2,fps=60'
    with pytest.raises(WorkError):m.mother_filter('square')


def test_new_package_cannot_resume_an_unbound_old_instance(tmp_path,monkeypatch):
    atomic_private(tmp_path/'motiongit-source.json',{})
    with pytest.raises(WorkError,match='缺少精确来源绑定'):
        m.new_instance({'style':'motiongit-611-v2-5-7'},tmp_path)


def test_component_validation_cannot_enable_unvalidated_native_production(monkeypatch):
    from backlot.studio_template_registry import resolve
    config={'production_ready':False,'validated_execution_modes':['components']}
    assert m.execution_modes(config)==['components']
    monkeypatch.setattr(m,'installed',lambda style:config)
    with pytest.raises(WorkError,match='这一制作方式尚未完成'):
        resolve({'input':{'motion':{'style':'motiongit-608-v2-5-7','layout':'portrait'},'templateExecution':'native'}})
    assert m.execution_modes({'production_ready':False})==[]


def test_sentence_narration_map_retains_negation_and_measured_intervals():
    segments=[{'t0':0,'t1':3,'control':'quote','$text':'不是所有人都需要。'},
              {'t0':3,'t1':6,'control':'quote','$text':'有条件时才使用。','$purpose':'summary'}]
    captions=[{'s':.2,'e':2.8,'text':'不是所有人都需要。'},{'s':3.2,'e':5.7,'text':'有条件时才使用。'}]
    rows=m.narration_map(segments,captions)
    assert rows[0]['spokenText']==segments[0]['$text']
    assert rows[0]['beats']==[{'at':.2,'until':2.8,'spokenText':'不是所有人都需要。','timing':'sentence','target':'quote'}]
    assert rows[1]['purpose']=='summary' and rows[1]['captionIndices']==[1]
    # A word-based shot cut must not silently split or retime a sentence cue.
    segments[0]['t1']=2;segments[1]['t0']=2
    with pytest.raises(WorkError,match='切开'):m.narration_map(segments,captions)
    with pytest.raises(WorkError,match='归属缺失'):m.narration_map([],captions)


def test_template_names_correspond_without_renaming_the_frozen_identity():
    from backlot.studio_template_names import motiongit_label
    assert motiongit_label('template-03-native-portrait','作者名称')=='03-A · 多屏展陈'
    assert motiongit_label('template-04-dark-console','作者名称')=='04-A · 仪器台演示'
    assert motiongit_label('template-01-integrated','作者名称')=='01 · 现代图文'


def test_local_adapter_does_not_expose_generation_or_online_registration(tmp_path):
    for operation in ['submit','api','production','register','update','setup','python','sh']:
        with pytest.raises(WorkError,match='本地模板制作'):m.command({},tmp_path,operation)


def test_changed_original_package_is_rejected_before_running_any_code(tmp_path,monkeypatch):
    package=tmp_path/'original.motion';package.write_bytes(b'verified-archive')
    helper=tmp_path/'motion.mjs';helper.write_bytes(b'official-helper')
    schema=tmp_path/'schema.json';schema.write_text('{}')
    caps=tmp_path/'caps.json';caps.write_text('{}')
    config={k:str(v) for k,v in [('package',package),('helper',helper),('schema',schema),('capabilities',caps)]}
    config.update({k+'_sha256':sha(Path(v)) for k,v in list(config.items())})
    monkeypatch.setattr(m,'configuration',lambda:{m.STYLE:config})
    assert m.installed()==config
    package.write_bytes(b'different-release')
    with pytest.raises(WorkError,match='已变化'):m.installed()


def test_unvalidated_package_cannot_bypass_disabled_card_through_creation_api(monkeypatch):
    from backlot.studio_template_registry import resolve
    monkeypatch.setattr(m,'installed',lambda style:{'production_ready':False})
    with pytest.raises(WorkError,match='未提交收费调用'):
        resolve({'input':{'motion':{'style':m.STYLE,'layout':'portrait'}}})


@pytest.mark.parametrize('tail_sample,accepted',[(0,True),(2000,False)])
def test_missing_provider_frame_never_freezes_person_or_cuts_audible_speech(tmp_path,monkeypatch,tail_sample,accepted):
    audio=tmp_path/'source.wav';video=tmp_path/'source.mp4';video.write_bytes(b'video-fixture')
    with wave.open(str(audio),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000)
        wav.writeframes(b'\x10\x00'*round(7.94*24000)+int(tail_sample).to_bytes(2,'little',signed=True)*round(.06*24000))
    original=sha(audio)
    schema=tmp_path/'schema.json';schema.write_text('{"properties":{"workflow":{}}}')
    monkeypatch.setattr(m,'installed',lambda:{'schema':str(schema)})
    def new(config,root):root.mkdir(parents=True)
    monkeypatch.setattr(m,'new_instance',new)
    monkeypatch.setattr(m,'command',lambda *a,**k:{'ready':True})
    monkeypatch.setattr('backlot.studio_render.media_probe',lambda p:{'duration':8.,'video':{'duration':'7.96'}} if Path(p)==video else {'duration':8.})
    draft={'id':'source','text':'原文','input':{'motion':{'style':m.STYLE,'layout':'portrait'},'music':{'mode':'none'}}}
    root=tmp_path/'instance'
    if accepted:
        m.make_plan(None,draft,root,video,audio,[],[])
        alignment=json.loads((root/'clock-alignment.json').read_text())
        assert alignment['person_freeze'] is False and alignment['speech_speed']==1
        assert 0<alignment['quiet_tail_trim_ms']<=60
        with wave.open(str(root/'input-staging/narration.wav')) as wav:assert wav.getframerate()==48000
    else:
        with pytest.raises(WorkError,match='原声仍有内容'):m.make_plan(None,draft,root,video,audio,[],[])
    assert sha(audio)==original


def test_export_never_contains_personal_envelope_or_unlocked_runtime(tmp_path):
    import zipfile
    for name in ['inputs/v1/params.json','inputs/v1/assets/voice.wav','plan/auto_plan.json','original.motion','personal/key.json','project/runtime.js']:
        p=tmp_path/'instance'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
    output=tmp_path/'editable.zip';m.export_project(tmp_path/'instance',output)
    with zipfile.ZipFile(output) as z:
        names=z.namelist()
        assert 'inputs/v1/params.json' in names and 'plan/auto_plan.json' in names
        assert not any(x.startswith(('personal/','project/')) or x.endswith('.motion') for x in names)


def test_export_binds_the_exact_delivered_video_and_editable_plan(tmp_path):
    import zipfile
    instance=tmp_path/'instance';instance.mkdir()
    presentation={'name':'03-A · 多屏展陈','style':'motiongit-610-v2-5-7','layout':'portrait',
        'variant':'motion-kit','template_ref':{'fingerprint':'signed-package'},
        'plan_sha256':'frozen-plan','output_sha256':'actual-final-video','private':'never-export'}
    archive=tmp_path/'editable-project.zip';m.export_project(instance,archive,presentation=presentation)
    with zipfile.ZipFile(archive) as z:
        binding=json.loads(z.read('delivery.json'))
        assert binding['output_sha256']=='actual-final-video'
        assert binding['plan_sha256']=='frozen-plan' and 'private' not in binding


def test_queue_rejects_changed_frozen_inputs(tmp_path,monkeypatch):
    project=tmp_path/'projects/studio-example';instance=project/'renders/test/instance';instance.mkdir(parents=True)
    p=instance/'media.wav';p.write_bytes(b'changed')
    files={'media.wav':'old-sha'}
    request={'runtime':'motiongit','draft':{'id':project.name},'template_ref':{},'render_id':'test','instance':'instance',
             'files':files,'binding_sha256':m.digest(files)}
    monkeypatch.setattr(m,'verify_ref',lambda ref:None)
    monkeypatch.setattr(m,'finish',lambda *a,**k:pytest.fail('must not render changed media'))
    result=m.run_job(project,request)
    assert result['status']=='failed' and result['error']['code']=='template_mismatch'


def test_native_plan_requires_its_own_ready_contract_and_preview_receipts(tmp_path):
    atomic_private(tmp_path/'haike-workflow.json',{'workflow':'native'})
    plan={'status':'ready-for-review','native_contract':{'ready':True,'selectedScenes':['readme-terminal']},
          'problems':[],'duration_s':7.5,'segments':[{'start_frame':0,'end_frame_exclusive':450}]}
    atomic_private(tmp_path/'plan/plan.json',plan);atomic_private(tmp_path/'plan/review.json',{})
    m.review_plan(tmp_path)
    assert json.loads((tmp_path/'plan/plan.json').read_text())['reviewed'] is True
    assert m.plan_info(tmp_path)['segments'][0]['recipe']=='readme-terminal'
    assert m.preview_stills({'stills':[{'path':'stills/one.png','sha256':'actual'}]})=={'stills/one.png':'actual'}
    plan['native_contract']['ready']=False;atomic_private(tmp_path/'plan/plan.json',plan)
    with pytest.raises(WorkError,match='尚未通过'):m.review_plan(tmp_path)


def test_unreceipted_or_changed_video_cannot_be_stamped_as_current_native_output(tmp_path):
    plan=tmp_path/'plan.json';plan.write_text('actual-plan')
    candidate=tmp_path/'video.mp4';candidate.write_bytes(b'actual-render')
    report={'plan_path':plan};ref={'fingerprint':'frozen-author-package'}
    assert not m.verified_candidate(candidate,tmp_path,report,ref)
    atomic_private(tmp_path/'qa.json',{'presentation':{'template_ref':ref,'plan_sha256':sha(plan),'output_sha256':sha(candidate)}})
    assert m.verified_candidate(candidate,tmp_path,report,ref)
    # Delivery loudness may change AAC bytes; the official render remains a
    # separately frozen source and must not trigger a second full render.
    atomic_private(tmp_path/'qa.json',{'presentation':{'template_ref':ref,'plan_sha256':sha(plan),
        'output_sha256':'normalized-delivery','render_source_sha256':sha(candidate)}})
    assert m.verified_candidate(candidate,tmp_path,report,ref)
    candidate.write_bytes(b'different-video')
    assert not m.verified_candidate(candidate,tmp_path,report,ref)


def test_native_review_covers_both_official_preview_layers_and_real_still_bytes(tmp_path):
    instance=tmp_path/'instance';project=instance/'project';engineering=project/'project';engineering.mkdir(parents=True)
    frame=engineering/'stills/frame.png';frame.parent.mkdir();frame.write_bytes(b'actual-rendered-frame')
    code=engineering/'scene.js';code.write_text('frozen-official-scene')
    atomic_private(instance/'haike-workflow.json',{'workflow':'native'})
    inner={'schema':'motiongit-preview/1','reviewed':False,'projectHashes':{'scene.js':sha(code)},
        'stills':[{'path':'stills/frame.png','sha256':sha(frame)}]}
    atomic_private(engineering/'preview.json',inner)
    outer={'reviewed':False,'stills':[{'path':'project/stills/frame.png','sha256':sha(frame)}]}
    atomic_private(project/'preview.json',outer)
    atomic_private(instance/'visual-review.json',{'approved':True,'issues':[],'preview_sha256':sha(project/'preview.json')})
    m.visual_review(None,{},instance)
    assert json.loads((engineering/'preview.json').read_text())['reviewed'] is True
    missing=json.loads((engineering/'preview.json').read_text());missing.pop('projectHashes')
    atomic_private(engineering/'preview.json',missing)
    with pytest.raises(WorkError,match='工程指纹'):
        m.visual_review(None,{},instance)
    atomic_private(engineering/'preview.json',inner)
    frame.write_bytes(b'changed-after-preview')
    with pytest.raises(WorkError,match='预览图片'):
        m.visual_review(None,{},instance)


def test_long_timeline_review_samples_every_scene_including_the_final_ones():
    ranges=[(i*4,(i+1)*4) for i in range(30)]
    times=m.preview_times(ranges,120)
    assert len(times)<=40
    assert all((a+b)/2 in times for a,b in ranges)
    assert 0 in times and round(120-1/60,3) in times
