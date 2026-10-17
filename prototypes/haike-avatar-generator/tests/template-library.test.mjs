import test from 'node:test';
import assert from 'node:assert/strict';
import {filterTemplateCards,nativeTemplateCards} from '../src/template-library.js';

test('native picker preserves exact package identity and original preview',()=>{
  const ref={runtime:'adu-legacy',fingerprint:'real-package-bytes'};
  const c={styles:[{id:'04-A',name:'仪器台演示',supported:true,groups:[{}],template_ref:ref,
    preview:'/native.png',demo:'/native.mp4',automatic_name:'自写仿版',automatic_preview:'/fake.svg'}]};
  const [card]=nativeTemplateCards(c,'portrait',{style:'04-A',layout:'portrait'});
  assert.equal(card.image,'/native.png');assert.equal(card.demo,'/native.mp4');
  assert.equal(card.name,'04-A · 仪器台演示');assert.deepEqual(card.choice.templateRef,ref);
  assert.equal(card.choice.templatePolicy,'strict');assert.equal(card.selected,true);
  assert.equal(card.choice.templateExecution,'native');
});

test('announced or unavailable packages cannot become creation choices',()=>{
  assert.deepEqual(nativeTemplateCards({styles:[{supported:false,id:'new-motion'}],pending_packages:[{id:'uninstalled'}]},'portrait',null),[]);
});

test('one-click library excludes quick components and packages without verified source identity',()=>{
  const styles=[{id:'quick',supported:true,groups:[]},{id:'04-A',supported:true,groups:[]},
    {id:'motiongit-612',name:'仪器台演示 · 完整版',supported:true,groups:[],selection:'console@2.5.2',template_ref:{runtime:'motiongit',version:'2.5.2',fingerprint:'signed-package'}}];
  const cards=nativeTemplateCards({styles},'portrait',null);
  assert.deepEqual(cards.map(c=>c.id),['motiongit-612']);
  assert.equal(cards[0].sourceLabel,'MotionGit · v2.5.2');
  assert.equal(cards[0].choice.motion.style,'motiongit-612');
});

test('search supports names, author source and purpose while keeping current choice first',()=>{
  const cards=[{name:'纸面聚合',id:'02-B',description:'清单',selected:false},
    {name:'仪器台演示',id:'04-A',sourceLabel:'ADu',selected:false},
    {name:'仪器台演示 · 完整版',id:'motiongit-612',sourceLabel:'MotionGit',selected:true}];
  assert.deepEqual(filterTemplateCards(cards,' 仪器台 ').map(c=>c.id),['motiongit-612','04-A']);
  assert.equal(filterTemplateCards(cards,'清单')[0].id,'02-B');
  assert.equal(filterTemplateCards(cards,'motiongit')[0].id,'motiongit-612');
  assert.deepEqual(filterTemplateCards(cards,'不存在'),[]);
  assert.equal(cards[0].id,'02-B');
});
