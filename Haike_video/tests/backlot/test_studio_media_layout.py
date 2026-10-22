import copy

import pytest

from backlot.studio_media_layout import kit_layout
from backlot.work_catalog import WorkError

CONTROLS={
    'media':{'props':{'src':{'type':'media'}}},
    'kenburns':{'minDur':3.5,'props':{'items':{'type':'array','of':'object','props':{'src':{'type':'media'}}}}},
}


def scene(role='footage'):
    return {'control':'media','t0':7.52,'t1':13.22,'cues':[7.52],
            'props':{'src':'owned.mp4','sourceStart':2.3,'title':'一家人等他吃饭'},
            'presenter':'card','$framing':{'role':role,'focus':{'x':.62,'y':.45}}}


def test_footage_gets_large_official_layout_without_retiming_or_losing_source_range():
    source=[scene()];original=copy.deepcopy(source);out,policies,receipt=kit_layout(source,CONTROLS)
    assert source==original
    assert out[0]['control']=='kenburns' and out[0]['variant']=='zoom' and out[0]['presenter']=='hide'
    assert {k:out[0][k] for k in ('t0','t1','cues')}=={k:source[0][k] for k in ('t0','t1','cues')}
    assert out[0]['props']['items'][0]=={'src':'owned.mp4','sourceStart':2.3,'caption':'一家人等他吃饭'}
    assert '$framing' not in out[0] and policies['owned.mp4']['fit']=='cover'
    assert policies['owned.mp4']['focus']=={'x':.62,'y':.45}


def test_screenshot_keeps_complete_evidence_and_its_annotations():
    s=scene('screenshot');s['props']['callouts']=[{'text':'结算日期','x':.4,'y':.6}]
    out,policies,_=kit_layout([s],CONTROLS)
    assert out[0]['control']=='media' and out[0]['props']==s['props']
    assert policies['owned.mp4']['fit']=='contain'


def test_cannot_drop_annotation_cut_a_qualifier_or_stretch_too_short_a_scene():
    s=scene();s['props']['callouts']=[{'text':'依据'}]
    with pytest.raises(WorkError,match='局部标注'):kit_layout([s],CONTROLS)
    s=scene();s['props']['title']='这是一条超过二十个字而且末尾还包含重要限定条件的说明'
    with pytest.raises(WorkError,match='忠实精简'):kit_layout([s],CONTROLS)
    s=scene();s['t1']=s['t0']+3
    with pytest.raises(WorkError,match='按原声合并'):kit_layout([s],CONTROLS)


def test_invalid_focus_and_conflicting_asset_roles_stop_before_render():
    s=scene();s['$framing']['role']=[]
    with pytest.raises(WorkError,match='实际画面'):kit_layout([s],CONTROLS)
    s=scene();s['$framing']['focus']['x']=float('nan')
    with pytest.raises(WorkError,match='取景焦点'):kit_layout([s],CONTROLS)
    with pytest.raises(WorkError,match='取景要求冲突'):kit_layout([scene(),scene('evidence')],CONTROLS)


def test_frozen_historical_recipe_is_not_silently_reframed():
    s=scene();s.pop('$framing')
    out,policies,receipt=kit_layout([s],CONTROLS)
    assert out==[s] and policies=={} and receipt['decisions']==[]
