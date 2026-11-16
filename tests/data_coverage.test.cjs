const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

(async()=>{
  const elements=new Map(),requests=[],renders=[],timers=[];
  const element=id=>{
    if(!elements.has(id))elements.set(id,{value:'',dataset:{},textContent:'',handlers:{},addEventListener(name,fn){this.handlers[name]=fn;}});
    return elements.get(id);
  };
  element('universe-select').value='VN30';element('group-select').value='Ngân hàng';element('symbol-select').value='VCB';
  const overview=Object.freeze({universe:'VN30',group:'Ngân hàng',symbol:'VCB',notional:'2500000000'});
  const storage=new Map([['lopm-data-universe-v1','VN100']]);
  let now=100000;
  class Clock extends Date{static now(){return now;}}
  const document={body:{dataset:{view:'methods',dataView:'status'}},hidden:false,getElementById:element};
  const context={window:{lopmDataView:{render:data=>renders.push(data)}},document,params:overview,state:overview,
    localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
    URLSearchParams,AbortController,Date:Clock,setInterval:fn=>timers.push(fn),setTimeout:()=>1,clearTimeout(){},dateTime:v=>v||'_',
    syncSelect:(id,options,value)=>{assert.equal(id,'data-universe-select');element(id).value=value;},
    fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/data-coverage.js'),'utf8'),context);
  const ui=context.window.lopmDataCoverage,settle=()=>new Promise(resolve=>setImmediate(resolve));
  const data=(universe,total)=>({mode:'data_coverage',source:'ssi_fastconnect',universe,group:'all',
    coverage:{scope:{symbols:total}},analysis:{mode:'saved',asof:'2026-11-16T11:29:57+07:00'},updated_at:'2026-11-16T13:00:00+07:00',
    available_universes:[{id:'VN30',count:30},{id:'VN100',count:100},{id:'HOSE',count:409},{id:'HNX',count:299},{id:'UPCOM',count:809}]});
  const resolve=(index,payload,ok=true)=>requests[index].resolve({status:ok?200:503,ok,json:async()=>payload});
  ui.activate();ui.activate();
  assert.equal(requests.length,1,'Only one coverage request may run.');
  assert.equal(requests[0].url,'/api/data-coverage?universe=VN100');
  element('data-universe-select').value='HOSE';element('data-universe-select').handlers.change();
  assert.equal(requests.length,2);assert.equal(requests[0].options.signal.aborted,true);
  resolve(0,data('VN100',100));await settle();
  assert.equal(renders.filter(Boolean).length,0,'A late old-universe response must not paint new-universe counts.');
  resolve(1,data('HOSE',409));await settle();
  assert.equal(renders.at(-1).universe,'HOSE');
  assert.equal(element('data-auto-update').textContent,'Tự cập nhật');
  assert.doesNotMatch(element('data-source-time').textContent,/FPT|VCB/);
  for(const [id,value] of [['universe-select','VN30'],['group-select','Ngân hàng'],['symbol-select','VCB']])assert.equal(element(id).value,value);
  assert.deepEqual(overview,{universe:'VN30',group:'Ngân hàng',symbol:'VCB',notional:'2500000000'});
  assert.equal(storage.get('lopm-data-universe-v1'),'HOSE');
  ui.refresh();assert.equal(requests.length,2,'Repeated refresh within five seconds is coalesced.');
  now+=5000;ui.refresh();resolve(2,{},false);await settle();
  assert.equal(renders.at(-1).universe,'HOSE','Temporary failure keeps the same-scope cached data.');
  assert.equal(element('data-auto-update').textContent,'Tự thử lại');
  document.body.dataset.view='overview';now+=5000;timers[0]();assert.equal(requests.length,3,'Hidden Data panel does not poll.');
  document.body.dataset.view='methods';document.body.dataset.dataView='guide';ui.activate();assert.equal(requests.length,3);
  document.body.dataset.dataView='status';ui.activate();
  assert.equal(requests.length,4);resolve(3,data('HOSE',409));await settle();
  assert.equal(element('data-auto-update').textContent,'Tự cập nhật');
  assert.ok(requests.every(r=>!/[?&](group|symbol|notional)=/.test(r.url)));
  console.log('Independent coverage: whole universe, unchanged overview, late responses, single request, cache/recovery and hidden-panel polling passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
