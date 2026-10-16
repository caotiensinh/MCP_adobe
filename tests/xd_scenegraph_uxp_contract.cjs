// Contract-test XD UXP read-only scenegraph against a fake in-process document.
// This executes plugin dispatch itself; it is not a desktop XD E2E claim.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let editCount = 0;
const child = {guid:'child-1', name:'CTA',visible:true,locked:false,
  globalBounds:{x:40,y:50,width:120,height:60},children:[],constructor:{name:'Text'}};
const artboard={guid:'ab-1',name:'Screen',visible:true,locked:false,
  globalBounds:{x:0,y:0,width:600,height:400},
  children:{length:1,at:()=>child},constructor:{name:'Artboard'}};
const root={guid:'root-1',children:{length:1,at:()=>artboard}};
const fakeRequire = id=>{
 if(id==='application')return {version:'test',appLanguage:'en',editDocument(){editCount++}};
 if(id==='scenegraph')return {root,selection:{items:[]},Rectangle:function(){},Text:function(){},Color:function(){}};
 if(id==='uxp')return {entrypoints:{setup(){}}};
 throw Error('unexpected module '+id);
};
const sandbox={require:fakeRequire,console,WebSocket:function(){throw Error('no network allowed')},
  setTimeout(){throw Error('no timers allowed')},clearTimeout(){},document:{}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('adobe-xd-plugin/main.js','utf8'),sandbox);
const snap=vm.runInContext("dispatch('xd.scenegraph.snapshot',{})",sandbox);
assert.equal(snap.complete,true);
assert.equal(snap.document_id,'root-1');
assert.equal(snap.node_count,2);
assert.equal(snap.nodes[0].children[0].id,'child-1');
assert.equal(snap.nodes[0].children[0].bounds.left,40);
assert.equal(snap.nodes[0].children[0].bounds.right,160);
const frame=vm.runInContext("dispatch('xd.canvas.frame',{})",sandbox);
assert.equal(frame.document_id,'root-1');
assert.equal(frame.left,0);
assert.equal(frame.width,600);
assert.equal(frame.artboard_count,1);
assert.equal(editCount,0);
child.guid='ab-1';
assert.throws(()=>vm.runInContext("dispatch('xd.scenegraph.snapshot',{})",sandbox),/duplicate/);
console.log('XD_UXP_SCENEGRAPH_CONTRACT=PASS; no Adobe edit or network operations');
