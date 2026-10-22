import { test } from 'node:test';
import assert from 'node:assert/strict';
import { auditionPresentation, canSubmitFreeClone, filterVoices, operationState, referencePresentation } from '../src/voice-model.js';
import { validateInputs } from '../src/generator-model.js';

const voices = [
  { id: 'voice_system', name: '海客口播', scope: 'system', language: 'zh', tags: ['清晰'], status: 'ready' },
  { id: 'voice_personal', name: '我的英语', scope: 'personal', language: 'en', tags: [], status: 'ready' },
];
test('试听统一一个按钮，首次自动准备且不提示费用，缓存可离线播放', () => {
  const voice={status:'ready',scope:'personal',sample_status:'missing'};
  assert.equal(auditionPresentation(voice).label,'试听');
  assert.match(auditionPresentation(voice).hint,/免费试听/);
  const cached={...voice,sample_status:'succeeded',status:'unavailable',preview_ready:false};
  assert.equal(auditionPresentation(cached).label,'试听');
  assert.match(auditionPresentation(cached).hint,/免费试听/);
  assert.equal(auditionPresentation(cached,true).label,'暂停');
  assert.equal(auditionPresentation({...voice,sample_status:'accepted'}).label,'准备中');
  assert.equal(auditionPresentation({...voice,sample_status:'submission_unknown'}).label,'试听');
});
test('系统与个人音色分别筛选，搜索名称、语言和标签', () => {
  assert.deepEqual(filterVoices(voices, { scope: 'system', search: '清晰' }).map(v => v.id), ['voice_system']);
  assert.deepEqual(filterVoices(voices, { scope: 'personal', language: 'en' }).map(v => v.id), ['voice_personal']);
  assert.equal(filterVoices(voices, { scope: 'personal', language: 'zh' }).length, 0);
});
test('切换账号后不把失效的个人音色替换成系统默认音色', () => {
  const input = { templateId: 'avatar-safe-circle-v1', text: '你好', soundMode: 'voice', voiceId: 'haike/cosyvoice', toneId: 'voice_old_account', portrait: {} };
  const models = [{ id: 'haike/cosyvoice' }];
  assert.equal(validateInputs(input, models, voices).field, 'voice');
  assert.equal(validateInputs({ ...input, toneId: 'voice_personal' }, models, voices), null);
  assert.equal(validateInputs({ ...input, toneId: 'voice_personal' }, models, voices.map(v => ({ ...v, status: 'unavailable' }))).field, 'voice');
});
test('已有音频保持免配音，音色库或模型不可用不阻断已有音频', () => {
  const input = { templateId: 'avatar-safe-circle-v1', text: '你好', soundMode: 'audio', voiceId: '', audio: {}, portrait: {} };
  assert.equal(validateInputs(input, [], []), null);
});
test('结果未知明确引导查询原任务，不提示重新克隆', () => {
  assert.match(operationState('submission_unknown'), /查询原任务/);
  assert.doesNotMatch(operationState('submission_unknown'), /重新创建|重新克隆/);
});
test('自动克隆只接受明确零价克隆，试听使用独立的一键流程', () => {
  const operation={kind:'clone',quote:{model:'haike/voice-clone',max_charge_micros:'0'}};
  assert.equal(canSubmitFreeClone(operation),true);
  assert.equal(canSubmitFreeClone({...operation,kind:'sample'}),false);
  assert.equal(canSubmitFreeClone({...operation,quote:{...operation.quote,max_charge_micros:'100'}}),false);
  assert.equal(canSubmitFreeClone({...operation,quote:{...operation.quote,max_charge_micros:undefined}}),false);
  assert.equal(canSubmitFreeClone(null),false);
  assert.doesNotMatch(operationState('failed'),/已释放|已退款/);
});
test('长录音说明显示原时长、实际截取区间和克隆片段试听，不要求再审核', () => {
  const value=referencePresentation({source_duration:166,duration:20,excerpt_start:70,excerpt_end:90,trimmed:true});
  assert.match(value.summary,/2:46/);
  assert.match(value.notice,/1:10–1:30/);
  assert.match(value.notice,/无需手动剪辑/);
  assert.equal(value.label,'实际克隆片段试听');
  assert.equal(referencePresentation(null).label,'原录音试听');
  assert.equal(referencePresentation({duration:8,trimmed:false}).summary,'8.0秒 · 录音格式检查通过');
});
