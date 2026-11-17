const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const elements=new Map();
function element(id){
  if(!elements.has(id))elements.set(id,{textContent:'',hidden:false,disabled:false,title:'',classList:{add(){}},replaceChildren(){}});
  return elements.get(id);
}
let now=Date.parse('2026-11-13T16:00:00+07:00');
class Clock extends Date{static now(){return now;}}
const sandbox={window:{},Date:Clock,document:{body:{dataset:{}},getElementById:element},
  localStorage:{getItem:()=>null},setInterval(){},
  state:{phase_code:'closed',analysis:{mode:'saved',asof:'2026-11-13T14:29:55+07:00'},
    selected:{symbol:'FPT',trade_time:'2026-11-13T14:29:51+07:00'}},
  set:(id,value)=>{element(id).textContent=String(value);},clock:()=> '16:00:00',dateTime:v=>v,sourceTime:v=>v};
for(const name of ['dashboard-model.js','product-ux.js'])vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/',name),'utf8'),sandbox);
const freshness=sandbox.window.lopmFreshness;
freshness.received();freshness.paint();
assert.equal(element('connection-label').textContent,'Ảnh đã lưu');
assert.equal(element('auto-update-state').textContent,'Tự cập nhật');
assert.equal(element('reference-banner').hidden,true,'A saved snapshot is normal, not an error banner.');
assert.match(sandbox.window.lopmProductUX.priceCaption(sandbox.state.selected,{source:false}),/14:29:51/);
assert.match(sandbox.state.analysis.asof,/14:29:55/);
assert.equal(elements.has('last-updated'),false,'Common status does not repeat the quote timestamp.');
assert.equal(elements.has('book-updated'),false,'Book time is shown with the book and ranking.');
// A background tab's paused timers do not prove a failed connection or a new
// market tick. Only an actual failed product request changes the connection.
now+=2*60*60*1000;freshness.paint();
assert.equal(sandbox.document.body.dataset.connection,'connected');
assert.equal(element('connection-label').textContent,'Ảnh đã lưu');
freshness.lost();
assert.equal(sandbox.document.body.dataset.connection,'cached');
assert.equal(element('auto-update-state').textContent,'Tự động thử lại');
assert.equal(element('export-button').disabled,true);
assert.equal(element('reference-banner').hidden,false);
assert.match(element('reference-banner').textContent,/đồng bộ gần nhất/);
assert.match(sandbox.window.lopmProductUX.priceCaption(sandbox.state.selected,{source:false}),/14:29:51/,'Network receipt time must not replace market time.');
assert.match(sandbox.state.analysis.asof,/14:29:55/);
assert.doesNotMatch(sandbox.window.lopmProductUX.priceCaption(sandbox.state.selected,{source:false}),/SSI/);
assert.match(sandbox.window.lopmProductUX.priceCaption({price_basis:'ssi_ohlc_daily',price_asof_date:'2026-11-12'},{source:false}),/12\/11\/2026.*nến ngày/,'Compact captions retain older prices and historical-bar provenance.');
freshness.received();freshness.paint();
assert.equal(sandbox.document.body.dataset.connection,'connected');
assert.equal(element('connection-label').textContent,'Ảnh đã lưu');
assert.equal(element('reference-banner').hidden,true,'The reconnecting notice clears after recovery.');
console.log('Automatic status: quiet closed market, background timers, real network loss and recovery passed.');
