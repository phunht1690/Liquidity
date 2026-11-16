const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function harness(reduced=false){
  const elements=new Map(),lists=[],events=[],animations=[];
  let focused=null;
  class Element{
    constructor(id,attrs={},dataset={}){this.id=id;this.attrs=attrs;this.dataset=dataset;this.handlers={};this.hidden=false;this.tabIndex=-1;elements.set(id,this);}
    getAttribute(name){return this.attrs[name];}
    setAttribute(name,value){this.attrs[name]=value;}
    addEventListener(name,fn){this.handlers[name]=fn;}
    focus(){focused=this.id;}
    animate(){animations.push(this.id);}
    querySelectorAll(){return this.tabs||[];}
  }
  for(const [name,values] of [['market',['stocks','sectors']],['book',['orders','trades']],['data',['status','guide']]]){
    const list=new Element(name,{}, {workspaceTabs:name});list.tabs=[];lists.push(list);
    for(const [i,value] of values.entries()){
      const panel=new Element(`${name}-${value}-panel`);
      const dataset={tabValue:value};
      if(name==='data')dataset.tabHash=value==='guide'?'how-it-works':'data';
      list.tabs.push(new Element(`${name}-${value}-tab`,{'aria-controls':panel.id,'aria-selected':String(i===0)},dataset));
    }
  }
  const document={body:{dataset:{}},querySelectorAll:()=>lists,getElementById:id=>elements.get(id),dispatchEvent:e=>events.push(e.detail)};
  new Element('data-off-hours');
  const location={hash:'#data'};
  const sandbox={window:{matchMedia:()=>({matches:reduced})},document,location,CustomEvent:class{constructor(type,options){this.detail=options.detail;}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/workspace-ui.js'),'utf8'),sandbox);
  const key=(id,name)=>{let prevented=false;elements.get(id).handlers.keydown({key:name,preventDefault(){prevented=true;}});return prevented;};
  return {ui:sandbox.window.lopmWorkspaceUI,elements,document,location,events,animations,key,focused:()=>focused};
}
const h=harness();
assert.equal(h.elements.get('market-stocks-panel').hidden,false);
assert.equal(h.elements.get('market-sectors-panel').hidden,true);
assert.equal(h.elements.get('book-orders-panel').hidden,false);
assert.equal(h.elements.get('book-trades-panel').hidden,true);
h.elements.get('market-sectors-tab').handlers.click();
assert.equal(h.ui.marketView(),'sectors');
assert.equal(h.elements.get('market-stocks-panel').hidden,true);
assert.equal(h.elements.get('market-sectors-panel').hidden,false);
assert.equal(h.document.body.dataset.marketView,'sectors');
assert.deepEqual(h.animations,['market-sectors-panel']);
assert.equal(h.key('market-sectors-tab','ArrowRight'),true);
assert.equal(h.focused(),'market-stocks-tab');
assert.equal(h.elements.get('market-stocks-tab').tabIndex,0);
assert.equal(h.elements.get('market-sectors-tab').getAttribute('aria-selected'),'false');
h.key('market-stocks-tab','End');assert.equal(h.ui.marketView(),'sectors');
h.key('market-sectors-tab','Home');assert.equal(h.ui.marketView(),'stocks');
assert.equal(h.key('market-stocks-tab','Tab'),false,'Normal Tab leaves the tablist.');
h.ui.selectBook('trades');
assert.equal(h.elements.get('book-trades-panel').hidden,false);
assert.equal(h.elements.get('book-orders-panel').hidden,true);
assert.equal(h.ui.marketView(),'stocks','Book choice does not change the market view.');
const before=h.animations.length;h.ui.selectBook('trades',{animate:true});
assert.equal(h.animations.length,before,'Repeated selection does not replay animations.');
const quiet=harness(true);quiet.ui.selectMarket('sectors',{animate:true});
assert.equal(quiet.animations.length,0,'Reduced motion suppresses transitions.');
// Direct links must expose the right inner panel before app.js scrolls to it.
h.ui.syncDataRoute('how-it-works');
assert.equal(h.elements.get('data-guide-panel').hidden,false);
assert.equal(h.elements.get('data-status-panel').hidden,true);
const priorFocus=h.focused(),priorAnimations=h.animations.length;
h.ui.syncDataRoute('how-it-works');
assert.equal(h.focused(),priorFocus,'Route sync does not steal keyboard focus.');
assert.equal(h.animations.length,priorAnimations,'Route sync does not animate twice.');
h.ui.syncDataRoute('overview');
assert.equal(h.elements.get('data-guide-panel').hidden,false,'Other pages do not reset the remembered data choice.');
h.ui.syncDataRoute('data-fields');
assert.equal(h.elements.get('data-status-panel').hidden,false);
assert.equal(h.elements.get('data-guide-panel').hidden,true);
h.ui.syncDataRoute('data-off-hours');assert.equal(h.elements.get('data-off-hours').open,true);
h.elements.get('data-guide-tab').handlers.click();assert.equal(h.location.hash,'how-it-works');
h.key('data-guide-tab','ArrowLeft');assert.equal(h.location.hash,'data');
assert.equal(h.focused(),'data-status-tab');
console.log('Workspace tabs: independent panels, deep links, history routes, keyboard/focus and reduced motion passed.');
