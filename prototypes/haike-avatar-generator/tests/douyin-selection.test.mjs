import test from 'node:test';
import assert from 'node:assert/strict';
import {douyinRecoveryNeeded} from '../src/douyin-selection-model.js';

test('抖音异常和旧素材确认暂停可继续自动选材，健康任务不显示恢复操作',()=>{
  assert.equal(douyinRecoveryNeeded({status:'awaiting_human',stage:'请选择有权使用的抖音素材'}),true);
  assert.equal(douyinRecoveryNeeded({status:'failed',stage:'抖音登录失效'}),true);
  assert.equal(douyinRecoveryNeeded({status:'running',stage:'抖音选材'}),false);
  assert.equal(douyinRecoveryNeeded({status:'awaiting_human',stage:'等待人工审核'}),false);
  assert.equal(douyinRecoveryNeeded(null),false);
});
