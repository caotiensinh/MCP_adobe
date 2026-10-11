// Regressions for Adobe XD Ellipse creation and GUID-targeted repair.
// Executes the real UXP applyMutation against a deterministic scenegraph mock.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const guid='11111111-1111-4111-8111-111111111111';
const rootGuid='22222222-2222-4222-8222-222222222222';
let nodes=[];
let counter=0;
class Ellipse {
  constructor(){
    this.radiusX=0;this.radiusY=0;this.tx=0;this.ty=0;
    this.guid=guid;this.name='';this.visible=true;
  }
  get localBounds(){return {x:0,y:0,width:2*this.radiusX,height:2*this.radiusY};}
  get globalBounds(){return {x:this.tx,y:this.ty,width:2*this.radiusX,height:2*this.radiusY};}
  moveInParentCoordinates(dx,dy){this.tx+=dx;this.ty+=dy;}
}
// Artboard is intentionally offset: MCP coordinates must NOT double-add it.
class Rectangle {
  constructor(){this.width=0;this.height=0;this.tx=0;this.ty=0;this.guid='rect-guid';this.name='';}
  get localBounds(){return {x:0,y:0,width:this.width,height:this.height};}
  get globalBounds(){return {x:491+this.tx,y:220+this.ty,width:this.width,height:this.height};}
  moveInParentCoordinates(dx,dy){this.tx+=dx;this.ty+=dy;}
}
class Text extends Rectangle {
  constructor(){super();this.width=100;this.height=32;this.guid='text-guid';this.text='';}
}
class Color{constructor(raw){this.raw=raw;}}
const root={guid:rootGuid,children:{get length(){return nodes.length},at:i=>nodes[i]}};
const insertionParent={addChild(node){nodes.push(node)},children:root.children};
const selection={items:[],insertionParent};
const sandbox={
 require(id){
  if(id==='scenegraph')return {Rectangle,Ellipse,Text,Color,root,selection};
  if(id==='application')return {version:'test',appLanguage:'en'};
  if(id==='uxp')return {entrypoints:{setup(){}}};
  throw Error('unexpected module '+id);
 },
 console,
 WebSocket:function(){throw Error('network not permitted')},
 setTimeout(){throw Error('timers not permitted')},clearTimeout(){},
 document:{}
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('adobe-xd-plugin/main.js','utf8'),sandbox);
const mutate=(method,params)=>vm.runInContext(
  'applyMutation({method:__testMethod,params:__testParams},scenegraph.selection)',
  Object.assign(sandbox,{__testMethod:method,__testParams:params}));
const params={guid,name:'06 XD Bamboo Upper Leaf',document_id:rootGuid,x:606,y:265,width:61,height:28};
const created=mutate('xd.queue.ellipse_create',{name:'New Ellipse',x:20,y:30,width:100,height:60,fill:'#777777'});
assert.equal(nodes.length,1);
assert.equal(nodes[0].radiusX,50);
assert.equal(nodes[0].radiusY,30);
assert.equal(nodes[0].globalBounds.x,20);
assert.equal(nodes[0].globalBounds.y,30);
assert.equal(nodes[0].localBounds.width,100);
assert.equal(nodes[0].localBounds.height,60);
assert.equal(created.bounds.width,100);
assert.equal(created.bounds.height,60);
// Rectangle and Text both have a nonzero artboard parent offset.
nodes=[];
const backdrop=mutate('xd.queue.rectangle_create',{name:'Poster',x:0,y:0,width:880,height:640,fill:'#AA0000'});
assert.equal(nodes[0].globalBounds.x,0,'rectangle should not inherit +491 offset');
assert.equal(nodes[0].globalBounds.y,0,'rectangle should not inherit +220 offset');
assert.equal(backdrop.bounds.x,0);
assert.equal(backdrop.bounds.y,0);
const second=mutate('xd.queue.rectangle_create',{name:'Shading',x:311,y:145,width:60,height:75});
assert.equal(nodes[1].globalBounds.x,311);
assert.equal(nodes[1].globalBounds.y,145);
assert.equal(second.bounds.width,60);
const label=mutate('xd.queue.text_create',{name:'Title',x:350,y:780,text:'Kung Fu',fontSize:36});
assert.equal(nodes[2].globalBounds.x,350,'text should use global document X');
assert.equal(nodes[2].globalBounds.y,780,'text should use global document Y');
assert.equal(label.bounds.x,350);
assert.throws(()=>mutate('xd.queue.rectangle_create',{x:'invalid',y:0,width:10,height:10}),/invalid global placement geometry/);

// Simulate the real E2E regression: Ellipse created with width/height (ignored).
nodes=[new Ellipse()];
nodes[0].name=params.name;
nodes[0].tx=params.x;nodes[0].ty=params.y;
const fixed=mutate('xd.queue.ellipse_geometry_repair',params);
assert.equal(nodes.length,1);
assert.equal(nodes[0].radiusX,30.5);
assert.equal(nodes[0].radiusY,14);
assert.equal(fixed.repaired,true);
assert.equal(fixed.bounds.width,61);
assert.equal(fixed.bounds.height,28);
assert.equal(fixed.bounds.left,606);
assert.equal(fixed.bounds.top,265);
assert.throws(()=>mutate('xd.queue.ellipse_geometry_repair',params),/already has nonzero radii/);
assert.throws(()=>mutate('xd.queue.ellipse_geometry_repair',{...params,guid:'33333333-3333-4333-8333-333333333333'}),/missing/);
assert.throws(()=>mutate('xd.queue.ellipse_geometry_repair',{...params,document_id:'wrong'}),/document identity/);
assert.throws(()=>mutate('xd.queue.ellipse_geometry_repair',{...params,width:0}),/already has nonzero radii/);
// No queued mutation should ever silently claim valid dimensions while zero-sized.
console.log('XD_ELLIPSE_GEOMETRY_CONTRACT=PASS radiusX/radiusY + global rectangle/text placement + GUID repair; negative and replay checks');
