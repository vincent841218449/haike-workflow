import {test} from 'node:test';
import assert from 'node:assert/strict';
import {enqueueAvatar, taskUrl, rememberSubmission, readSubmission} from '../src/avatar-submit.js';

const submission = () => ({draft:{id:'studio-test'},quote:{id:'quote-a',revision:3,known_max_micros:13000000},billingPolicy:'actual_usage'});
test('一键提交冻结报价和版本，按实际使用制作，不要求视频总预算', async()=>{
  const calls=[],job={job_id:'queue-a',parent_job_id:'studio-3',status:'queued'};
  assert.equal(await enqueueAvatar(async(...args)=>{calls.push(args);return job;},submission()),job);
  assert.deepEqual(calls,[['/api/studio/drafts/studio-test/generate',{revision:3,quote_id:'quote-a',billing_policy:'actual_usage',confirmed:true}]]);
  assert.equal(taskUrl(job),'/tasks?task=queue-a');
});
test('旧页面丢响应的提交仍恢复原参数，不能悄悄升级旧冻结请求', async()=>{
  const calls=[];
  await enqueueAvatar(async(path,body)=>{calls.push(body);return {job_id:'original'};},{...submission(),maximum:10000000});
  assert.equal(calls[0].max_charge_micros,10000000);
  assert.equal(calls[0].billing_policy,undefined);
});
test('提交响应丢失时查回同版本原任务，旧版本不能冒充成功',async()=>{
  const job={job_id:'existing',parent_job_id:'studio-3'};
  assert.equal(await enqueueAvatar(async(path,body)=>{if(body)throw new Error('lost');return {job};},submission()),job);
  await assert.rejects(enqueueAvatar(async(path,body)=>{if(body)throw new Error('lost');return {job:{...job,parent_job_id:'studio-2'}};},submission()),e=>e.submissionUncertain===true);
});
test('未知结果保留原提交；重试重用相同版本、报价与预算',async()=>{
  const bodies=[],s=submission();let retry=false;
  const request=async(path,body)=>{if(!body)throw new Error('offline');bodies.push(body);if(!retry)throw new Error('offline');return {job_id:'same'};};
  await assert.rejects(enqueueAvatar(request,s),e=>e.submissionUncertain===true);
  retry=true;await enqueueAvatar(request,s);
  assert.deepEqual(bodies[0],bodies[1]);
});
test('明确拒绝可以修改输入后重新提交；不锁为未知付费任务',async()=>{
  await assert.rejects(enqueueAvatar(async(path,body)=>{if(!body)return {job:null};throw Object.assign(new Error('quote expired'),{status:409});},submission()),e=>e.submissionUncertain===false);
});
test('刷新保留待核对提交，不存正文或凭据，也不恢复到其他草稿',()=>{
  const values=new Map(),storage={setItem:(k,v)=>values.set(k,v),getItem:k=>values.get(k),removeItem:k=>values.delete(k)};
  const s=submission();s.draft.text='private text';s.draft.input={};
  rememberSubmission(storage,s);
  assert.equal(readSubmission(storage,s.draft.id).quote.id,'quote-a');
  assert.equal(readSubmission(storage,'another'),null);
  assert.ok(!JSON.stringify([...values.values()]).includes('private text'));
  rememberSubmission(storage,null);assert.equal(readSubmission(storage,s.draft.id),null);
});

test('修正输入后沿原创作继续，刷新和提交均保留显式关联',async()=>{
  const values=new Map(),storage={setItem:(k,v)=>values.set(k,v),getItem:k=>values.get(k),removeItem:k=>values.delete(k)};
  const s={...submission(),resumeTask:'PQ-original'};
  rememberSubmission(storage,s);
  const restored=readSubmission(storage,s.draft.id),calls=[];
  await enqueueAvatar(async(path,body)=>{calls.push(body);return {job_id:'PQ-next'};},restored);
  assert.equal(calls[0].resume_task,'PQ-original');
  assert.equal(calls[0].billing_policy,'actual_usage');
  assert.equal(calls[0].max_charge_micros,undefined);
});
