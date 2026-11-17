const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function harness(reduced=false){
  const animations=[],events=[],handlers={};
  class Element{
    constructor(native=false){this.tagName=native?'DETAILS':'DIV';this.hidden=!native;this.open=false;this.isConnected=true;this.style={};this.dataset={};this.id='example';this.parentElement={closest:()=>null};this.contentHeight=240;}
    getBoundingClientRect(){if(this.currentHeight!==undefined){const height=this.currentHeight;delete this.currentHeight;return {height};}return {height:this.hidden?0:this.tagName==='DETAILS'&&!this.open?44:this.contentHeight};}
    removeAttribute(name){if(name==='data-disclosure-moving')delete this.dataset.disclosureMoving;}
    animate(frames,options){const animation={frames,options,cancel(){this.cancelled=true;}};animations.push(animation);return animation;}
  }
  const context={window:{matchMedia:()=>({matches:reduced})},document:{addEventListener:(name,fn)=>handlers[name]=fn,dispatchEvent:event=>events.push(event.detail)},
    WeakMap,getComputedStyle:()=>({boxSizing:'border-box'}),CustomEvent:class{constructor(type,options){this.detail=options.detail;}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/disclosure-motion.js'),'utf8'),context);
  return {api:context.window.lopmDisclosure,animations,events,Element,handlers,finish(){animations.at(-1).onfinish();}};
}
const h=harness(),panel=new h.Element();
assert.equal(h.api.toggle(panel),true);assert.equal(panel.hidden,false);
assert.equal(h.animations[0].frames[0].height,'0px');assert.equal(h.animations[0].frames[1].height,'240px');
h.finish();assert.equal(panel.style.height,'');assert.equal(panel.style.overflow,'');
panel.contentHeight=900;h.api.toggle(panel);assert.equal(panel.hidden,false,'Content remains mounted while collapsing.');
assert.equal(h.animations.at(-1).frames[0].height,'900px','Natural content growth is measured, without a fixed max-height.');
h.finish();assert.equal(panel.hidden,true);
const details=new h.Element(true);h.api.toggle(details);assert.equal(details.open,true);
const first=h.animations.at(-1);details.currentHeight=120;h.api.toggle(details);
assert.equal(first.cancelled,true);assert.equal(first.onfinish,null);
assert.equal(h.animations.at(-1).frames[0].height,'120px','Reversal starts at the current rendered height.');
assert.equal(h.api.isExpanded(details),false);details.currentHeight=80;h.api.toggle(details);assert.equal(h.api.isExpanded(details),true);
delete details.currentHeight;h.finish();assert.equal(details.open,true);assert.equal(details.dataset.disclosureMoving,undefined);
let prevented=false;
const summary={parentElement:details,closest:selector=>selector==='summary'?summary:null};
h.handlers.click({target:summary,button:0,preventDefault(){prevented=true;}});
assert.equal(prevented,true);h.finish();assert.equal(details.open,false,'Native summary click works in either direction.');
const quiet=harness(true),quietDetails=new quiet.Element(true),quietPanel=new quiet.Element();
quiet.api.toggle(quietDetails);quiet.api.toggle(quietPanel);quiet.api.toggle(quietPanel);
assert.equal(quietDetails.open,true);assert.equal(quietPanel.hidden,true);assert.equal(quiet.animations.length,0);
const hidden=new h.Element();hidden.parentElement.closest=()=>({hidden:true});h.api.toggle(hidden);
assert.equal(hidden.hidden,false);assert.equal(hidden.style.height,'','Hidden ancestors do not leave stale height constraints.');
console.log('Disclosure motion: native/custom controls, rapid reversal, growing content, cleanup and reduced motion passed.');
