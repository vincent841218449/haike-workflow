import test from 'node:test';
import assert from 'node:assert/strict';
import {toggleDouyinSelection,douyinSelectionRequest} from '../src/douyin-selection-model.js';

test('多选保留原顺序，移除后不把其他素材取消',()=>{
  const selected=toggleDouyinSelection(['one'],'two');
  assert.deepEqual(selected,['one','two']);
  assert.deepEqual(toggleDouyinSelection(selected,'one'),['two']);
  assert.throws(()=>toggleDouyinSelection(Array.from({length:10},(_,i)=>String(i)),'eleven'),/10/);
});
test('只提交用户选择并明确授权的集合，空选或重复不提交',()=>{
  const selected=['one','two'];
  assert.throws(()=>douyinSelectionRequest(selected,false),/使用权/);
  assert.throws(()=>douyinSelectionRequest([],true),/请选择/);
  assert.throws(()=>douyinSelectionRequest(['one','one'],true),/请选择/);
  assert.deepEqual(douyinSelectionRequest(selected,true),{video_ids:['one','two'],rights_confirmed:true});
});
