import {test} from 'node:test';
import assert from 'node:assert/strict';
import {applyAuditionRate, isSpeechRate, speechRateLabel} from '../src/speech-rate.js';
import {validateInputs} from '../src/generator-model.js';

test('支持0.80至1.50倍、0.05步长，旧草稿默认1倍并拒绝越界或非数值',()=>{
  for(let i=0;i<=14;i++) assert.equal(isSpeechRate(Number((.8+i*.05).toFixed(2))),true);
  assert.equal(isSpeechRate(undefined),true);
  for(const value of [.75,1.55,1.125,'1.2',null,true,NaN,Infinity]) assert.equal(isSpeechRate(value),false);
  assert.equal(speechRateLabel(1.15),'1.15×');
});
test('试听只改变缓存播放器的语速并保持音调，不替换音频来源',()=>{
  const audio={src:'/api/studio/voices/voice_local_test/sample',currentTime:2.3,playbackRate:1,preservesPitch:false};
  for(const rate of [1.15,.8,1.5,1]) {
    applyAuditionRate(audio,rate);
    assert.equal(audio.playbackRate,rate); assert.equal(audio.preservesPitch,true);
    assert.equal(audio.currentTime,2.3); assert.equal(audio.src,'/api/studio/voices/voice_local_test/sample');
  }
});
test('非法语速在提交之前定位到音色区，已有音频继续按原语速制作',()=>{
  const input={templateId:'avatar-safe-circle-v1',text:'真实文案',soundMode:'voice',voiceId:'haike/cosyvoice',portrait:{},rate:1.125};
  assert.equal(validateInputs(input,[{id:input.voiceId}]).field,'voice');
  assert.equal(validateInputs({...input,rate:1.15},[{id:input.voiceId}]),null);
  assert.equal(validateInputs({...input,soundMode:'audio',audio:{}},[]),null);
});
