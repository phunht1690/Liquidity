const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../src/app/static/app.js'),'utf8');
const calls=[],elements=new Map();
for(const id of ['overview-view','alerts-view','methods-view','export-button','page-title','page-subtitle','cost-section','telemetry-panel','how-it-works']){
  elements.set(id,{id,hidden:false,textContent:'',classList:{toggle(){}},getBoundingClientRect:()=>({top:-1000}),scrollIntoView:options=>calls.push({target:id,...options})});
}
const document={body:{dataset:{view:'overview'}},getElementById:id=>elements.get(id),querySelectorAll:selector=>selector==='section.view'?['overview-view','alerts-view','methods-view'].map(id=>elements.get(id)):[]};
const window={scrollY:1400,matchMedia:()=>({matches:false}),scrollTo:options=>calls.push(options),lopmSizingControls:{mount(){},sync(){}},
  lopmWorkspaceUI:{syncDataRoute(){},syncOverviewRoute(hash){calls.push({route:hash});}}};
const context=vm.createContext({window,document,location:{hash:'#book'},requestAnimationFrame:fn=>fn(),drawCharts(){},console});
vm.runInContext(source.slice(0,source.indexOf('\nfunction chooseSymbol')),context);
vm.runInContext('applyView()',context);
assert.equal(elements.get('overview-view').hidden,false);
assert.equal(elements.get('methods-view').hidden,true);
assert.equal(calls.find(c=>c.behavior)?.behavior,'instant','Switching an Overview tab never slides through a long page.');
assert.equal(calls.some(c=>c.target),false,'Overview tabs are not scroll targets.');
assert.equal(calls.find(c=>c.behavior).top,400,'A tab switched from deep content stays near the common tab bar.');
calls.length=0;context.location.hash='#ranking';vm.runInContext('applyView()',context);
assert.equal(calls[0].route,'ranking');assert.equal(calls.some(c=>c.target),false);
calls.length=0;context.location.hash='#cost';vm.runInContext('applyView()',context);
assert.equal(calls[0].route,'cost');assert.equal(calls.find(c=>c.target)?.target,'cost-section','Specific scale links still reach the estimate within the book panel.');
calls.length=0;context.location.hash='#how-it-works';vm.runInContext('applyView()',context);
assert.equal(document.body.dataset.view,'methods');assert.equal(elements.get('overview-view').hidden,true);
assert.equal(calls.find(c=>c.target)?.target,'how-it-works');
calls.length=0;context.location.hash='#stock';vm.runInContext('applyView()',context);
assert.equal(calls.find(c=>c.behavior)?.top,0,'Entering Overview from another page starts at its filters.');
// The secondary cost chart is drawn only when visible, using the latest size state.
const comparison={open:false,addEventListener(type,fn){this[type]=fn;}},plots=[];
const drawing=vm.createContext({
  state:{cost_curve:[{notional:1e9}],history:[]},currentView:()=> 'overview',
  window:{lopmWorkspaceUI:{overviewView:()=> 'book'},lopmChart:{render:payload=>plots.push(['price',payload])}},
  $:id=>{assert.equal(id,'cost-comparison');return comparison;},
  requestAnimationFrame:fn=>fn(),drawCost:points=>plots.push(['cost',points]),drawHistory(){throw Error('Unexpected fallback');}
});
vm.runInContext(source.slice(source.indexOf('function drawCharts(){'),source.indexOf('\nwindow.addEventListener("hashchange"')),drawing);
vm.runInContext('drawCharts()',drawing);assert.equal(plots.length,0);
comparison.open=true;comparison.toggle();assert.equal(plots.length,1);assert.equal(plots[0][1][0].notional,1e9);
comparison.open=false;drawing.state={cost_curve:[{notional:2e9}],history:[]};vm.runInContext('drawCharts()',drawing);
assert.equal(plots.length,1,'Background updates do not plot a collapsed comparison.');
comparison.open=true;comparison.toggle();assert.equal(plots[1][1][0].notional,2e9,'Reopening uses the newest size calculation.');
drawing.window.lopmWorkspaceUI.overviewView=()=> 'stock';vm.runInContext('drawCharts()',drawing);
assert.equal(plots.at(-1)[0],'price','The stock view continues to draw only its price chart.');
console.log('Overview navigation: independent panels, deep links, and current data on cost-chart expansion passed.');
