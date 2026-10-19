import {test} from 'node:test';
import assert from 'node:assert/strict';
import {canProduceVoice, defaultProductionTone, creationReadiness, voiceDraft, materialSelection, persistedAsset} from '../src/avatar-creation-model.js';

const models=[{id:'haike/cosyvoice'}], legacy={id:'voice_gateway_default',status:'ready'}, preview={id:'official',model:'haike/cosyvoice-system',status:'ready',production_ready:false};
test('新项目只默认选择能实际制作的音色；没有可用服务时不伪装为就绪',()=>{
  const library={items:[preview,legacy],default_voice_id:preview.id};
  assert.equal(defaultProductionTone(library,models),legacy);
  assert.equal(defaultProductionTone(library,[]),undefined);
  assert.equal(canProduceVoice(preview,[{id:preview.model}]),false);
  assert.equal(defaultProductionTone({items:[legacy,{...preview,production_ready:true}],default_voice_id:preview.id},[...models,{id:preview.model}]).id,preview.id);
});
test('四项输入按所选音色制作，涵盖可选素材的授权',()=>{
  const input={text:'我的文案',soundMode:'voice',toneId:legacy.id,portrait:{name:'portrait.png'},ai:{enabled:true,materials:[]}};
  assert.equal(creationReadiness(input,models,[legacy]).ready,true);
  assert.equal(creationReadiness({...input,text:'  '},models,[legacy]).completed,2);
  assert.equal(creationReadiness({...input,text:'字'.repeat(5001)},models,[legacy]).ready,false);
  assert.equal(creationReadiness({...input,ai:{enabled:true,materials:[{rights_confirmed:false}]}},models,[legacy]).ready,false);
  assert.equal(creationReadiness({...input,soundMode:'audio',audio:{id:'a'}},[],[]).ready,false);
  assert.equal(creationReadiness({...input,toneId:preview.id},models,[preview]).ready,false);
});

test('准备提示指出所有缺项，并为素材问题提供可操作定位',()=>{
  const state=creationReadiness({text:'',soundMode:'voice',toneId:'missing',portrait:null,ai:{enabled:true,materials:[{}]}},[],[]);
  assert.deepEqual(state.missing.map(v=>v.id),['text','voice','portrait','materials']);
  assert.equal(state.message,'还需：文案、音色、人物图片、素材使用确认');
  const tooMany=creationReadiness({text:'文案',soundMode:'voice',toneId:legacy.id,portrait:{},ai:{materials:Array(5).fill({rights_confirmed:true})}},models,[legacy]);
  assert.equal(tooMany.ready,false);assert.equal(tooMany.missing[0].id,'materials');
  assert.match(tooMany.message,/最多4份/);
});

test('旧录音草稿只在编辑副本切换为按文案配音，原文和音色素材完整保留',()=>{
  const original={text:'完整文案',soundMode:'audio',audio:{id:'old-sample'},toneId:legacy.id,voiceId:'haike/cosyvoice',portrait:{id:'p'},motion:{style:'04-A'},rate:1.2};
  const copy=voiceDraft(original);
  assert.equal(copy.soundMode,'voice');assert.ok(!('audio' in copy));
  assert.equal(original.audio.id,'old-sample');assert.equal(original.soundMode,'audio');
  for(const field of ['text','toneId','voiceId','portrait','motion','rate'])assert.deepEqual(copy[field],original[field]);
  assert.equal(creationReadiness(copy,models,[legacy]).ready,true);
  assert.equal(creationReadiness({...copy,toneId:'missing'},models,[legacy]).ready,false);
});
test('批量素材在上传前核对剩余容量和全部文件，不截断或上传半个无效批次',()=>{
  const f=name=>({name,size:100});
  assert.deepEqual(materialSelection([f('a.jpg'),f('b.MOV')],2).map(f=>f.name),['a.jpg','b.MOV']);
  assert.throws(()=>materialSelection([f('a.png'),f('b.png')],3),/还可添加1/);
  assert.throws(()=>materialSelection([f('valid.png'),f('bad.exe')],0),/bad.exe/);
  assert.throws(()=>materialSelection([{name:'large.png',size:80*1024*1024+1}],0),/80 MB/);
  assert.throws(()=>materialSelection([{name:'empty.jpg',size:0}],0),/empty.jpg/);
});
test('保存已上传图片不把浏览器File序列化回服务器，重复保存和刷新仍使用原素材',()=>{
  const source={id:'portrait-a',name:'我的人物.png',url:'/api/studio/assets/portrait-a',kind:'image',type:'image/png',file:new Blob(['local file'])};
  const saved=persistedAsset(source);
  assert.equal(saved.id,source.id);assert.equal(saved.url,source.url);
  assert.ok(!('file' in saved));
  assert.deepEqual(persistedAsset(JSON.parse(JSON.stringify({...source,file:{}}))),saved);
});
