const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
let now=0;const calls=[],preference={matches:false,addEventListener(type,callback){this.changed=callback;}};
class Element{
  constructor(tag,attrs={}){this.tag=tag;this.attrs={...attrs};this.children=[];this.style={};this.clientWidth=800;this.clientHeight=320;}
  setAttribute(k,v){this.attrs[k]=String(v);}getAttribute(k){return this.attrs[k]??null;}
  append(...items){for(const item of items){if(item.parent){const list=item.parent.children;list.splice(list.indexOf(item),1);}item.parent=this;this.children.push(item);}}
  insertBefore(item,before){assert.equal(before.parent,this);item.parent=this;this.children.splice(this.children.indexOf(before),0,item);}
  querySelectorAll(){const found=[];function walk(e){for(const c of e.children){if(c.attrs['data-series']||c.attrs['data-side']||c.attrs['data-cost-series'])found.push(c);walk(c);}}walk(this);return found;}
  animate(frames,options){const animation={frames,options,element:this,cancelled:false,cancel(){this.cancelled=true;},finished:new Promise(()=>{})};calls.push(animation);return animation;}
}
const document={hidden:false,createElementNS:(ns,tag)=>new Element(tag)};
const sandbox={window:{matchMedia:()=>preference},document,performance:{now:()=>now}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/chart-motion.js'),'utf8'),sandbox);
const motion=sandbox.window.lopmChartMotion,chart=new Element('svg');
function paint(volume=3){
  chart.children=[];const axis=new Element('text'),line=new Element('path',{'data-series':'price',d:'M0,5 L50,10 M70,8 L90,4'}),cross=new Element('line');
  chart.append(axis,line,...Array.from({length:volume},(_,i)=>new Element('rect',{'data-series':'volume',height:i+1})),cross);
  return {axis,line,cross};
}
let nodes=paint(5000);motion.present(chart,'FPT|line');
assert.equal(calls.length,2,'thousands of bars use at most two group animations');
assert.equal(nodes.line.getAttribute('d'),'M0,5 L50,10 M70,8 L90,4','preserve geometry and gaps');
assert.equal(nodes.axis.parent,chart,'axes stay outside animated groups');assert.equal(nodes.cross.parent,chart);
const entered=calls.length;paint();motion.present(chart,'FPT|line');assert.equal(calls.length,entered,'polls do not restart entry');
paint();motion.present(chart,'FPT|line',{replay:true});assert.equal(calls.length,entered,'replay frames stay immediate');
paint();motion.requestView(chart);motion.present(chart,'FPT|line',{interacting:true});assert.equal(calls.length,entered,'dragging stays immediate');
now=500;paint();motion.requestView(chart);motion.present(chart,'FPT|line');assert.equal(calls.length,entered+1,'discrete zoom gets one brief fade');
now=550;paint();motion.requestView(chart);motion.present(chart,'FPT|line');assert.equal(calls.length,entered+1,'rapid zoom events are throttled');
now=900;paint();motion.present(chart,'VCB|candles');assert.equal(calls.length,entered+3,'a different dataset/style can enter');
preference.matches=true;preference.changed();assert.ok(calls.every(a=>a.cancelled),'reduced motion cancels active animations');
const quiet=calls.length;paint();motion.present(chart,'HPG|line');motion.enter(new Element('dialog'),'dialog');assert.equal(calls.length,quiet);
preference.matches=false;document.hidden=true;paint();motion.present(chart,'SSI|line');assert.equal(calls.length,quiet,'hidden tabs do not animate');
document.hidden=false;motion.reset(chart);paint();motion.present(chart,'SSI|line');assert.equal(calls.length,quiet+2);
console.log('Bounded chart motion, static axes, polling/replay/drag guards, zoom throttling and reduced motion passed.');
