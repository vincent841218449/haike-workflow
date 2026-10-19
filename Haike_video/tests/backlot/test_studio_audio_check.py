"""Audio preflight exercises real matching and HTTP gates, never paid providers."""
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backlot.studio import Studio
from backlot.studio_api import router
from backlot.work_catalog import WorkError


def test_old_sample_is_blocked_but_its_true_script_passes():
    from backlot.studio_audio_check import assess
    sample = '海客科技让创作更简单，一个接口连接配音数字人和创作工作流。'
    report = assess('各位老板，我问一个问题，你们不用回答，心里想下就行。去年大年三十你在哪？' * 10,
                    [{'text': sample, 'startMs': 0, 'endMs': 6560}])
    assert report['status'] == 'blocked' and report['differences']
    assert assess(sample, [{'text': sample}])['status'] == 'passed'


@pytest.mark.parametrize('spoken', ['投资100万元，目标6个月回本，不作保证。',
                                    '投资10万元，目标6个月回本，作保证。'])
def test_critical_change_does_not_pass_high_global_similarity(spoken):
    from backlot.studio_audio_check import assess
    report = assess('投资10万元，目标6个月回本，不作保证。', [{'text': spoken}])
    assert report['status'] == 'review' and report['critical_differences']


def test_number_notation_punctuation_and_one_asr_typo_are_tolerated():
    from backlot.studio_audio_check import assess
    assert assess('大家好。',[{'text':'大家好.'}])['status']=='passed'
    assert assess('投资十万元，目标六个月回本，不作保证。', [{'text':'投资10万元目标6个月回本不作保证'}])['status'] == 'passed'
    assert assess('大家好，这是海客数字人功能测试。画面是否符合所选模板，声音和字幕是否同步。',
                  [{'text':'大家好这是海客数字人功能测试画面是否符合锁选模板声音和字幕是否同步'}])['status'] == 'passed'


def test_missing_whole_sentence_and_low_confidence_are_not_auto_passed():
    from backlot.studio_audio_check import assess
    first='今天我们介绍海客数字人的制作流程，先填写文案，再选择人物和声音。'
    assert assess(first+'最后必须核对重要金额和承诺条件，并且保留所有原始记录。', [{'text':first}])['status']=='blocked'
    assert assess(first,[{'text':first,'confidence':.1}])['status']=='review'
    assert assess(first,[{'text':first,'confidence':float('nan')}])['status']=='review'


@pytest.mark.parametrize(('script','spoken'),[
    ('今年投资100万元，目标增长10%。','今年投资100万元，目标增长10。'),
    ('投资10万元，计划三年回本。','投资10万美元，计划三年回本。'),
    ('不保证收益，提供服务。','保证收益，不提供服务。'),
    ('日期2026年10月19日，请按时参加培训。','日期2026年10月18日，请按时参加培训。'),
])
def test_units_dates_and_moved_negation_need_review(script,spoken):
    from backlot.studio_audio_check import assess
    report=assess(script,[{'text':spoken}])
    assert report['status']!='passed' and report['critical_differences']


def test_percent_and_large_chinese_number_equivalence():
    from backlot.studio_audio_check import assess
    assert assess('投入十万元，增长百分之十。',[{'text':'投入100000元增长10%'}])['status']=='passed'


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    from backlot import studio_audio_check as checks, studio_asr, studio_avatar
    s=Studio(tmp_path/'projects')
    d=s.save_draft({'template_id':'avatar-safe-circle-v1','title':'测试','text':'今天介绍真实声音与字幕核对流程。','input':{'soundMode':'audio'}})
    folder=s.projects_root/d['id'];folder.mkdir(parents=True)
    audio=folder/'input.wav';audio.write_bytes(b'owned audio')
    with s.db() as db: db.execute('INSERT INTO studio_assets VALUES(?,?,?,?,?)',('audio',d['id'],'录音.wav','audio',str(audio)))
    d=s.save_draft({**d,'input':{**d['input'],'audio':{'id':'audio','name':'录音.wav'}}})
    monkeypatch.setattr(studio_asr,'snapshot',lambda _: {'provider':'local-whisper','identity':'engine-1'})
    monkeypatch.setattr(studio_avatar,'prepare_audio',lambda src,dst,*a: (Path(dst).write_bytes(Path(src).read_bytes()),3)[1])
    calls=[]
    def transcribe(*args):
        calls.append(1)
        return {'segments':[{'text':d['text'],'start':0,'end':3,'words':[{'text':d['text'],'start':0,'end':3,'probability':.99}]}]}
    monkeypatch.setattr(studio_asr,'transcribe',transcribe)
    return s,d,calls


def test_cache_concurrency_and_changed_text_or_audio_binding(fixture):
    from backlot.studio_audio_check import check_audio, require_pass
    s,d,calls=fixture
    with ThreadPoolExecutor(2) as pool: reports=list(pool.map(lambda _:check_audio(s,d),range(2)))
    assert reports[0]['binding']==reports[1]['binding'] and len(calls)==1
    require_pass(s,d,reports[0])
    changed={**d,'text':'完全不同的新文案'}
    with pytest.raises(WorkError): require_pass(s,changed,reports[0])
    check_audio(s,changed)
    assert len(calls)==1  # Same real audio clock reused, content comparison refreshed.
    s.asset('audio',d['id']).write_bytes(b'changed audio')
    with pytest.raises(WorkError): require_pass(s,d,reports[0])


def test_http_revision_ownership_and_no_paid_gateway(fixture, monkeypatch):
    s,d,calls=fixture
    monkeypatch.setattr(s,'client',lambda:pytest.fail('preflight must never create a paid client'))
    app=FastAPI();app.state.studio=s;app.include_router(router);client=TestClient(app)
    url=f'/api/studio/drafts/{d["id"]}/audio-check'
    assert client.post(url,json={'revision':0}).status_code==409
    report=client.post(url,json={'revision':d['revision']}).json()
    assert report['status']=='passed' and report['charge_micros']==0
    assert client.post(url,json={'revision':d['revision'],'audio_id':'foreign'}).status_code==409


def test_quote_mismatch_gate_precedes_all_uploads_and_quotes(fixture, monkeypatch):
    from backlot import studio_avatar, studio_template_registry
    s,d,_=fixture
    d={**d,'text':'这是另一份完全不同的长文案，与当前录音毫无关系。'}
    monkeypatch.setattr(studio_avatar,'validate',lambda *a:None)
    monkeypatch.setattr(studio_template_registry,'resolve',lambda *a:None)
    monkeypatch.setattr(s,'client',lambda:pytest.fail('mismatch reached paid/upload client'))
    with pytest.raises(WorkError,match='核对|不匹配'):studio_avatar.quote(s,d)


def test_receipt_cannot_be_forged_or_reused_after_engine_change(fixture,monkeypatch):
    from backlot import studio_asr
    from backlot.studio_audio_check import check_audio,require_pass
    s,d,_=fixture
    report=check_audio(s,d)
    with pytest.raises(WorkError):require_pass(s,d,{**report,'id':'forged'})
    monkeypatch.setattr(studio_asr,'snapshot',lambda _: {'provider':'local-whisper','identity':'engine-2'})
    with pytest.raises(WorkError):require_pass(s,d,report)


def test_production_reuses_the_clock_that_passed_recheck_without_new_asr(fixture,monkeypatch):
    from backlot import studio_asr
    from backlot.studio_audio_check import check_audio,production_clock
    s,d,calls=fixture
    original=studio_asr.transcribe
    # Low-confidence recognition requires a bounded independent decode, even with equal text.
    def low(*args):
        result=original(*args);result['provider']='local-whisper'
        result['segments'][0]['words'][0]['probability']=.1
        return result
    monkeypatch.setattr(studio_asr,'transcribe',low)
    retry={'provider':'local-whisper','segments':[{'text':d['text'],'start':0,'end':3,
           'words':[{'text':d['text'],'start':0,'end':3,'probability':.99}]}]}
    monkeypatch.setattr(studio_asr,'recheck',lambda *a:retry)
    monkeypatch.setattr(studio_asr,'verify_engine',lambda *a:None)
    report=check_audio(s,d)
    assert report['status']=='passed' and report['recognition']=='local-recheck'
    path=s.projects_root/d['id']/'assets/audio-checks'/report['clock_folder']/'narration.wav'
    assert production_clock(s,d,report,path,3)['segments'][0]['words'][0]['probability']==.99
    assert len(calls)==1
    path.write_bytes(b'changed prepared audio')
    with pytest.raises(WorkError):production_clock(s,d,report,path,3)


def test_worker_stale_binding_stops_before_any_generation(fixture,monkeypatch):
    from backlot.studio_audio_check import check_audio
    from backlot.studio_avatar import run_avatar,key_identity
    s,d,_=fixture
    report=check_audio(s,d)
    s.asset('audio',d['id']).write_bytes(b'changed after quote')
    class NoPaidClient:
        def __getattr__(self,name):pytest.fail(f'stale receipt reached provider {name}')
    request={'id':'gated','draft':d,'key_identity':key_identity(s),'render_id':'gated','prepared':{},'audio_check':report}
    result=run_avatar(s.projects_root/d['id'],request,NoPaidClient())
    assert result['status']=='awaiting_human' and result['error']['code']=='audio_check_stale'


def test_queue_freeze_requires_private_matching_receipt(fixture):
    from backlot.studio_audio_check import check_audio
    from backlot.studio_avatar import frozen_request,key_identity
    s,d,_=fixture
    report=check_audio(s,d)
    data={'id':'checked-quote','draft':d,'key_identity':key_identity(s),'prepared':{},'quotes':{},'audio_check':report}
    with s.db() as db:db.execute('INSERT INTO studio_quotes VALUES(?,?)',(data['id'],json.dumps(data)))
    assert frozen_request(s,d,data['id'])['audio_check']['id']==report['id']
    s.asset('audio',d['id']).write_bytes(b'changed before queue submission')
    with pytest.raises(WorkError) as error:frozen_request(s,d,data['id'])
    assert error.value.code=='audio_check_stale'
