import test from 'node:test';
import assert from 'node:assert/strict';
import {taskProgress} from '../src/task-progress.js';
test('provider waits show observed stage counts, not a frozen invented generation percent',()=>{
  const task={status:'running',provider_wait:true,progress:{basis:'steps',completed:3,total:7,percent:43}};
  assert.deepEqual(taskProgress(task),{percent:null,steps:'3/7 步',label:'等待返回'});
  assert.equal(taskProgress({...task,provider_wait:false}).label,'3/7 步');
  assert.equal(taskProgress({...task,status:'completed',provider_wait:false}).percent,100);
  assert.equal(taskProgress({status:'running',progress:{basis:'frames',percent:64}}).percent,64);
});
