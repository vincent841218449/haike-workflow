import test from 'node:test';
import assert from 'node:assert/strict';
import {automaticTemplateChoice,filterTemplateCards,nativeTemplateCards,verticalTemplateCards} from '../src/template-library.js';

const ref={runtime:'motiongit',version:'2.5.7',fingerprint:'verified-source'};
const ready={id:'motiongit-612-v2-5-7',display_name:'04-A · 仪器台演示',supported:true,
  automatic_ready:true,template_ref:ref,groups:[],execution_modes:['components'],
  preview:'/actual.png',demo:'/actual.mp4'};

test('every selectable motion card preserves the verified automatic package',()=>{
  const [card]=nativeTemplateCards({styles:[ready]},'portrait',{style:ready.id,layout:'portrait'});
  assert.equal(card.name,ready.display_name);assert.equal(card.image,'/actual.png');
  assert.equal(card.demo,'/actual.mp4');assert.deepEqual(card.choice.templateRef,ref);
  assert.equal(card.choice.templateExecution,'auto');assert.equal(card.choice.motion.style,ready.id);
  assert.equal(card.choice.templatePolicy,'strict');assert.equal(card.selected,true);
});

test('native-only, unverified, announced and old releases cannot promise one-click creation',()=>{
  assert.deepEqual(nativeTemplateCards({styles:[{...ready,automatic_ready:false},
    {...ready,supported:false},{...ready,template_ref:null},
    {id:'04-A',supported:true,template_ref:{runtime:'adu-legacy',fingerprint:'old'}}],
    pending_packages:[{id:'uninstalled'}]},'portrait',null),[]);
});

test('an editing copy adopts only the corresponding visible new release',()=>{
  const catalog={styles:[ready]};
  assert.equal(automaticTemplateChoice(catalog,{style:'04-A',layout:'portrait'}).choice.templateExecution,'auto');
  assert.equal(automaticTemplateChoice(catalog,{style:ready.id,layout:'portrait'}).id,ready.id);
  assert.equal(automaticTemplateChoice(catalog,{style:'05-A',layout:'portrait'}),null);
  assert.equal(automaticTemplateChoice(catalog,{style:'04-A',layout:'landscape'}),null);
});

test('search matches exact names and sources, retaining current choice first',()=>{
  const cards=[{name:'02 · 纸面透视',id:'paper',description:'纸面',selected:false},
    {name:'04-A · 仪器台演示',id:'console',sourceLabel:'ADu',selected:true}];
  assert.equal(filterTemplateCards(cards,'仪器台')[0].id,'console');
  assert.equal(filterTemplateCards(cards,'纸面')[0].id,'paper');
  assert.deepEqual(filterTemplateCards(cards,'不存在'),[]);
  assert.equal(cards[0].id,'paper');
});

test('new library shows latest portrait identity once and never enables an unverified release',()=>{
  const old={...ready,template_ref:{...ref,layout:'portrait',template_id:'console'}};
  const next={...old,id:'new',automatic_ready:false,template_ref:{...old.template_ref,version:'2.7.11'}};
  const catalog={styles:[old,next,{...old,id:'wide',template_ref:{...old.template_ref,layout:'landscape'}}],
    pending_packages:[{id:'motiongit:adunext:console',layout:'portrait',version:'2.7.11',name:'科技控制台',reason:'等待实际渲染',url:'https://motiongit.com/template'}]};
  const cards=verticalTemplateCards(catalog);
  assert.equal(cards.length,1);assert.equal(cards[0].selectable,true);
  assert.equal(cards[0].choice.motion.style,old.id);
  assert.match(cards[0].sourceLabel,/已验收 v2.5.7.*新版 v2.7.11 验证中/);
  next.automatic_ready=true;
  assert.equal(verticalTemplateCards(catalog)[0].choice.motion.style,'new');
  assert.equal(nativeTemplateCards({styles:[old]},'portrait',{style:old.id,layout:'portrait'})[0].selected,true);
});

test('fresh drafts choose a verified portrait release rather than a removed basic template',()=>{
  const old={...ready,template_ref:{...ref,layout:'portrait',template_id:'template-04-dark-console-portrait'}};
  const pending={...old,id:'pending',automatic_ready:false,template_ref:{...old.template_ref,version:'2.7.11'}};
  assert.equal(automaticTemplateChoice({styles:[old,pending]},{style:'catalog-default',layout:'portrait'}).id,old.id);
  assert.equal(automaticTemplateChoice({styles:[pending]},{style:'catalog-default',layout:'portrait'}),null);
});
