import copy
import json
import pytest
from backlot import studio_motiongit_poster as poster
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError,sha


def fixture(root):
    (root/'plan').mkdir();(root/'inputs').mkdir();(root/'project/host-preview').mkdir(parents=True)
    params=root/'inputs/params.json';atomic_private(params,{'duration':8,'segments':[{'control':'title'}]})
    plan={'workflow':'poster-kit','parameter':'inputs/params.json','parametersSha256':sha(params),
          'inputFiles':{'voice.wav':'frozen'},'result':json.dumps({'duration':8,'segments':['title']})}
    atomic_private(root/'plan/host-plan.json',plan)
    directory=root/'project/host-preview';(directory/'t_4.png').write_bytes(b'actual preview bytes')
    atomic_private(directory/'geometry.json',{'violations':[]})
    receipt={**{k:plan[k] for k in ['workflow','parametersSha256','inputFiles']},'reviewed':False,
             'files':{n:sha(directory/n) for n in ['t_4.png','geometry.json']}}
    atomic_private(directory/'preview-review.json',receipt)
    return directory,receipt


def test_poster_uses_the_author_host_not_motion_kit_cli(tmp_path):
    assert poster.arguments(tmp_path,'plan',['params.json','--out','plan'])==[
        '--workflow','poster-kit','--timeline','params.json','--out','plan','--language','zh']
    command=poster.arguments(tmp_path,'render',['--out','final.mp4'])
    assert command[command.index('--preview-review')+1]==str(tmp_path/'project/host-preview')
    assert '--timeline' in command and '@vault' in command


def test_native_preview_binding_rejects_changed_frames_parameters_or_path_escape(tmp_path):
    directory,receipt=fixture(tmp_path)
    poster.preview_receipt(tmp_path)
    (directory/'t_4.png').write_bytes(b'changed')
    with pytest.raises(WorkError,match='文件已改变'):poster.preview_receipt(tmp_path)
    receipt['files']={'../secret.png':'a'};atomic_private(directory/'preview-review.json',receipt)
    with pytest.raises(WorkError,match='文件已改变'):poster.preview_receipt(tmp_path)
    atomic_private(tmp_path/'inputs/params.json',{'duration':9,'segments':[]})
    with pytest.raises(WorkError,match='冻结参数'):poster.plan_info(tmp_path)


def test_real_body_safety_hits_block_but_quote_ornament_is_not_body_text(tmp_path):
    directory,receipt=fixture(tmp_path)
    def geometry(text,kind):
        atomic_private(directory/'geometry.json',{'violations':[{'hits':[{'kind':kind,'text':text}]}]})
        receipt['files']['geometry.json']=sha(directory/'geometry.json')
        atomic_private(directory/'preview-review.json',receipt)
    geometry('“','safe-edge');poster.preview_receipt(tmp_path)
    geometry('完整原文','safe-edge')
    with pytest.raises(WorkError,match='安全区'):poster.preview_receipt(tmp_path)
    geometry('“','caption-overlap')
    with pytest.raises(WorkError,match='安全区'):poster.preview_receipt(tmp_path)


def test_review_stamps_are_bound_and_idempotent(tmp_path):
    directory,receipt=fixture(tmp_path);poster.preview_receipt(tmp_path)
    poster.approve_preview(tmp_path);poster.approve_preview(tmp_path)
    outer=json.loads((tmp_path/'project/preview.json').read_text())
    assert outer['host_review_sha256']==sha(directory/'preview-review.json')
    receipt['reviewed']=True;receipt['files']={};atomic_private(directory/'preview-review.json',receipt)
    with pytest.raises(WorkError,match='回执已改变'):poster.approve_preview(tmp_path)


def test_layout_preserves_all_title_characters_and_explicit_user_regions():
    original={'layout':'portrait','presenter':{'src':'talk.mp4'},'segments':[
        {'control':'title','props':{'line1':'大家好，这是海客数字人功能测试。'}},
        {'control':'media','area':{'x':10,'y':20,'w':300,'h':500},'props':{}}]}
    before=copy.deepcopy(original);result=poster.content_layout(original)
    props=result['segments'][0]['props']
    assert props['line1']+props['line2']==before['segments'][0]['props']['line1']
    assert result['segments'][1]['area']==before['segments'][1]['area']
    assert original==before
