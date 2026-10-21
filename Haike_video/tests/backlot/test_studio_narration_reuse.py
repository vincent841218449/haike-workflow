import copy
import json
import shutil
import wave
from types import SimpleNamespace

import pytest

from backlot import studio_narration_reuse as reuse
from backlot.work_catalog import WorkError


@pytest.fixture
def completed(tmp_path, monkeypatch):
    studio = SimpleNamespace(projects_root=tmp_path/'projects', private=tmp_path/'.backlot')
    folder=studio.projects_root/'studio-old'/'renders'/'studio-1';folder.mkdir(parents=True)
    audio=folder/'narration.wav';audio.write_bytes(b'original-voice')
    draft={'text':'各位老板。','input':{'soundMode':'voice','voiceId':'haike/cosyvoice','toneId':'voice_hou','rate':1.2}}
    original={**copy.deepcopy(draft),'id':'studio-old','text':'各位老板。第二句。'}
    quote={'id':'original-quote','model':'haike/cosyvoice','execution_route':'local-system-voice'}
    job={'status':'completed','job_id':'PQ-original','frozen_request':{'draft':original,'render_id':'studio-1','quotes':{'tts':quote}}}
    state={'prepared':{'audio_path':str(audio),'duration':6},'stages':{'tts':{'quote':quote,'job':{'status':'succeeded'},'intent_identity':'call-original'}}}
    (folder/'gateway-state.json').write_text(json.dumps(state))
    class Queue:
        def __init__(self,*args):pass
        def get(self,*args,**kwargs):return job
    monkeypatch.setattr('backlot.production_queue.ProductionQueue',Queue)
    return studio,draft,{'task':'PQ-original','end_seconds':3.04},job,state,folder,audio


def test_completed_prefix_preserves_original_receipt_without_new_intent(completed):
    studio,draft,selection,*_=completed
    audio,receipt=reuse.source(studio,draft,selection)
    assert receipt['source_intent']=='call-original' and receipt['new_tts_calls']==0
    assert receipt['duration']==3.04 and receipt['speed_changed'] is False
    target=audio.parent/'reused.wav';target.write_bytes(b'derivative')
    receipt['audio_sha256']=reuse.sha(target)
    reuse.verify(studio,draft,receipt,target)
    target.write_bytes(b'replaced')
    with pytest.raises(WorkError,match='已改变'):reuse.verify(studio,draft,receipt,target)


@pytest.mark.parametrize('mutation',['text','tone','rate','pending','receipt','clock','escape'])
def test_changed_identity_unfinished_source_and_unbound_clock_are_rejected(completed,mutation,tmp_path):
    studio,draft,selection,job,state,folder,audio=completed
    if mutation=='text':draft['text']='另一份文案。'
    if mutation=='tone':draft['input']['toneId']='voice_other'
    if mutation=='rate':draft['input']['rate']=1
    if mutation=='pending':job['status']='ambiguous'
    if mutation=='receipt':state['stages']['tts']['job']['status']='submission_unknown'
    if mutation=='clock':selection['end_seconds']=3.01
    if mutation=='escape':
        other=tmp_path/'external.wav';other.write_bytes(b'external');state['prepared']['audio_path']=str(other)
    (folder/'gateway-state.json').write_text(json.dumps(state))
    with pytest.raises(WorkError):reuse.source(studio,draft,selection)


def test_25fps_audio_end_conforms_to_60fps_render_without_retiming_other_boundaries():
    from backlot.studio_motiongit import output_segments
    rows=[{'t0':0,'t1':12.32},{'t0':12.32,'t1':50.88}]
    out=output_segments(rows,round(50.88*60)/60)
    assert out[-1]['t1']==3053/60
    assert out[0]==rows[0] and out[-1]['t0']==12.32 and rows[-1]['t1']==50.88
    # A missing substantive scene must still fail the author's timeline check.
    assert output_segments([{'t0':0,'t1':49}],50.88)[-1]['t1']==49


def test_cut_keeps_original_samples_and_does_not_apply_tts_rate_twice(completed,monkeypatch):
    studio,draft,selection,_,_,folder,audio=completed
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:pytest.skip('FFmpeg not installed')
    monkeypatch.setattr('lib.ffmpeg_locator.resolve_ffmpeg_pair',lambda:(ffmpeg,None))
    samples=b'\x12\x34\x56\x78'*(6*24000//2)
    with wave.open(str(audio),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(samples)
    original=reuse.sha(audio);target=folder/'prefix.wav'
    receipt=reuse.prepare(studio,draft,selection,target)
    with wave.open(str(target)) as w:
        assert w.getnframes()==round(3.04*24000)
        assert w.readframes(w.getnframes())==samples[:round(3.04*24000)*2]
    assert reuse.sha(audio)==original and receipt['new_tts_calls']==0


def test_recovery_accepts_bound_reuse_without_inventing_a_new_tts_stage(completed):
    from backlot.studio_audio_check import generated_clock_ready
    studio,draft,selection,_,_,_,audio=completed
    _,receipt=reuse.source(studio,draft,selection)
    project=studio.projects_root/'studio-new';folder=project/'renders/studio-2';folder.mkdir(parents=True)
    target=project/'assets/prefix.wav';target.parent.mkdir();target.write_bytes(audio.read_bytes())
    receipt['audio_sha256']=reuse.sha(target)
    request={'draft':draft,'render_id':'studio-2','narration_reuse':receipt,'quotes':{},
             'asr':{'provider':'local-whisper','identity':'test-engine'}}
    state={'stages':{},'prepared':{'audio_path':str(target),'duration':3.04}}
    (folder/'gateway-state.json').write_text(json.dumps(state))
    result={'segments':[{'start':0,'end':3,'text':'另一种识别写法','words':[{'start':0,'end':3,'text':'另一种识别写法'}]}]}
    (folder/'local-asr.json').write_text(json.dumps({'fingerprint':{'audio_sha256':reuse.sha(target),'engine_identity':'test-engine'},'result':result}))
    assert generated_clock_ready(project,request)
    assert not json.loads((folder/'gateway-state.json').read_text())['stages']
    target.write_bytes(b'changed')
    assert not generated_clock_ready(project,request)
