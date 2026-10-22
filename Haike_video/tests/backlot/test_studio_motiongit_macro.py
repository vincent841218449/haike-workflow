import pytest
from backlot.studio_motiongit_macro import groups, validate, params
from backlot.work_catalog import WorkError


def fixture():
    text='模板保留原生动作。'
    group={'id':'03-A:claim','minFrames':60,'slots':[{'id':'title','type':'text','required':True}],
        'profile':{'intents':['claim'],'requiredPhases':['point'],'cardinality':{},'cueRoles':{'cue':'point'}}}
    guide={'groups':[group,{**group,'id':'03-X:universal-statement'}]}
    draft={'text':text,'input':{'motion':{'layout':'portrait'}}}
    segment={'group':group['id'],'text':text,'from_cue':0,'to_cue':0,'values':{'title':'原生动作'},'anchors':{'point':0},
        'semantics':{'intent':{'value':'claim','quote':text},'phases':[{'name':'point','quote':text}],
            'counts':{},'support':{'title':[text]}}}
    return draft,guide,[segment],[{'startMs':0,'endMs':2000,'clock':'word'}],{'duration':2,'scenes':[]}


def test_macro_preserves_complete_source_ownership_and_real_action_clock():
    draft,guide,segments,cues,storyboard=fixture()
    selected=validate(draft,segments,cues,storyboard,guide)
    brief=params(draft,selected,guide,{},2)
    assert ''.join(u['text'] for u in brief['contentEvidence']['units'])==draft['text']
    assert brief['segments'][0]['anchors']=={'point':{'at':0}}
    assert brief['segments'][0]['durationFrames']==120
    assert brief['allowedStyles']==['03-A']


def test_retained_basic_expressions_cannot_replace_selected_native_choreography():
    draft,guide,segments,cues,storyboard=fixture()
    assert '03-X:universal-statement' not in groups(guide)
    segments[0]['group']='03-X:universal-statement'
    with pytest.raises(WorkError):validate(draft,segments,cues,storyboard,guide)


def test_unvalidated_native_caption_adapter_never_stages_or_runs_media(tmp_path,monkeypatch):
    from backlot import studio_motiongit as motion
    monkeypatch.setattr(motion,'installed',lambda *a:pytest.fail('must stop before runtime or media'))
    with pytest.raises(WorkError,match='字幕接口尚待本地验收'):
        motion.make_plan(None,{},tmp_path/'instance',None,None,[],{'workflow':'macro','segments':[]})
    assert not (tmp_path/'instance').exists()


@pytest.mark.parametrize('mutation',['script','clock','field','foreign-media'])
def test_macro_rejects_rewritten_script_guessed_word_clock_and_unowned_media(mutation):
    draft,guide,segments,cues,storyboard=fixture()
    if mutation=='script':segments[0]['text']='改写后的台词。'
    if mutation=='clock':cues[0]['clock']='sentence'
    if mutation=='field':segments[0]['values']['arbitrary_path']='/tmp/injected'
    if mutation=='foreign-media':
        guide['groups'][0]['slots'].append({'id':'evidence','type':'video'})
        segments[0]['values']['evidence']={'asset':'not-owned','offset':0}
    with pytest.raises(WorkError):validate(draft,segments,cues,storyboard,guide)
