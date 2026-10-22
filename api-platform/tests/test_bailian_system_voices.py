import json
from types import SimpleNamespace

import pytest
from test_voice_library import rig
from test_commerce import real_quote, fund
from test_platform import submit
from platform_app import bailian_system_voices as system, gateway, adapters, providers


def test_official_catalogue_is_stable_shared_and_audition_has_no_job(env):
    store,client,outsider,_,_,vault,headers,other=rig(env)
    library=client.get('/v2/voices',headers=headers).json()
    tones=[v for v in library['items'] if v.get('sample_kind')=='official']
    assert len(tones)==len({v['id'] for v in tones})==7
    assert {v['name'] for v in tones}=={'龙小淳','龙小夏','龙三叔','龙安昀','龙安朗','龙应笑','龙嘉怡'}
    assert next(v for v in tones if v['name']=='龙嘉怡')['language']=='yue'
    assert library['default_voice_id']==system.identity('longxiaochun_v3')
    assert all(v['model']==system.MODEL and v['production_ready'] for v in tones)
    assert len([v for v in outsider.get('/v2/voices',headers=other).json()['items'] if v.get('sample_kind')=='official'])==7
    preview=client.post('/v2/voices/'+tones[0]['id']+'/preview-quote',headers=headers).json()
    assert preview['cached'] and preview['sample_kind']=='official' and 'quote' not in preview
    assert preview['sample_url'].startswith('https://help-static-aliyun-doc.aliyuncs.com/')
    assert 'private-test-provider-secret' not in json.dumps(library)
    with store.read() as db:
        assert db.execute('SELECT count(*) FROM gateway_jobs').fetchone()[0]==0


def test_selected_system_voice_model_and_tariff_are_frozen_without_retargeting_clones(env):
    store,client,_,_,_,vault,headers,_=rig(env)
    preset=system.identity('longxiaochun_v3')
    q=real_quote(client,headers,model=system.MODEL,inputs={'text':'你好','voice_id':preset})
    with store.read() as db:
        snapshot=json.loads(db.execute('SELECT snapshot FROM gateway_quotes WHERE id=?',(q['id'],)).fetchone()[0])
    assert snapshot['model_info']['target_model']=='cosyvoice-v3-flash'
    assert snapshot['provider_config']['voice']=='longxiaochun_v3'
    assert snapshot['rule']['costs']['characters']=='1000000'
    assert vault.models()['haike/cosyvoice']['target_model']=='cosyvoice-v3.5-flash'
    fund(env);vault.update('bailian',{'voice':'other-cloned-voice'})
    assert submit(client,headers,q).status_code==200
    seen=[]
    class Fake:
        def execute(self,model,inputs,checkpoint,upstream_id):
            seen.append((model,inputs['_provider_config']['voice'],inputs['_model_info']['target_model']))
            return {'usage':{'characters':4},'result':{'audio_url':'https://example.test/a.wav'}}
    gateway.execute_one(store,Fake())
    assert seen==[(system.MODEL,'longxiaochun_v3','cosyvoice-v3-flash')]


def test_missing_wrong_or_arbitrary_voice_cannot_fall_back_to_a_default(env):
    _,client,_,_,_,_,headers,_=rig(env)
    for model,inputs in [
        (system.MODEL,{'text':'你好'}),
        (system.MODEL,{'text':'你好','voice_id':'voice_arbitrary'}),
        ('haike/cosyvoice',{'text':'你好','voice_id':system.identity('longxiaochun_v3')}),
    ]:
        assert client.post('/v2/quotes',headers=headers,json={'model':model,'input':inputs}).status_code in {404,409,422}


def test_system_synthesis_uses_existing_http_protocol_exact_voice_and_receipt(env,monkeypatch):
    from dashscope.audio.http_tts.http_speech_synthesizer import HttpSpeechSynthesizer
    store,_,_,_,_,vault,_,_=rig(env)
    calls=[]
    def fake(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200,usage={'characters':4},audio_url='https://example.test/a.wav',audio_id='audio-one',request_id='request-one')
    monkeypatch.setattr(HttpSpeechSynthesizer,'call',fake)
    inputs={'text':'你好','_model_info':providers.MODELS[system.MODEL], '_provider_config':{'voice':'longxiaochun_v3'}}
    result=adapters.Adapter(vault,store.path.parent/'files').execute(system.MODEL,inputs,lambda _:None)
    assert calls[0]['model']=='cosyvoice-v3-flash' and calls[0]['voice']=='longxiaochun_v3'
    assert result['usage']=={'characters':4}
