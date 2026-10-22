import copy
import pytest
from backlot import studio_template_auto as auto
from backlot.work_catalog import WorkError


@pytest.fixture
def package():
    controls={k:{'minDur':3} for k in ('title','quote','media')}
    caps={'controls':controls,'styleProfiles':{'defaultProfile':'paper','profiles':{'paper':{}}}}
    definitions=[{'type':'object','required':['control','props','t0','t1'],
        'properties':{'control':{'const':k},'props':{'type':'object'}}} for k in controls]
    schema={'properties':{'timeline':{'properties':{'segments':{'items':{'oneOf':definitions}}}}}}
    config={k:k for k in ('package_sha256','release_sha256','helper_sha256','schema_sha256','capabilities_sha256')}
    config.update(version='2.5.7',template_id='template-02-expanded-portrait',layout='portrait',
                  style='motiongit-test',validated_execution_modes=['components'])
    return config,schema,caps


def episode():
    texts=['各位老板，我问一个问题。','不是所有项目都能回本。','目标是三个月，不是承诺。','先看真实成本，再做决定。']
    cues=[{'startMs':i*5000,'endMs':(i+1)*5000-100,'text':t} for i,t in enumerate(texts)]
    draft={'id':'studio-check','text':''.join(texts),'input':{'templateExecution':'auto',
        'motion':{'style':'motiongit-test','layout':'portrait'},'ai':{'materials':[]}}}
    return draft,cues,{'duration':20,'scenes':[]}


def test_story_preserves_full_text_negation_profile_and_actual_clock_without_cardinalities(package):
    draft,cues,board=episode()
    result=auto.select(draft,cues,board,*package)
    assert ''.join(s['$text'] for s in result)==draft['text']
    assert result[0]['t0']==0 and result[-1]['t1']==20
    assert all(a['t1']==b['t0'] for a,b in zip(result,result[1:]))
    assert all(s['styleProfile']=='paper' for s in result)
    assert all(s['props'].get('text',s['props'].get('line1','')) in draft['text'] for s in result)
    assert any('不是承诺' in s['props'].get('text','') for s in result)
    assert result[0]['control']=='title'


def test_caption_boundaries_preserve_punctuation_without_guessing_word_times(package):
    draft,cues,board=episode();cues[1]['startMs']=5321;cues[0]['endMs']=5200
    result=auto.select(draft,cues,board,*package)
    assert result[0]['t1']==5.321 and result[1]['t0']==5.321
    assert ''.join(s['$text'] for s in result)==draft['text']
    wrong=copy.deepcopy(cues);wrong[1]['startMs']=1000
    with pytest.raises(WorkError,match='重叠'):auto.select(draft,wrong,board,*package)
    with pytest.raises(WorkError):auto.select(draft,[],board,*package)


def test_required_media_is_bound_to_owned_id_before_optional_media(package):
    draft,cues,board=episode()
    draft['input']['ai']['materials']=[{'id':'must','mode':'must'}]
    board['scenes']=[{'asset':{'id':'prefer','mode':'prefer'}},{'asset':{'id':'must','mode':'must','offset':2}}]
    result=auto.select(draft,cues,board,*package)
    assert result[0]['props']['src']=='asset:must'
    assert result[0]['props']['sourceStart']==2
    assert result[0]['$framing']['role']=='evidence'
    assert result[1]['props']['src']=='asset:prefer'
    assert ''.join(s['$text'] for s in result)==draft['text']


def test_precheck_is_local_replayable_and_rejects_changed_inputs_before_spending(tmp_path,monkeypatch,package):
    from backlot import studio_motiongit as m
    from backlot.studio_storyboard import TrialRelay
    monkeypatch.setattr(m,'contracts',lambda style:package)
    monkeypatch.setattr(TrialRelay,'call',lambda *a,**k:pytest.fail('cannot call a model'))
    draft,_,_=episode()
    first=m.precheck(None,draft,tmp_path)
    assert first==m.precheck(None,draft,tmp_path) and first['paid_calls']==0
    draft['text']+='修改'
    with pytest.raises(WorkError,match='输入已改变'):m.precheck(None,draft,tmp_path)


def test_required_media_can_use_additional_real_sentence_boundaries(package):
    draft,cues,board=episode()
    cues[1].update(startMs=3100,endMs=6900)
    cues[0]['endMs']=3000
    cues[2].update(startMs=7100,endMs=10900)
    cues[3].update(startMs=11100,endMs=19900)
    materials=[{'id':str(i),'mode':'must'} for i in range(4)]
    draft['input']['ai']['materials']=materials
    board['scenes']=[{'asset':m} for m in materials]
    result=auto.select(draft,cues,board,*package)
    assert [r['props']['src'] for r in result]==['asset:0','asset:1','asset:2','asset:3']
    assert [r['t0'] for r in result]==[0,3.1,7.1,11.1]
    assert ''.join(s['$text'] for s in result)==draft['text']


def test_contract_cannot_enable_other_versions_or_unvalidated_packages(package):
    config,schema,caps=package
    auto.contract(config,schema,caps)
    with pytest.raises(WorkError):auto.contract({**config,'version':'2.5.2'},schema,caps)
    with pytest.raises(WorkError):auto.contract({**config,'validated_execution_modes':['native']},schema,caps)
    del caps['controls']['quote']
    with pytest.raises(WorkError,match='缺少自动制作合同'):auto.contract(config,schema,caps)


def test_automatic_completion_cannot_claim_native_or_another_template():
    from backlot.studio_presentation import verify
    d={'input':{'motion':{'style':'04-A','layout':'portrait'},'templateExecution':'auto'}}
    verify(d,{'id':'adu:04-A:portrait','variant':'motion-kit'})
    with pytest.raises(WorkError):verify(d,{'id':'adu:04-A:portrait','variant':'native'})
    with pytest.raises(WorkError):verify(d,{'id':'adu:03-A:portrait','variant':'motion-kit'})


def test_auto_parent_reuses_cached_media_and_keeps_planning_clock_when_subtitles_are_off(tmp_path,monkeypatch):
    from backlot import studio_avatar as producer, studio_motiongit as motion, studio_storyboard as planning
    from backlot.studio import Studio
    studio=Studio(tmp_path/'projects');draft,cues,board=episode()
    draft['input'].update(subtitles=False,soundMode='voice',voiceId='haike/cosyvoice')
    project=studio.projects_root/draft['id'];folder=project/'renders/test'
    folder.mkdir(parents=True);audio=folder/'narration.wav';audio.write_bytes(b'cached-audio')
    (folder/'avatar-source.mp4').write_bytes(b'cached-presenter')
    monkeypatch.setattr(auto,'snapshot',lambda d:{'compiler':'frozen-test'})
    monkeypatch.setattr(producer,'captions',lambda *a:cues)
    monkeypatch.setattr(producer,'clock_captions',lambda *a:cues)
    monkeypatch.setattr(planning,'produce',lambda *a:pytest.fail('must not invoke remote storyboard or acquisition'))
    observed=[]
    def prepare(s,d,f,a,c,b,caption_cues,**kw):
        assert b['workflow']==auto.VERSION and c==cues and caption_cues==cues
        return {'mode':'motiongit','segments':['frozen-scenes'],'notice':''}
    monkeypatch.setattr('backlot.studio_preflight.prepare',prepare)
    def compose(s,d,f,v,a,caption_cues,segments,**kw):
        assert d['text']==draft['text'] and caption_cues==cues and segments==['frozen-scenes']
        observed.append('local-compose')
        return {'status':'completed','result':{'presentation':{}}}
    monkeypatch.setattr(motion,'compose',compose)
    monkeypatch.setattr('backlot.studio_presentation.verify_native',lambda *a,**kw:None)
    monkeypatch.setattr('backlot.studio_presentation.verify',lambda *a,**kw:None)
    monkeypatch.setattr('backlot.studio_presentation.selected',lambda d:{})
    class NoPaidCalls:
        def __getattr__(self,key):pytest.fail('paid endpoint accessed: '+key)
    request={'id':'local-test','draft':draft,'render_id':'test','key_identity':producer.key_identity(studio),
        'automatic_template_execution':{'compiler':'frozen-test'},'template_ref':{},'presentation':{},'workflow_version':4,
        'asr':{'provider':'test-cached'},'quotes':{},'prepared':{'audio_path':str(audio),'audio_file':'cached-audio-id','duration':20}}
    # Supply the existing ASR receipt via the paid() cache path; never call a provider.
    from backlot.studio import atomic_private
    atomic_private(folder/'gateway-state.json',{'prepared':request['prepared'],
        'stages':{'asr':{'job':{'status':'succeeded','result':{}}}}})
    request['local_recomposition']=True
    assert producer.run_avatar(project,request,NoPaidCalls())['status']=='completed'
    assert producer.run_avatar(project,request,NoPaidCalls())['status']=='completed'
    assert observed==['local-compose','local-compose']
    request['automatic_template_execution']={'compiler':'changed'}
    result=producer.run_avatar(project,request,NoPaidCalls())
    assert result['status']=='awaiting_human' and result['error']['code']=='template_mismatch'
