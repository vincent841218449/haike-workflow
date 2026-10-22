"""Speech speed persists through drafts and the real local audio preparation."""
import array
import hashlib
import json
import math
import struct
import wave

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.studio import Studio
from backlot.studio_api import router
from backlot.studio_avatar import prepare_audio, validate_voice, frozen_request, key_identity
from backlot.studio_speech_rate import speech_rate
from backlot.work_catalog import WorkError


def draft(rate):
    return {"template_id":"avatar-safe-circle-v1","title":"语速验收","text":"你好，海客。",
            "input":{"soundMode":"voice","voiceId":"haike/cosyvoice","rate":rate}}


@pytest.mark.parametrize("rate", [round(.8+i*.05,2) for i in range(15)])
def test_speed_is_saved_and_validated_for_production(tmp_path, rate):
    studio=Studio(tmp_path/'projects'); saved=studio.save_draft(draft(rate))
    reloaded=Studio(studio.projects_root).draft(saved['id'])
    assert reloaded['input']['rate']==rate
    validate_voice(reloaded['input'])
    assert speech_rate(rate)==rate


@pytest.mark.parametrize("rate", [.75,1.55,1.125,True,False,None,"1.2",float('nan'),float('inf')])
def test_bad_speeds_are_rejected_before_any_quote_or_supplier_call(tmp_path, rate):
    studio=Studio(tmp_path/'projects')
    with pytest.raises(WorkError,match='语速'): studio.save_draft(draft(rate))
    with pytest.raises(WorkError,match='语速'): validate_voice(draft(rate)['input'])


def test_http_roundtrip_and_frozen_quote_keep_the_selected_speed(tmp_path):
    studio=Studio(tmp_path/'projects'); app=FastAPI();app.state.studio=studio;app.include_router(router)
    with TestClient(app) as http:
        response=http.post('/api/studio/drafts',json=draft(1.15))
        assert response.status_code==200
        saved=response.json()
        assert http.get('/api/studio/drafts/'+saved['id']).json()['input']['rate']==1.15
    value={'id':'rate-quote','draft':saved,'key_identity':key_identity(studio),'quotes':{},'prepared':{}}
    with studio.db() as db: db.execute('INSERT INTO studio_quotes VALUES(?,?)',('rate-quote',json.dumps(value)))
    assert frozen_request(studio,saved,'rate-quote',1000)['draft']['input']['rate']==1.15
    with pytest.raises(WorkError,match='改变'):
        frozen_request(studio,{**saved,'input':{**saved['input'],'rate':1.2}},'rate-quote',1000)


def test_uploaded_audio_ignores_the_unused_voice_speed(tmp_path):
    studio=Studio(tmp_path/'projects'); value=draft(1.125)
    value['input']['soundMode']='audio'
    saved=studio.save_draft(value)
    validate_voice(saved['input'])
    assert saved['input']['rate']==1.125


@pytest.mark.parametrize('rate',[.8,1.15,1.5])
def test_real_audio_preparation_changes_duration_and_preserves_pitch(tmp_path, rate):
    source,target=tmp_path/'original.wav',tmp_path/'prepared.wav'
    with wave.open(str(source),'wb') as audio:
        audio.setparams((1,2,24000,0,'NONE','not compressed'))
        audio.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(2*math.pi*440*i/24000))) for i in range(4*24000)))
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    duration=prepare_audio(source,target,rate)
    with wave.open(str(target),'rb') as audio:
        assert audio.getframerate()==24000 and audio.getnchannels()==1
        assert audio.getnframes()/24000==pytest.approx(math.ceil(4/rate*25)/25,abs=1/24000)
        audio.setpos(24000//2); samples=array.array('h',audio.readframes(24000))
        crossings=sum(a<=0<b for a,b in zip(samples,samples[1:]))
        assert 437<=crossings<=443
    assert duration==math.ceil(4/rate*25)/25
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
