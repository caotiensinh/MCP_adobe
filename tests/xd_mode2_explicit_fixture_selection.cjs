"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const original=fs.readFileSync("experimental/mode2-xd-uxp/main.js","utf8");
const DOC="98d6635b-3767-4254-b200-ec8442b69ad2";
const GUID="130fdb64-c691-4374-ab46-66fd3f9e077c";
const shape={
  guid:GUID,name:"11 XD Panda Right Ear",locked:false,visible:true,
  fill:"#112233",constructor:{name:"Ellipse"},
  globalBounds:{x:484,y:166,width:100,height:114},
  localBounds:{x:484,y:166,width:100,height:114}
};
const root={guid:DOC,children:{length:1,at:()=>shape}};
const selection={items:[],insertionParent:root};
const sent=[];
let registered;
let edited=0;
class Socket{
  constructor(url){this.url=url;this.readyState=1;Socket.current=this}
  send(x){sent.push(JSON.parse(x))}
}
const scenegraph={root,selection,getNodeByGUID(id){return id===GUID?shape:undefined}};
const context={
  console,WebSocket:Socket,setTimeout:()=>0,clearTimeout(){},
  require(p){
    if(p==="scenegraph")return {...scenegraph, Rectangle:class{},Ellipse:class{},Path:class{},Text:class{},Color:class{}};
    if(p==="application")return {version:"mock",appLanguage:"en",editDocument(){edited++}};
    if(p==="uxp")return {entrypoints:{setup(c){registered=c}}};
    throw Error(p);
  }
};
vm.runInNewContext(original,context,{timeout:2500,filename:"experimental/mode2-xd-uxp/main.js"});
assert.ok(registered.commands.mcpAdobeMode2SelectFixture);
assert.equal(registered.commands.mcpAdobeMode2SelectFixture.name,"selectMode2FixtureCommand");
registered.commands.mcpAdobeConnect(selection,root);
async function call(method,params={}){
  const id="mode2_fixture_"+Math.random();
  Socket.current.onmessage({data:JSON.stringify({id,method,params})});
  for(let i=0;i<10;i++)await Promise.resolve();
  const r=sent.find(x=>x.id===id);
  assert.ok(r,"no response for "+method);
  return r;
}
(async()=>{
  assert.equal(selection.items.length,0);
  let response=await call("xd.mode2.select.fixture",{document_id:DOC,node_id:GUID});
  assert.equal(response.ok,false,"remote WebSocket may NEVER select a node");
  assert.equal(selection.items.length,0);
  const checks=[
    ()=>{shape.locked=true},
    ()=>{shape.name="Unknown Node"},
    ()=>{shape.globalBounds.width=104},
    ()=>{root.guid="different"},
  ];
  for(const mutate of checks){
    mutate();
    assert.throws(()=>registered.commands.mcpAdobeMode2SelectFixture(selection,root),/MODE2_FIXTURE_/);
    assert.equal(selection.items.length,0);
    root.guid=DOC;shape.locked=false;shape.name="11 XD Panda Right Ear";shape.globalBounds.width=100;
  }
  const receipt=registered.commands.mcpAdobeMode2SelectFixture(selection,root);
  assert.equal(receipt.selected,true);
  assert.equal(receipt.node_id,GUID);
  assert.equal(selection.items.length,1);
  assert.equal(selection.items[0],shape);
  assert.equal(edited,0,"selection command may not call editDocument");
  assert.equal(shape.fill,"#112233","selection command may not change native node fill");
  const select=await call("xd.selection.get");
  assert.equal(select.ok,true);
  assert.equal(select.result.items.length,1);
  assert.equal(select.result.items[0].guid,GUID);
  const inspect=await call("xd.mode2.node.inspect",{
    document_id:DOC,node_id:GUID,
    bounds:{left:484,top:166,right:584,bottom:280}
  });
  assert.equal(inspect.ok,true);
  assert.equal(inspect.result.node_id,GUID);
  assert.equal((await call("xd.health")).result.pending_count,0);
  console.log("MODE2_EXPLICIT_FIXTURE_SELECTION_RUNTIME_PASS");
})().catch(e=>{console.error(e);process.exitCode=1});
