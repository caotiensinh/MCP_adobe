"use strict";
// Real experimental UXP main.js in a Node VM. No host edits.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const code=fs.readFileSync("experimental/mode2-xd-uxp/main.js","utf8");
const DOC="98d6635b-3767-4254-b200-ec8442b69ad2";
const GUID="8adab848-2d3f-4998-912a-cde2462def29";
const NAME="MODE2_DISPOSABLE_FILL_RECT_GUID_E2E";
const shape={
  guid:GUID,name:NAME,visible:true,locked:false,fill:"#445566",
  globalBounds:{x:820,y:500,width:36,height:28},localBounds:{x:820,y:500,width:36,height:28},
  constructor:{name:"Rectangle"}
};
const old=Array.from({length:33},(_,i)=>({
  guid:"known-"+i,name:"Panda fixture "+i,visible:true,locked:false,
  globalBounds:{x:1,y:2,width:4,height:6},
  constructor:{name:"Rectangle"}
}));
const nodes=[...old,shape];
const root={guid:DOC,children:{length:nodes.length,at:i=>nodes[i]}};
const selection={items:[],insertionParent:root};
let registered,editCalls=0;
let now=1700000000000;
class FakeDate extends Date { static now(){return now;} }

const messages=[];
class Socket{
  constructor(){this.readyState=1;Socket.current=this}
  send(msg){messages.push(JSON.parse(msg))}
}
const graph={root,selection,getNodeByGUID:guid=>nodes.find(n=>n.guid===guid)};
const context={
 console,WebSocket:Socket,Date:FakeDate,setTimeout:()=>0,clearTimeout(){},
 require(id){
   if(id==="scenegraph")return {...graph,Rectangle:class {},Ellipse:class {},Path:class {},Text:class {},Color:class {}};
   if(id==="application")return {version:"mock",appLanguage:"en",editDocument(){editCalls++}};
   if(id==="uxp")return {entrypoints:{setup:r=>{registered=r}}};
   throw Error(id);
 }
};
vm.runInNewContext(code,context,{timeout:4000,filename:"experimental/mode2-xd-uxp/main.js"});
assert.ok(registered.commands.mcpAdobeMode2SelectStagedRect);
registered.commands.mcpAdobeConnect(selection,root);
let ctr=0;
async function call(method,params={}){
  const id="test-"+(++ctr);
  Socket.current.onmessage({data:JSON.stringify({id,method,params})});
  for(let i=0;i<10;i++)await Promise.resolve();
  const response=messages.find(v=>v.id===id);
  assert.ok(response,"no response "+method);
  return response;
}
const args={
  document_id:DOC,node_id:GUID,name:NAME,
  isolated_test_copy:true,
  bounds:{left:820,top:500,right:856,bottom:528}
};
(async()=>{
  const wrong=[
    {...args,document_id:"unknown"},
    {...args,node_id:"0".repeat(36)},
    {...args,name:"11 XD Panda Right Ear"},
    {...args,isolated_test_copy:false},
    {...args,bounds:{...args.bounds,right:857}},
    {...args,bounds:{...args.bounds,left:NaN}},
    {...args,unknown:"untrusted"}
  ];
  // Reject all malformed read-only stage requests without selection.
  for(const [index,candidate] of wrong.entries()){
    const response=await call("xd.mode2.selection.stage_disposable",candidate);
    assert.equal(response.ok,false,"invalid stage "+index);
    assert.equal(selection.items.length,0);
  }
  let response=await call("xd.mode2.selection.stage_disposable",args);
  assert.equal(response.ok,true);
  assert.equal(response.result.status,"awaiting_user_menu");
  assert.equal(selection.items.length,0,"WebSocket stage must never select");
  response=await call("xd.mode2.selection.stage_disposable",args);
  assert.equal(response.ok,false,"already staged must reject");
  shape.globalBounds.x=824;
  assert.throws(()=>registered.commands.mcpAdobeMode2SelectStagedRect(selection,root),/MODE2_DISPOSABLE_RECT_BOUNDS_CHANGED/);
  assert.equal(selection.items.length,0);
  shape.globalBounds.x=820;
  assert.throws(()=>registered.commands.mcpAdobeMode2SelectStagedRect(selection,root),/MODE2_STAGED_SELECTION_EXPIRED_OR_WRONG_DOC/);
  response=await call("xd.mode2.selection.stage_disposable",args);
  assert.equal(response.ok,true);
  // Changing root after stage must fail closed and consume the ticket.
  root.guid="other";
  assert.throws(()=>registered.commands.mcpAdobeMode2SelectStagedRect(selection,root),/MODE2_STAGED_SELECTION_EXPIRED_OR_WRONG_DOC/);
  root.guid=DOC;
  response=await call("xd.mode2.selection.stage_disposable",args);
  assert.equal(response.ok,true);
  const receipt=registered.commands.mcpAdobeMode2SelectStagedRect(selection,root);
  assert.equal(receipt.selected,true);
  assert.equal(receipt.node_id,GUID);
  assert.equal(selection.items.length,1);
  assert.equal(selection.items[0],shape);
  const read=await call("xd.mode2.node.inspect",{document_id:DOC,node_id:GUID,bounds:args.bounds});
  assert.equal(read.ok,true);
  assert.equal(read.result.selection_count,1);
  assert.equal((await call("xd.health")).result.pending_count,0);
  assert.equal(editCalls,0);
  assert.equal(shape.fill,"#445566");
  assert.throws(()=>registered.commands.mcpAdobeMode2SelectStagedRect(selection,root),/MODE2_STAGED_SELECTION_EXPIRED_OR_WRONG_DOC/);
  // A crashed sidecar can leave a ticket behind. An unexpired ticket must
  // remain protected; at 90+ seconds a new read-only stage must replace it.
  response=await call("xd.mode2.selection.stage_disposable",args);
  assert.equal(response.ok,true);
  response=await call("xd.mode2.selection.stage_disposable",args);
  assert.equal(response.ok,false,"unexpired staging remains immutable");
  now+=90001;
  response=await call("xd.mode2.selection.stage_disposable",args);
  assert.equal(response.ok,true,"expired staging should not block forever");
  assert.equal(selection.items.length,1);
  const renewed=registered.commands.mcpAdobeMode2SelectStagedRect(selection,root);
  assert.equal(renewed.selected,true);
  assert.equal(renewed.node_id,GUID);
  assert.equal(shape.fill,"#445566");
  assert.equal(editCalls,0,"expired-ticket replacement must not edit native node");
  console.log("MODE2_STAGED_DISPOSABLE_GUID_SELECTION_RUNTIME_PASS");
})().catch(e=>{console.error(e);process.exitCode=1});
