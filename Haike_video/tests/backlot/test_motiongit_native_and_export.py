import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.studio_motiongit_native import validate
from backlot.work_catalog import WorkCatalog,WorkError,sha
from backlot.work_api import router


def native_fixture():
    text='先准备文案，再准备声音。'
    schema={'$defs':{},'properties':{'segments':{'oneOf':[{'items':{'oneOf':[{'type':'object','properties':{
        'recipe':{'const':'two-items'},'durationFrames':{'type':'integer','minimum':180,'maximum':600},
        'inputs':{'type':'object'},'anchors':{'type':'object','required':['entry']}},'required':['recipe','durationFrames','inputs','anchors']}]}}]}}}
    recipe=[{'id':'two-items','cardinality':{'items':{'min':2,'max':2}}}]
    item={'recipe':'two-items','text':text,'from_cue':0,'to_cue':1,'inputs':{},'anchors':{'entry':0},'support':[text],
          'facts':{'items':[{'name':'文案','quote':'先准备文案'},{'name':'声音','quote':'再准备声音'}]}}
    draft={'text':text,'input':{}};cues=[{'startMs':0,'clock':'word'},{'startMs':3000,'clock':'word'}]
    return draft,[item],cues,{'duration':6,'scenes':[]},schema,recipe


def test_native_recipes_compile_real_clock_and_distinct_entities():
    args=native_fixture();out=validate(*args)
    assert out['workflow']=='native' and out['segments'][0]['durationFrames']==360
    args[1][0]['facts']['items'][1]={'name':'文案','quote':'先准备文案'}
    with pytest.raises(WorkError,match='真实数量'):validate(*args)


def test_native_cannot_use_sentence_time_as_word_time_or_arbitrary_paths():
    args=native_fixture();args[2][0]['clock']='sentence'
    with pytest.raises(WorkError,match='词级'):validate(*args)
    args[2][0]['clock']='word';args[1][0]['inputs']={'recording':{'path':'/unowned/private.mp4'}}
    with pytest.raises(WorkError,match='本期素材编号'):validate(*args)


def test_engineering_download_is_bound_to_exact_video_version(tmp_path,monkeypatch):
    root=tmp_path/'projects';project=root/'example';project.mkdir(parents=True)
    (project/'project.json').write_text(json.dumps({'title':'版本验收'}))
    monkeypatch.setattr('backlot.work_catalog.probe',lambda p:{'duration':8,'width':1080,'height':1920,'has_audio':True})
    c=WorkCatalog(root);ids=[]
    for name in ['old','new']:
        folder=project/'renders'/name;folder.mkdir(parents=True);video=folder/'motion-preview.mp4';video.write_bytes(name.encode())
        archive=folder/'editable-project.zip';archive.write_bytes((name+'-engineering').encode())
        (folder/'qa.json').write_text(json.dumps({'presentation':{'output_sha256':sha(video)},'archive_sha256':sha(archive)}))
        w=c.register('example',video,event_id=name);ids.append(w['versions'][-1]['version_id'])
    app=FastAPI();app.state.work_catalog=c;app.include_router(router);client=TestClient(app)
    url=f"/api/works/{w['work_id']}/engineering"
    old=client.get(url,params={'version':ids[0]});assert old.status_code==200 and old.content==b'old-engineering'
    assert client.head(url,params={'version':ids[1]}).status_code==200
    assert client.head(url,params={'version':'unrecorded'}).status_code==404
    (project/'renders/old/editable-project.zip').write_bytes(b'wrong-version')
    assert client.get(url,params={'version':ids[0]}).status_code==409
