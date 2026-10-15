import {test} from 'node:test';
import assert from 'node:assert/strict';
import {canProduceVoice, defaultProductionTone, creationReadiness, knownAudioMismatch, materialSelection, persistedAsset} from '../src/avatar-creation-model.js';

const models=[{id:'haike/cosyvoice'}], legacy={id:'voice_gateway_default',status:'ready'}, preview={id:'official',model:'haike/cosyvoice-system',status:'ready',production_ready:false};
test('新项目只默认选择能实际制作的音色；没有可用服务时不伪装为就绪',()=>{
  const library={items:[preview,legacy],default_voice_id:preview.id};
  assert.equal(defaultProductionTone(library,models),legacy);
  assert.equal(defaultProductionTone(library,[]),undefined);
  assert.equal(canProduceVoice(preview,[{id:preview.model}]),false);
  assert.equal(defaultProductionTone({items:[legacy,{...preview,production_ready:true}],default_voice_id:preview.id},[...models,{id:preview.model}]).id,preview.id);
});
test('四项输入的就绪状态涵盖可选素材的授权，已有录音不依赖配音服务',()=>{
  const input={text:'我的文案',soundMode:'voice',toneId:legacy.id,portrait:{name:'portrait.png'},ai:{enabled:true,materials:[]}};
  assert.equal(creationReadiness(input,models,[legacy]).ready,true);
  assert.equal(creationReadiness({...input,text:'  '},models,[legacy]).completed,2);
  assert.equal(creationReadiness({...input,text:'字'.repeat(5001)},models,[legacy]).ready,false);
  assert.equal(creationReadiness({...input,ai:{enabled:true,materials:[{rights_confirmed:false}]}},models,[legacy]).ready,false);
  assert.equal(creationReadiness({...input,soundMode:'audio',audio:{}},[],[]).ready,true);
  assert.equal(creationReadiness({...input,toneId:preview.id},models,[preview]).ready,false);
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
test('已识别录音与文案不符时不显示准备完成，切换配音或换录音后自动解除',()=>{
  const input={text:'真实文案',soundMode:'audio',audio:{id:'sample'},portrait:{id:'portrait'}};
  const job={input_issue:{code:'audio_script_mismatch',audio_id:'sample',text:'真实文案'}};
  assert.equal(knownAudioMismatch(input,job),true);
  assert.equal(creationReadiness(input,[],[],job).completed,2);
  assert.equal(knownAudioMismatch({...input,soundMode:'voice'},job),false);
  assert.equal(knownAudioMismatch({...input,audio:{id:'replacement'}},job),false);
  assert.equal(knownAudioMismatch({...input,text:'修改后的文案'},job),false);
});
