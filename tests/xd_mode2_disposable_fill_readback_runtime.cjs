"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const code=fs.readFileSync("experimental/mode2-xd-uxp/main.js","utf8");
const DOC="98d6635b-3767-4254-b200-ec8442b69ad2";
const GUID="9989e92f-7c9b-4721-9cdc-b5b5ea33cdf2";
const NAME="MODE2_DISPOSABLE_FILL_RECT_GUID_E2E";
class Color{
  constructor(hex){this.hex=hex}
  toHex(force){assert.equal(force,true);return this.hex}
}
const shape={guid:GUID,name:NAME,visible:true,locked:false,fillEnabled:true,
  fill:new Color("#445566"),constructor:{name:"Rectangle"},
  globalBounds:{x:820,y:500,width:36,height:28},
  localBounds:{x:820,y:500,width:36,height:28}
};
const base=Array.from({length:33},(_,i)=>({
  guid:"original-"+i,name:"Panda Original "+i,visible:true,locked:false,
  globalBounds:{x:1,y:2,width:5,height:6},constructor:{name:"Rectangle"}
}));
const all=[...base,shape], root={guid:DOC,children:{length:all.length,at:i=>all[i]}};
const selection={items:[shape],insertionParent:root};
const messages=[];let setup,edits=0;
class Socket{
  constructor(){this.readyState=1;Socket.current=this}
  send(m){messages.push(JSON.parse(m))}
}
vm.runInNewContext(code,{console,WebSocket:Socket,
  setTimeout:()=>0,clearTimeout(){},
  require(name){
    if(name==="scenegraph")return {root,selection,getNodeByGUID:id=>all.find(n=>n.guid===id),
      Color,Rectangle:class{},Ellipse:class{},Path:class{},Text:class{}};
    if(name==="application")return {version:"unit",appLanguage:"en",editDocument(){edits++}};
    if(name==="uxp")return {entrypoints:{setup(x){setup=x}}};
    throw Error("unknown import "+name);
  }
},{timeout:3500,filename:"mode2-xd-uxp/main.js"});
setup.commands.mcpAdobeConnect(selection,root);
let counter=0;
async function call(method,params={}){
  const id="fill-"+(++counter);
  Socket.current.onmessage({data:JSON.stringify({id,method,params})});
  for(let i=0;i<12;i++)await Promise.resolve();
  const response=messages.find(x=>x.id===id);
  assert.ok(response,"missing UXP response "+method);
  return response;
}
const args={document_id:DOC,node_id:GUID,name:NAME,
  bounds:{left:820,top:500,right:856,bottom:528}};
(async()=>{
  let result=await call("xd.mode2.node.fill.inspect",args);
  assert.equal(result.ok,true);
  assert.equal(result.result.fill,"#445566");
  assert.equal(result.result.fill_type,"Color");
  assert.equal(result.result.node_id,GUID);
  assert.equal(result.result.pending_count,0);
  assert.equal(edits,0);
  for(const mutation of [
    {name:"11 XD Panda Right Ear"},
    {node_id:"wrong"},
    {document_id:"wrong"},
    {bounds:{...args.bounds,left:821}},
    {extra:"untrusted"}
  ]){
    const denied=await call("xd.mode2.node.fill.inspect",{...args,...mutation});
    assert.equal(denied.ok,false,"must fail closed on changed target");
  }
  shape.fillEnabled=false;
  assert.equal((await call("xd.mode2.node.fill.inspect",args)).ok,false);
  shape.fillEnabled=true;
  shape.fill=null;
  assert.equal((await call("xd.mode2.node.fill.inspect",args)).ok,false);
  shape.fill={toHex:()=>"#bad"};
  assert.equal((await call("xd.mode2.node.fill.inspect",args)).ok,false);
  shape.fill=new Color("#A1B2C3");
  result=await call("xd.mode2.node.fill.inspect",args);
  assert.equal(result.result.fill,"#A1B2C3");
  const queued=await call("xd.queue.mode2_fill",{
    document_id:DOC,node_id:GUID,bounds:args.bounds,
    fill:"#ABCDEF",isolated_test_copy:true,user_confirmed:true
  });
  assert.equal(queued.ok,true);
  assert.equal(queued.result.status,"queued");
  assert.equal((await call("xd.mode2.node.fill.inspect",args)).ok,false,
    "no readback while a mutation is awaiting manual approval");
  assert.equal(shape.fill.hex,"#A1B2C3","queued write cannot change native color");
  assert.equal(edits,0,"readback does not mutate via editDocument");
  console.log("MODE2_EXACT_NATIVE_FILL_READBACK_RUNTIME_PASS");
})().catch(e=>{console.error(e);process.exitCode=1});
