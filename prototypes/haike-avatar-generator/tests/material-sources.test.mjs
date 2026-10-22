import test from 'node:test';
import assert from 'node:assert/strict';
import {changeSource,selectedSources,MATERIAL_SEARCH_SCHEMA} from '../src/material-sources.js';

test('source choices are explicit, preserve uploads and do not mutate saved drafts',()=>{
  const old={materials:[{id:'keep'}],skip_douyin:true};
  assert.deepEqual(selectedSources(old),[]);
  const next=changeSource(old,'douyin',true);
  assert.deepEqual(next.material_search,{schema:MATERIAL_SEARCH_SCHEMA,providers:['douyin'],max_scenes:4});
  assert.equal(next.skip_douyin,false);
  assert.deepEqual(old,{materials:[{id:'keep'}],skip_douyin:true});
  const stock=changeSource(next,'pexels',true);
  assert.deepEqual(selectedSources(stock),['douyin','pexels']);
  const disabled=changeSource(stock,'douyin',false);
  assert.deepEqual(selectedSources(disabled),['pexels']);
  assert.equal(disabled.skip_douyin,true);
  assert.deepEqual(disabled.materials,[{id:'keep'}]);
  const ownOnly=changeSource(disabled,'pexels',false);
  assert.equal(ownOnly.material_search,undefined);
  assert.deepEqual(ownOnly.materials,[{id:'keep'}]);
});
