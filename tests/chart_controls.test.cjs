const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../src/app/static'),html=fs.readFileSync(path.join(root,'index.html'),'utf8');

// Exercise the real view/controller with a small DOM; no browser or source API.
function harness(){
  const elements=new Map(),frames=[],listeners={};let document;
  class Element{
    constructor(tag='div',attrs={}){
      this.tag=tag;this.attrs={...attrs};this.id=attrs.id;this.hidden='hidden' in attrs;this.checked='checked' in attrs;
      this.children=[];this.handlers={};this.style={};this.dataset={};this.textContent='';this.value=attrs.value||'';
      this.clientWidth=600;this.clientHeight=320;this.classList={add(){},remove(){},toggle(){}};
    }
    get options(){return this.tag==='select'?this.children:undefined;}
    get selectedOptions(){return this.tag==='select'?this.children.filter(n=>n.value===this.value):undefined;}
    setAttribute(k,v){this.attrs[k]=String(v);if(k==='value')this.value=String(v);}
    getAttribute(k){return this.attrs[k];}
    addEventListener(k,fn){(this.handlers[k]||=[]).push(fn);}
    fire(k,event={}){for(const fn of this.handlers[k]||[])fn({preventDefault(){},stopPropagation(){},...event});}
    focus(){document.activeElement=this;}
    append(...nodes){for(const node of nodes){node.remove?.();node.parentElement=this;this.children.push(node);}}
    replaceChildren(...nodes){for(const n of this.children)n.parentElement=null;this.children=[];this.append(...nodes);}
    remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this);this.parentElement=null;}
    before(node){const parent=this.parentElement;node.parentElement=parent;parent.children.splice(parent.children.indexOf(this),0,node);}
    replaceWith(node){const parent=this.parentElement;node.remove();parent.children.splice(parent.children.indexOf(this),1,node);node.parentElement=parent;this.parentElement=null;}
    contains(node){return node===this||this.children.some(n=>n.contains?.(node));}
    querySelector(selector){return selector.startsWith('option')?this.children.find(n=>n.value==='candles'):null;}
    querySelectorAll(){return [...elements.values()].filter(n=>n.id?.startsWith('cache-')&&['input','button','select'].includes(n.tag));}
    setPointerCapture(){}
    getBoundingClientRect(){return {left:0,top:0,width:600,height:320};}
    showModal(){this.open=true;}
    close(){this.open=false;this.fire('close');}
  }
  const attrs=raw=>Object.fromEntries([...raw.matchAll(/([\w-]+)(?:="([^"]*)")?/g)].map(m=>[m[1],m[2]??'']));
  for(const m of html.matchAll(/<([a-z][\w-]*)\b([^<>]*\bid="([^"]+)"[^<>]*)>/g))elements.set(m[3],new Element(m[1],attrs(m[2])));
  const get=id=>{assert.ok(elements.has(id),id);return elements.get(id);};
  for(const m of html.matchAll(/<select\b[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)){
    const select=get(m[1]);
    for(const o of m[2].matchAll(/<option\b([^>]*)>([^<]*)<\/option>/g)){const el=new Element('option',attrs(o[1]));el.textContent=o[2];select.append(el);}
    select.value=(select.children.find(n=>'selected' in n.attrs)||select.children[0])?.value||'';
  }
  document={body:new Element(),activeElement:null,hidden:false,addEventListener(k,fn){listeners[k]=fn;},createComment:()=>new Element('comment')};
  const home=new Element();home.append(get('telemetry-panel'));get('telemetry-panel').append(get('history-chart'),get('chart-navigator'));
  const context={window:{scrollY:120,scrollTo(){},addEventListener(k,fn){listeners[k]=fn;}},document,console,
    $:get,set:(id,v)=>get(id).textContent=String(v),node:(tag,cls,text)=>{const e=new Element(tag);e.textContent=text;return e;},
    svg:(tag,a,text)=>{const e=new Element(tag,a);e.textContent=text;return e;},
    dateTime:v=>v||'_',clock:v=>v||'_',valid:v=>typeof v==='number'&&Number.isFinite(v),fmt:v=>v??'_',
    ResizeObserver:class{observe(){}},requestAnimationFrame:fn=>(frames.push(fn),frames.length),
    setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,clearInterval(){},AbortController,URLSearchParams,
    currentView:()=> 'overview',drawEmpty(){},params:{symbol:'FPT'},state:null};
  context.option=(v,t)=>{const e=new Element('option',{value:v});e.textContent=t;return e;};
  const run=file=>vm.runInNewContext(fs.readFileSync(path.join(root,file),'utf8'),context);
  run('chart-view-model.js');run('chart-viewport.js');
  return {get,context,run,home,flush(){let n=0;while(frames.length){assert.ok(++n<30);frames.shift()();}}};
}
const rows=Array.from({length:60},(_,i)=>({timestamp:new Date(Date.parse('2026-11-16T09:15:00+07:00')+i*60000).toISOString(),
  trading_date:'2026-11-16',valid:true,price_available:true,last_price_vnd:50000+i*10,close:50000+i*10,
  volume_shares:100,spread_bps:10,depth_min_vnd:1e9,avg_match_price_vnd:50000,reference_price_vnd:50000}));

(async()=>{
  const h=harness(),v=h.context.window.lopmChartViewport;
  assert.equal(h.get('chart-settings').hidden,true);
  assert.equal(h.get('chart-settings-toggle').textContent,'Nâng cao');
  assert.equal(h.get('chart-navigator-panel').hidden,true,'Navigator is hidden in the compact chart.');
  const redraw=()=>v.prepare(rows,{key:'FPT',bars:true,onChange:redraw});redraw();assert.equal(h.get('chart-reset').hidden,true);
  assert.match(h.get('chart-visible-range').textContent,/16\/11\/2026/);
  assert.ok(!h.get('chart-visible-range').textContent.includes('60/60'),'Full range does not repeat the header count.');
  h.get('chart-navigator').fire('pointerdown',{button:0,clientX:100,pointerId:1,target:{dataset:{}}});
  h.get('chart-navigator').fire('pointermove',{clientX:250});h.get('chart-navigator').fire('pointerup',{clientX:250});h.flush();
  assert.ok(v.bounds()[0]>0&&v.bounds()[1]<rows.length-1);assert.equal(h.get('chart-reset').hidden,false);
  const selection=Array.from(v.bounds());h.get('chart-settings-toggle').fire('click');assert.equal(h.get('chart-settings').hidden,false);
  h.get('chart-type').value='candles';h.get('chart-ma20').checked=true;
  h.get('chart-expand').fire('click');assert.equal(h.get('telemetry-panel').parentElement,h.get('chart-dialog'));
  assert.equal(h.get('chart-navigator-panel').hidden,false);
  assert.equal(h.get('chart-settings').hidden,false);assert.equal(h.get('chart-type').value,'candles');
  h.get('chart-expand').fire('click');assert.equal(h.get('telemetry-panel').parentElement,h.home);
  assert.equal(h.get('chart-navigator-panel').hidden,true);
  assert.deepEqual(Array.from(v.bounds()),selection);assert.equal(h.get('chart-ma20').checked,true);
  h.get('chart-settings-toggle').fire('click');h.get('chart-expand').fire('click');h.get('chart-dialog').close();
  assert.equal(h.get('chart-navigator-panel').hidden,true,'Esc/dialog close hides the navigator again.');
  assert.equal(h.get('chart-settings').hidden,true,'Collapsed settings stay collapsed across fullscreen.');
  h.get('chart-reset').fire('click');h.flush();v.prepare(rows,{key:'FPT',bars:true});assert.equal(h.get('chart-reset').hidden,true);
  h.get('chart-timeframe').value='1d';v.prepare([{...rows[0]},{...rows[0],timestamp:'2026-11-17T00:00:00+07:00'}],{key:'daily',bars:true});
  assert.ok(!h.get('chart-visible-range').textContent.includes('00:00'),'Daily ranges show dates.');
  assert.doesNotThrow(()=>v.prepare([{...rows[0],timestamp:'invalid'}],{key:'unknown-date',bars:true}));

  const live=harness(),requests=[],plots=[];live.run('chart-engine.js');
  Object.assign(live.context.window.lopmChartEngine,{price:(points,options)=>plots.push({points,options}),liquidity:(points,options)=>plots.push({points,options})});
  const payload={selected:{symbol:'FPT',change_percent:1,trading_date:'2026-11-16'},universe:'VN30',updated_at:'2026-11-16T10:15:00+07:00',history:rows,
    analysis:{mode:'live',asof:'2026-11-16T10:15:00+07:00'},data_status:{days:[]}};
  live.context.state=payload;
  live.context.fetch=async url=>{
    requests.push(url);const replay=url.startsWith('/api/chart-cache');
    return {ok:true,json:async()=>replay?{source:'ssi_fastconnect',symbol:'FPT',universe:'VN30',day:'2026-11-16',points:rows,
      days:[{day:'2026-11-16',snapshots:60}],universes:[{id:'VN30',count:30}],symbols:['FPT'],summary:{price_observations:60,liquidity_observations:60}}:
      {source:'ssi_fastconnect_ohlc',symbol:'FPT',range:'session',timeframe:'5m',bars:rows.slice(0,46),updated_at:payload.updated_at,complete_range:false}};
  };
  const settle=()=>new Promise(resolve=>setImmediate(resolve));live.run('chart-replay.js');await settle();
  assert.equal(plots.at(-1).options.reference,true);assert.equal(plots.at(-1).options.average,false);assert.equal(plots.at(-1).options.ma20,false);
  assert.equal(live.get('chart-ma50').disabled,true);assert.match(live.get('ma50-control').title,/đang có 46/);
  assert.match(live.get('chart-data-status').textContent,/Một phần khoảng chọn/);
  assert.ok(live.get('chart-source-fields').children.length>0);assert.ok(!live.get('history-caption').textContent.includes('FPT'));
  assert.ok(!live.get('history-caption').textContent.includes('46'),'The heading shows the range and interval without repeating sample counts.');
  const candleCount=live.get('chart-source-fields').children.find(row=>row.children[0].textContent==='Số nến');
  assert.equal(candleCount.children[1].textContent,46,'The actual sample count remains available with the source details.');
  const count=requests.length;live.get('chart-settings-toggle').fire('click');live.get('chart-expand').fire('click');live.get('chart-dialog').close();live.flush();
  assert.equal(requests.length,count,'Opening settings/fullscreen does not fetch data.');
  live.get('chart-range').value='custom';live.get('chart-range').fire('change');await settle();
  assert.equal(live.get('chart-custom-range').hidden,false);
  live.get('chart-metric').value='liquidity';live.get('chart-metric').fire('change');await settle();
  assert.equal(live.get('liquidity-day-control').hidden,false);assert.equal(live.get('chart-range-control').hidden,true);
  assert.match(live.get('chart-source-note').textContent,/Lượng chờ/);
  live.get('chart-cache').fire('click');await settle();
  assert.equal(live.get('cache-controls').hidden,false);assert.equal(live.get('chart-range-control').hidden,true);
  assert.match(live.get('chart-source-note').textContent,/Chỉ biểu đồ phát lại/);
  console.log('Chart controls: collapse/fullscreen state, brush/reset, dates, live/replay, source coverage and local-only UI actions passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
