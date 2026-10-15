import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeTemplateCards} from '../src/template-library.js';

test('native picker preserves exact package identity and original preview',()=>{
  const ref={fingerprint:'real-package-bytes'};
  const c={styles:[{id:'04-A',name:'仪器台演示',supported:true,groups:[{}],template_ref:ref,
    preview:'/native.png',demo:'/native.mp4',automatic_name:'自写仿版',automatic_preview:'/fake.svg'}]};
  const [card]=nativeTemplateCards(c,'portrait',{style:'04-A',layout:'portrait'});
  assert.equal(card.image,'/native.png');assert.equal(card.demo,'/native.mp4');
  assert.equal(card.name,'仪器台演示');assert.deepEqual(card.choice.templateRef,ref);
  assert.equal(card.choice.templatePolicy,'strict');assert.equal(card.selected,true);
});

test('announced or unavailable packages cannot become creation choices',()=>{
  assert.deepEqual(nativeTemplateCards({styles:[{supported:false,id:'new-motion'}],pending_packages:[{id:'uninstalled'}]},'portrait',null),[]);
});
