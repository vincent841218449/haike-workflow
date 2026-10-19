import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from backlot.studio import Studio, atomic_private
from backlot.studio_storyboard import TrialRelay, options, resolve_scene, status, validate_plan, produce, verify_spoken_script, motion_clock_segments, image_identity
from backlot.work_catalog import WorkError


@pytest.fixture
def data(tmp_path):
    s = Studio(tmp_path / 'projects')
    config={'base_url':'https://supplier.example/v1','api_key':'test-private-value','image_verified':True,'chat_route':'direct'}
    config['image_verified_for']=image_identity(config)
    atomic_private(s.private / 'studio-ai/relay.json', config)
    d = s.save_draft({'template_id':'avatar-safe-circle-v1','title':'测试','text':'第一句。第二句。','input':{'ai':{'enabled':True,'materials':[],'allow_images':True,'max_images':2}}})
    cues = [{'text':'第一句。','startMs':20,'endMs':1500},{'text':'第二句。','startMs':1700,'endMs':3100}]
    raw = {'scenes':[{'from_cue':0,'to_cue':0,'script_start':0,'script_end':4,'label':'第一镜','asset_id':'','query':'technology','illustration_prompt':'示意插画','reason':'缺少可用用户素材'},
                     {'from_cue':1,'to_cue':1,'script_start':4,'script_end':8,'label':'第二镜','asset_id':'','query':'computer','illustration_prompt':'示意插画','reason':'缺少可用用户素材'}]}
    return s,d,cues,raw


def test_server_binds_contiguous_real_clock(data):
    s,d,cues,body = data
    scenes = validate_plan(body,d,cues,3.2)
    assert [(x['start'],x['end']) for x in scenes] == [(0,1.7),(1.7,3.2)]
    assert ''.join(x['text'] for x in scenes) == d['text']
    assert status(s)['customer_charge_micros'] == '0' and status(s)['procurement_price'] is None
    assert 'test-private-value' not in json.dumps(status(s))


@pytest.mark.parametrize('sound_mode', ['audio','voice'])
def test_storyboard_binds_original_text_to_asr_instead_of_model_character_counts(data, tmp_path, monkeypatch, sound_mode):
    from backlot.studio_storyboard import make_plan
    s, d, cues, body = data
    d['input']['soundMode']=sound_mode
    if sound_mode=='voice':
        monkeypatch.setattr('backlot.studio_audio_check.assess',lambda *a:pytest.fail('TTS storyboard must not assess content'))
    body['scenes'][0]['script_end'] = 99
    body['scenes'][1].update(script_start=100, script_end=200)
    response = {'choices': [{'message': {'content': json.dumps(body)}}]}
    calls = []
    relay = SimpleNamespace(folder=tmp_path, call=lambda *args: calls.append(args) or response)
    plan = make_plan(s, d, cues, 3.2, relay)
    assert ''.join(scene['text'] for scene in plan['scenes']) == d['text']
    assert [(scene['script_start'], scene['script_end']) for scene in plan['scenes']] == [(0, 4), (4, 8)]
    assert [(scene['start'], scene['end']) for scene in plan['scenes']] == [(0, 1.7), (1.7, 3.2)]
    assert len(calls) == 1


def test_storyboard_does_not_hide_invalid_cue_ranges_as_json_parse_errors(data, tmp_path):
    from backlot.studio_storyboard import make_plan
    s, d, cues, body = data
    body['scenes'][1]['from_cue'] = 0
    relay = SimpleNamespace(folder=tmp_path, call=lambda *_: {'choices': [{'message': {'content': json.dumps(body)}}]})
    with pytest.raises(WorkError, match='连续覆盖'):
        make_plan(s, d, cues, 3.2, relay)


def test_script_binding_preserves_punctuation_and_newlines(data):
    from backlot.studio_storyboard import bind_script_ranges
    _, d, cues, body = data
    d['text'] = '第一句。\n第二句。'
    cues[0]['text'] = '第一句'
    cues[1]['text'] = ' 第二句'
    scenes = validate_plan(bind_script_ranges(body, d, cues), d, cues, 3.2)
    assert [scene['text'] for scene in scenes] == ['第一句。\n', '第二句。']


def test_script_binding_blocks_a_boundary_without_a_source_anchor(data):
    from backlot.studio_storyboard import bind_script_ranges
    _, d, cues, body = data
    cues = [cues[0], {'text': '错', 'startMs': 1700, 'endMs': 1800}, {'text': '二句', 'startMs': 1800, 'endMs': 3100}]
    body['scenes'][1]['to_cue'] = 2
    with pytest.raises(WorkError, match='安全对齐'):
        bind_script_ranges(body, d, cues)


def test_storyboard_uses_asr_sentence_clock_not_caption_wrap_interpolation():
    from backlot.studio_avatar import captions
    result={'segments':[{'start':.25,'end':4.9,'text':'这是一句超过十八个字的长口播用于确认真实句级时钟没有被按字数拆开。'}]}
    assert len(captions(result,5))>1
    exact=captions(result,5,split=False)
    assert len(exact)==1 and exact[0]['startMs']==250 and exact[0]['endMs']==4900


def test_real_audio_and_script_must_describe_same_speech():
    verify_spoken_script('海客科技，让创作更简单。',[{'text':'海客科技让创作更简单'}])
    with pytest.raises(WorkError,match='不一致'):
        verify_spoken_script('今天讲工业生产流程',[{'text':'用户素材优先缺少素材再补充示意插画'}])


@pytest.mark.parametrize('text', ['各位老板我问一个问题你们不用回答。', '我今天带来的不是什么大项目恰恰相反。', '这笔结算款拖欠了整整十四个月共1000万元。'])
def test_word_captions_keep_real_boundaries_without_single_character_tail(text):
    from backlot.studio_avatar import captions
    words = [{'text': char, 'start': i*.1, 'end': (i+1)*.1} for i, char in enumerate(text)]
    source = {'segments': [{'start': 0, 'end': len(words)*.1, 'text': text, 'words': words}]}
    result = captions(source, len(words)*.1)
    assert ''.join(c['text'] for c in result) == text
    assert all(len(c['text'].strip('，。')) >= 5 for c in result)
    assert all(c['startMs'] in [w['start']*1000 for w in words] and c['endMs'] in [w['end']*1000 for w in words] for c in result)
    if '1000' in text: assert any('1000' in c['text'] for c in result)


def test_25fps_drive_is_mapped_to_observed_60fps_tail():
    segments=[{'text':'一','end':1.73},{'text':'二','end':5.12}]
    result=motion_clock_segments(segments,308)
    assert result[0]['end']==104/60 and result[-1]['end']==308/60
    assert ''.join(s['text'] for s in result)=='一二'
    with pytest.raises(WorkError,match='过短'):motion_clock_segments([{'end':.001},{'end':5.12}],308)


@pytest.mark.parametrize('change',[{'from_cue':1},{'to_cue':9},{'script_start':2},{'asset_id':'foreign'},{'path':'../../etc/passwd'},{'from_cue':False}])
def test_invalid_plan_never_reaches_renderer(data,change):
    _,d,cues,body=data; body['scenes'][0].update(change)
    with pytest.raises(WorkError): validate_plan(body,d,cues,3.2)


def test_must_and_reference_materials_are_enforced(data):
    _,d,cues,body=data
    d['input']['ai']['materials']=[{'id':'local','mode':'must'}]
    with pytest.raises(WorkError,match='遗漏'): validate_plan(body,d,cues,3.2)
    body['scenes'][0]['asset_id']='local'
    assert validate_plan(body,d,cues,3.2)[0]['asset_id']=='local'
    d['input']['ai']['materials'][0]['mode']='reference'
    with pytest.raises(WorkError,match='仅供参考'): validate_plan(body,d,cues,3.2)


def test_materials_require_ownership_and_rights(data):
    s,d,_,_=data; b=io.BytesIO();Image.new('RGB',(300,300)).save(b,format='PNG')
    a=s.save_asset(d['id'],'test.png','image',b.getvalue())
    d['input']['ai']['materials']=[{**a,'mode':'prefer','rights_confirmed':False}]
    with pytest.raises(WorkError,match='使用权'): options(s,d)
    d['input']['ai']['materials'][0]['rights_confirmed']=True
    assert options(s,d)
    other=s.save_draft({'template_id':'avatar-safe-circle-v1','title':'其他','input':{}})
    other['input']['ai']=d['input']['ai']
    with pytest.raises(WorkError,match='不属于'): options(s,other)


def test_source_order_and_no_paid_fallback_on_login_failure():
    calls=[]
    def source(name,result):
        def run(_):calls.append(name);return result
        return run
    sources=SimpleNamespace(douyin=source('douyin',None),pexels=source('pexels',None),illustration=source('image',{'id':'generated'}))
    scene={'illustration_prompt':'test'}; ai={'allow_images':True,'max_images':2}
    assert resolve_scene(scene,ai,sources)['id']=='generated'; assert calls==['douyin','pexels','image']
    calls.clear()
    def login(_):calls.append('login');raise WorkError('登录失效','unavailable')
    sources.douyin=login
    with pytest.raises(WorkError,match='登录'):resolve_scene(scene,ai,sources)
    assert calls==['login']
    calls.clear(); resolve_scene(scene,{**ai,'skip_douyin':True},sources);assert calls==['pexels','image']


def test_user_asset_bypasses_all_network_sources():
    def bad(_):raise AssertionError('unwanted network')
    sources=SimpleNamespace(douyin=bad,pexels=bad,illustration=bad)
    asset=resolve_scene({'asset_id':'local'},{'materials':[{'id':'local','mode':'must'}]},sources)
    assert asset['id']=='local' and asset['provenance']['source']=='user'


@pytest.mark.parametrize('observation', [{}, {'output_observation': 'no_output_files'}])
@pytest.mark.parametrize('source_status', ['empty', 'failed'])
def test_douyin_resume_searches_selected_title_in_a_fresh_collection(data, tmp_path, monkeypatch, observation, source_status):
    from pathlib import Path
    from backlot.studio_storyboard import Sources
    s, d, _, _ = data
    folder = tmp_path / 'render' / 'ai-requests'; folder.mkdir(parents=True)
    atomic_private(folder.parent / 'source-decisions.json', {'authorized_video_ids': ['selected']})
    atomic_private(folder / 'scene-1-candidates.json', {'items': [{'id': 'selected', 'title': '已确认的商务视频'}]})
    calls = []
    class FakeSource:
        def search(self, keywords, budget, **kwargs):
            calls.append((keywords, kwargs['run_id']))
            return SimpleNamespace(status=source_status, report=observation, candidates=[])
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'copy_skill/copy_skill-main/src'))
    monkeypatch.setattr('douyin_intelligence.sources.douyin.DouyinSource', FakeSource)
    monkeypatch.setattr('backlot.studio_storyboard.configuration', lambda _: {'douyin_commercial_authorized': True, 'douyin_login_confirmed': True})
    monkeypatch.setattr('backlot.studio_storyboard.crawler_config', lambda *_: {})
    source = Sources(s, d, SimpleNamespace(folder=folder), None)
    scene = {'id': 'scene-1', 'query': '泛化查询 | generic search'}
    if source_status == 'failed':
        with pytest.raises(WorkError, match='核对后恢复'):
            source.douyin(scene)
        assert len(calls) == 1
        return
    assert source.douyin(scene) is None
    assert source.douyin(scene) is None
    assert [call[0] for call in calls] == [['已确认的商务视频'], ['已确认的商务视频']]
    assert calls[0][1] != calls[1][1]


def test_selected_video_is_analyzed_once_for_all_scenes_and_can_be_rejected(data, tmp_path, monkeypatch):
    from backlot.studio_storyboard import Sources
    s,d,_,_ = data
    folder = tmp_path / 'render/ai-requests'; folder.mkdir(parents=True)
    scenes = [{'id':'scene-1','text':'工程款拖欠','label':'欠款','query':'payment'},
              {'id':'scene-2','text':'现场听众','label':'听众','query':'audience'}]
    atomic_private(folder.parent/'storyboard.json',{'scenes':scenes,'draft_fingerprint':'original'})
    path=folder/'approved.mp4'; path.write_bytes(b'authorized-video')
    calls=[]
    def call(stage, payload):
        calls.append(payload)
        return {'choices':[{'message':{'content':json.dumps({'suitable_scene_ids':['scene-2'],'reason':'画面为演讲听众，可作听众示意，不适合表现工程款拖欠'})}}]}
    monkeypatch.setattr('backlot.studio_render.media_probe',lambda _: {'duration':5})
    monkeypatch.setattr('backlot.studio_storyboard.image_preview',lambda *args:'data:image/jpeg;base64,preview')
    source=Sources(s,d,SimpleNamespace(folder=folder,call=call),None)
    item={'id':'approved','title':'用户选择的演讲片段'}
    assert source.review_selected_douyin(scenes[0],path,item) is False
    assert source.review_selected_douyin(scenes[1],path,item) is True
    assert len(calls)==1
    assert len([part for part in calls[0]['messages'][1]['content'] if part['type']=='image_url'])==3
    record=json.loads((folder.parent/'douyin-material-review.json').read_text())['approved']
    assert record['suitable_scene_ids']==['scene-2'] and record['reason']


def test_cached_douyin_candidates_are_automatically_analyzed_without_rights_prompt(data,tmp_path,monkeypatch):
    from pathlib import Path
    from backlot.studio_storyboard import Sources
    s,d,_,_=data
    folder=tmp_path/'render/ai-requests';folder.mkdir(parents=True)
    items=[{'id':str(i),'title':'候选素材'+str(i)} for i in range(10)]
    atomic_private(folder/'scene-1-candidates.json',{'items':items})
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]/'copy_skill/copy_skill-main/src'))
    class Source:
        def search(self,*args,**kwargs):raise AssertionError('Reuse saved discovery candidates')
    monkeypatch.setattr('douyin_intelligence.sources.douyin.DouyinSource',Source)
    monkeypatch.setattr('backlot.studio_storyboard.configuration',lambda _: {'douyin_commercial_authorized':True,'douyin_login_confirmed':True})
    monkeypatch.setattr('backlot.studio_storyboard.crawler_config',lambda *_:{})
    source=Sources(s,d,SimpleNamespace(folder=folder),None)
    calls=[]
    monkeypatch.setattr(source,'selected_douyin',lambda scene,selected,*args: calls.append(selected) or {'id':'chosen'})
    assert source.douyin({'id':'scene-1','query':'audience'})=={'id':'chosen'}
    assert calls==[items[:3]]


@pytest.mark.parametrize('suitable',[True,False])
def test_fresh_douyin_downloads_once_and_ai_can_reject_without_human_gate(data,tmp_path,monkeypatch,suitable):
    from pathlib import Path
    from backlot.studio_storyboard import Sources
    s,d,_,_=data
    folder=tmp_path/'render/ai-requests';folder.mkdir(parents=True)
    candidate=SimpleNamespace(video_id='video1',title='商务听众',source_url='https://www.douyin.com/video/video1',author='作者')
    calls=[]
    class Source:
        download_referer='https://www.douyin.com/'
        def search(self,keywords,*args,**kwargs):
            calls.append(keywords)
            return SimpleNamespace(status='ok',candidates=[candidate])
        def resolve_media_url(self,item):return 'https://example.test/signed-video'
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]/'copy_skill/copy_skill-main/src'))
    monkeypatch.setattr('douyin_intelligence.sources.douyin.DouyinSource',Source)
    monkeypatch.setattr('backlot.studio_storyboard.configuration',lambda _: {'douyin_commercial_authorized':True,'douyin_login_confirmed':True})
    monkeypatch.setattr('backlot.studio_storyboard.crawler_config',lambda *_:{})
    downloads=[]
    def download(url,path,**kwargs):downloads.append(url);path.write_bytes(b'video')
    monkeypatch.setattr('backlot.studio_avatar.download_result',download)
    source=Sources(s,d,SimpleNamespace(folder=folder),None)
    reviewed=[]
    monkeypatch.setattr(source,'review_selected_douyin',lambda scene,path,item:reviewed.append(item['id']) or suitable)
    monkeypatch.setattr(source,'own',lambda path,kind,provenance: {'provenance':provenance})
    scene={'id':'scene-1','query':'商务观众 | business audience'}
    result=source.douyin(scene)
    if suitable:assert result['provenance']['rights']=='operator-declared-default'
    else:assert result is None
    assert len(downloads)==1 and calls==[['商务观众']] and reviewed==['video1']
    assert 'signed-video' not in (folder/'scene-1-candidates.json').read_text()
    source.douyin(scene)
    assert len(downloads)==1 and len(calls)==1


def test_image_cap_and_explicit_opt_in():
    bad=lambda _: (_ for _ in ()).throw(AssertionError('unwanted generation'))
    sources=SimpleNamespace(douyin=lambda _:None,pexels=lambda _:None,illustration=bad)
    for ai,count in [({},0),({'allow_images':True,'max_images':1},1)]:
        with pytest.raises(WorkError,match='未找到'):resolve_scene({'illustration_prompt':'test'},ai,sources,count)


def test_trial_cached_success_and_ambiguous_request_never_repeat(data,tmp_path):
    s,_,_,_=data; calls=[]
    def ok(payload,image):calls.append(payload);return {'choices':[{'message':{'content':'{}'}}],'usage':{'prompt_tokens':2}}
    r=TrialRelay(s,tmp_path/'calls',ok); payload={'model':'gpt-6-luna'}
    assert r.call('one',payload)==r.call('one',payload);assert len(calls)==1
    with pytest.raises(WorkError,match='冻结'): r.call('one',{'model':'changed'})
    def timeout(payload,image):calls.append(payload);raise TimeoutError()
    r.transport=timeout
    with pytest.raises(WorkError,match='待核对'):r.call('unknown',payload)
    with pytest.raises(WorkError,match='未重复'):r.call('unknown',payload)
    assert len(calls)==2


def test_trial_daily_limits_are_durable(data,tmp_path):
    s,_,_,_=data
    from backlot.studio import timestamp
    atomic_private(s.private/'studio-ai/trial-budget.json',{'day':timestamp()[:10],'requests':50,'images':0})
    r=TrialRelay(s,tmp_path/'calls',lambda *_:(_ for _ in ()).throw(AssertionError()))
    with pytest.raises(WorkError,match='今日'):r.call('over-limit',{'model':'gpt-6-luna'})
    assert not list(r.folder.glob('*.json'))


def test_candidate_metadata_does_not_consume_ai_request_quota(data,tmp_path):
    s,_,_,_=data
    relay=TrialRelay(s,tmp_path/'requests',transport=lambda *_:{'choices':[{'message':{'content':'ok'}}]})
    for i in range(12):atomic_private(relay.folder/f'scene-{i}-candidates.json',{'items':[]})
    assert relay.call('one-actual-call',{'messages':[]})['choices']


@pytest.mark.parametrize('extra',[0,13,True,1.5])
def test_ai_recovery_allowance_is_bounded_and_bound_to_original_plan(data,tmp_path,extra):
    s,_,_,_=data;relay=TrialRelay(s,tmp_path/'render/requests')
    atomic_private(relay.folder.parent/'storyboard.json',{'draft_fingerprint':'original'})
    assert relay.request_limit()==12
    atomic_private(relay.folder.parent/'ai-recovery-budget.json',{'draft_fingerprint':'original','extra_requests':extra,'reason':'local repair'})
    with pytest.raises(WorkError,match='恢复额度'):relay.request_limit()


def test_ai_recovery_allowance_does_not_reset_or_hide_consumed_requests(data,tmp_path):
    s,_,_,_=data;relay=TrialRelay(s,tmp_path/'render/requests',transport=lambda *_:{'choices':[{'message':{'content':'ok'}}]})
    atomic_private(relay.folder.parent/'storyboard.json',{'draft_fingerprint':'original'})
    for i in range(12):relay.call('existing-'+str(i),{'messages':[]})
    with pytest.raises(WorkError,match='次数上限'):relay.call('new',{'messages':[]})
    atomic_private(relay.folder.parent/'ai-recovery-budget.json',{'draft_fingerprint':'original','extra_requests':1,'reason':'local repair'})
    relay.call('new',{'messages':[]})
    assert len(relay.request_paths())==13
    with pytest.raises(WorkError,match='次数上限'):relay.call('beyond',{'messages':[]})
    atomic_private(relay.folder.parent/'storyboard.json',{'draft_fingerprint':'different'})
    with pytest.raises(WorkError,match='恢复额度'):relay.request_limit()


def test_cached_visual_review_reuses_only_matching_plan_media_and_scene(data,tmp_path,monkeypatch):
    from backlot.studio_storyboard import Sources
    from backlot.work_catalog import sha
    s,d,_,_=data
    folder=tmp_path/'render/ai-requests';folder.mkdir(parents=True)
    atomic_private(folder.parent/'storyboard.json',{'draft_fingerprint':'original'})
    path=folder/'one.mp4';path.write_bytes(b'reviewed-video')
    atomic_private(folder.parent/'pexels-material-review.json',{'one':{'review_policy':3,'sha256':sha(path),
        'draft_fingerprint':'original','filename':path.name,'suitable_scene_ids':['scene-2'],
        'provenance':{'source':'pexels','source_url':'https://example.test/one'}}})
    source=Sources(s,d,SimpleNamespace(folder=folder),None)
    monkeypatch.setattr(source,'own',lambda path,kind,provenance:{'id':'same-media','provenance':provenance})
    assert source.cached_material({'id':'scene-2'},'pexels')['id']=='same-media'
    assert source.cached_material({'id':'scene-1'},'pexels') is None
    path.write_bytes(b'changed')
    assert source.cached_material({'id':'scene-2'},'pexels') is None


def test_empty_retail_search_preserves_original_request_and_uses_distinct_fallback_intent(data,tmp_path,monkeypatch):
    from backlot.studio_storyboard import Sources
    s,d,_,_=data;folder=tmp_path/'render/requests';folder.mkdir(parents=True)
    calls=[]
    def paid(stage,model,inputs):
        calls.append((stage,inputs['query']))
        return {'items':[{'id':str(len(calls)),'video_files':[{'file_type':'video/mp4','width':640,'link':'https://test.example/video'}]}]}
    source=Sources(s,d,SimpleNamespace(folder=folder),paid)
    monkeypatch.setattr('backlot.studio_avatar.download_result',lambda url,path:path.write_bytes(b'video'))
    monkeypatch.setattr(source,'review_material',lambda scene,path,item,kind:item['id']=='2')
    monkeypatch.setattr(source,'own',lambda path,kind,provenance:{'id':'accepted'})
    assert source.pexels({'id':'scene-8','query':'空铺 | vacant neighborhood retail unit','label':'空铺'})['id']=='accepted'
    assert calls[0][0].startswith('assets-scene-8-search-') and calls[0][1]=='empty room interior'
    assert calls[1]==('assets-scene-8','vacant neighborhood retail unit')


def test_stock_media_prefers_720p_over_large_1080p_download(data,tmp_path,monkeypatch):
    from backlot.studio_storyboard import Sources
    s,d,_,_=data;folder=tmp_path/'render/requests';folder.mkdir(parents=True)
    files=[{'file_type':'video/mp4','width':1920,'height':1080,'link':'https://test.example/large'},
           {'file_type':'video/mp4','width':640,'height':360,'link':'https://test.example/small'},
           {'file_type':'video/mp4','width':1280,'height':720,'link':'https://test.example/720p'}]
    source=Sources(s,d,SimpleNamespace(folder=folder),lambda *_:{'items':[{'id':'one','video_files':files}]})
    downloads=[]
    def download(url,path):downloads.append(url);path.write_bytes(b'video')
    monkeypatch.setattr('backlot.studio_avatar.download_result',download)
    monkeypatch.setattr(source,'review_material',lambda *args:True)
    monkeypatch.setattr(source,'own',lambda *args:{'id':'accepted'})
    source.pexels({'id':'scene-1','query':'empty shop','label':'空店'})
    assert downloads==['https://test.example/720p']
    files[2]['size']=116_000_000
    files[0]['size']=201_000_000
    for f in folder.glob('*.mp4'):f.unlink()
    source.pexels({'id':'scene-1','query':'empty shop','label':'空店'})
    assert downloads[-1]=='https://test.example/small'


@pytest.mark.parametrize('change',[{'image_model':'gpt-image-1.5'}, {'api_key':'another-private-value'}, {'base_url':'https://another.example/v1'}])
def test_probe_cannot_enable_a_different_model_or_destination(data,change):
    s,d,_,_=data
    assert status(s)['image_verified']
    path=s.private/'studio-ai/relay.json'; c=json.loads(path.read_text()); c.update(change); atomic_private(path,c)
    assert not status(s)['image_verified']
    with pytest.raises(WorkError,match='尚未验收'):options(s,d)


def test_fallback_model_never_resubmits_an_unknown_original_request(data,tmp_path):
    s,_,_,_=data;calls=[]
    def failed(payload,image):calls.append(payload['model']);raise TimeoutError()
    relay=TrialRelay(s,tmp_path/'calls',failed);stage='illustration-scene-1'
    payload={'model':'gpt-image-2','prompt':'test'}
    with pytest.raises(WorkError):relay.call(stage,payload,image=True)
    path=s.private/'studio-ai/relay.json';c=json.loads(path.read_text());c.update(image_model='gpt-image-1.5');atomic_private(path,c)
    assert relay.image_model_for_stage(stage)=='gpt-image-2'
    assert relay.image_model_for_stage('illustration-scene-2')=='gpt-image-2'
    assert TrialRelay(s,tmp_path/'new-job').image_model_for_stage('illustration-scene-1')=='gpt-image-1.5'
    with pytest.raises(WorkError,match='未重复'):relay.call(stage,payload,image=True)
    assert calls==['gpt-image-2']


def test_switching_image_model_preserves_successful_receipt_identity(data,tmp_path):
    s,_,_,_=data
    relay=TrialRelay(s,tmp_path/'calls',lambda *_:{'data':[{'b64_json':'fixture'}]})
    stage='illustration-scene-1'
    relay.call(stage,{'model':'gpt-image-1.5'},image=True)
    assert relay.image_model_for_stage(stage)=='gpt-image-1.5'


def test_only_a_valid_probe_can_enable_the_configured_image_model(data,monkeypatch):
    from scripts.configure_studio_ai import verify_image
    s,_,_,_=data;path=s.private/'studio-ai/relay.json';c=json.loads(path.read_text())
    c.update(image_model='gpt-image-1.5',image_verified=False);atomic_private(path,c)
    image=io.BytesIO();Image.new('RGB',(1024,1536)).save(image,format='PNG')
    import base64
    def fake(self,stage,payload,image=False):
        assert payload['model']=='gpt-image-1.5' and image
        return {'data':[{'b64_json':base64.b64encode(image_bytes).decode()}],'usage':{'input_tokens':1,'output_tokens':2}}
    image_bytes=image.getvalue();monkeypatch.setattr(TrialRelay,'call',fake)
    verify_image(s,'one-explicit-test')
    assert status(s)['image_verified'] and status(s)['image_model']=='gpt-image-1.5'
    c=json.loads(path.read_text());c.update(image_model='gpt-image-1');atomic_private(path,c)
    with pytest.raises(ValueError,match='绑定'):verify_image(s,'one-explicit-test')


def test_unified_avatar_motion_result_is_recovered_after_restart(tmp_path):
    from backlot.production_queue_worker import ProductionQueueWorker
    root=tmp_path/'projects';output=root/'demo/renders/studio-1';output.mkdir(parents=True)
    (output/'motion-preview.mp4').write_bytes(b'test-render');(output/'qa.json').write_text('{}')
    worker=ProductionQueueWorker(None,root)
    job={'project_id':'demo','kind':'studio_avatar','frozen_request':{'render_id':'studio-1','draft':{'input':{'motion':{'style':'01-D'}}}}}
    result=worker.inspect_parent(job)
    assert result['status']=='completed' and result['result']['output_path'].endswith('motion-preview.mp4')


def test_empty_motion_selection_explains_template_mismatch_before_render(data, tmp_path, monkeypatch):
    from backlot.studio_storyboard import compose_motion
    s, d, cues, body = data
    scenes = validate_plan(body, d, cues, 3.2)
    for scene in scenes: scene['asset'] = {'id': 'owned-material', 'kind': 'video'}
    monkeypatch.setattr('backlot.studio_storyboard.motion_options', lambda *_: {'groups': [], 'id': '04-A'})
    monkeypatch.setattr(TrialRelay, 'call', lambda *_: {'choices': [{'message': {'content': '{"segments":[]}'}}]})
    with pytest.raises(WorkError, match='更换模板'):
        compose_motion(s, d, tmp_path, tmp_path / 'avatar.mp4', tmp_path / 'audio.wav', cues,
                       {'scenes': scenes, 'duration': 3.2})
    assert not (tmp_path / 'ai-motion-draft.json').exists()


def test_expired_quote_renewal_cannot_change_customer_approval():
    from backlot.studio_avatar import renew_if_expired
    q={'id':'original','model':'haike/avatar','price':{'version':1},'quoted_usage':{'tasks':1},'max_charge_micros':'100','expires_at':'2020-01-01T00:00:00+00:00'}
    calls=[]
    def request(path,body):calls.append((path,body));return {**q,'expires_at':'2099-01-01T00:00:00+00:00'}
    sdk=SimpleNamespace(request=request)
    assert renew_if_expired(sdk,q)['id']=='original' and len(calls)==1
    sdk.request=lambda *_:{**q,'max_charge_micros':'101'}
    with pytest.raises(WorkError,match='改变'):renew_if_expired(sdk,q)


def test_pipeline_resumes_completed_scenes_without_researching(data,tmp_path,monkeypatch):
    s,d,cues,body=data
    b=io.BytesIO();Image.new('RGB',(300,300)).save(b,format='PNG')
    a=s.save_asset(d['id'],'test.png','image',b.getvalue())
    plan={'scenes':validate_plan(body,d,cues,3.2),'duration':3.2}
    monkeypatch.setattr('backlot.studio_storyboard.make_plan',lambda *_:plan)
    calls=[]
    def resolve(scene,*_):
        calls.append(scene['id'])
        if len(calls)==2:raise WorkError('需要登录抖音','unavailable')
        return {**a,'provenance':{'source':'user'}}
    monkeypatch.setattr('backlot.studio_storyboard.resolve_scene',resolve)
    with pytest.raises(WorkError):produce(s,d,tmp_path/'render',cues,3.2,None)
    result=produce(s,d,tmp_path/'render',cues,3.2,None)
    assert result['status']=='ready' and calls==['scene-1','scene-2','scene-2']


def test_ready_storyboard_rerenders_offline_but_still_verifies_inputs(data,tmp_path,monkeypatch):
    import hashlib
    from backlot.work_catalog import sha
    s,d,cues,body=data
    buffer=io.BytesIO();Image.new('RGB',(300,300)).save(buffer,format='PNG')
    asset=s.save_asset(d['id'],'existing.png','image',buffer.getvalue())
    plan={'scenes':validate_plan(body,d,cues,3.2),'duration':3.2,'status':'ready',
          'draft_fingerprint':hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()}
    for scene in plan['scenes']:
        scene.update(asset=asset,asset_sha256=sha(s.asset(asset['id'],d['id'])))
    folder=tmp_path/'offline-render';folder.mkdir()
    atomic_private(folder/'storyboard.json',plan)
    (s.private/'studio-ai/relay.json').unlink()
    monkeypatch.setattr('backlot.studio_storyboard.TrialRelay',lambda *_:pytest.fail('Must not initialize remote AI for existing scenes'))
    assert produce(s,d,folder,cues,3.2,None)==plan
    s.asset(asset['id'],d['id']).write_bytes(b'changed-media')
    with pytest.raises(WorkError,match='素材发生变化'):
        produce(s,d,folder,cues,3.2,None)


def test_explicit_basic_text_scene_needs_no_random_material_and_keeps_source_clock(data,tmp_path,monkeypatch):
    import hashlib
    s,d,cues,body=data
    for scene in body['scenes']:
        scene.update(presentation='text',query='',illustration_prompt='',reason='本句是提问，使用原文文字卡')
    scenes=validate_plan(body,d,cues,3.2)
    folder=tmp_path/'text-render';folder.mkdir()
    plan={'status':'ready','duration':3.2,'scenes':scenes,'draft_fingerprint':hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()}
    atomic_private(folder/'storyboard.json',plan)
    (s.private/'studio-ai/relay.json').unlink()
    monkeypatch.setattr('backlot.studio_storyboard.TrialRelay',lambda *_:pytest.fail('Text-only rerender must stay offline'))
    assert produce(s,d,folder,cues,3.2,None)==plan
    assert ''.join(x['text'] for x in scenes)==d['text']
    assert [(x['start'],x['end']) for x in scenes]==[(0,1.7),(1.7,3.2)]
    d['input']['ai']['materials']=[{'id':'required','mode':'must'}]
    with pytest.raises(WorkError,match='必须使用'):validate_plan(body,d,cues,3.2)
    d['input']['motion']={'style':'04-A','layout':'portrait'}
    with pytest.raises(WorkError,match='原生导演'):validate_plan(body,d,cues,3.2)
