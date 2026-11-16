const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const context={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/data-view.js'),'utf8'),context);
const model=context.window.lopmDataView.model;
const payload={analysis:{mode:'saved'},coverage:{scope:{symbols:30,received_prices:29,received_volumes:28,received_books:27,valid_books:26},
  collector:{symbols:100,received_prices:100,received_volumes:99,received_books:98}},
  data_status:{stream_connected:true,snapshots:14,days:[{day:'2026-11-11',snapshots:14},{day:'bad',snapshots:10}]}};
const m=model(payload);
assert.equal(m.scope.symbols,30);assert.equal(m.scope.received_volumes,28);assert.equal(m.collector.symbols,100);
assert.equal(m.connection,'Đã kết nối nguồn SSI');assert.equal(m.mode,'Đang dùng ảnh sổ đã lưu');
assert.equal(m.snapshots,14);assert.equal(m.days.length,1);
const zero=model({coverage:{scope:{symbols:3,received_prices:0,received_books:0,valid_books:0}},data_status:{snapshots:0,days:[],stream_connected:false}});
assert.equal(zero.scope.received_prices,0);assert.equal(zero.snapshots,0);assert.equal(zero.days.length,0);
assert.equal(zero.mode,'Chưa có sổ đủ dữ liệu để tính');assert.equal(zero.connection,'Chưa kết nối nguồn SSI');
const legacy=model({coverage:{visible_count:30,collected_count:100,received_prices:100,received_books:100},data_status:{}});
assert.equal(legacy.scope.received_prices,null);assert.equal(legacy.scope.symbols,30);assert.equal(legacy.collector.symbols,100);
assert.equal(legacy.snapshots,null);
const backfill=context.window.lopmDataView.backfillModel;
assert.equal(backfill({status:'filling'}).label,'Đang tải bù');
assert.match(backfill({status:'backoff'}).note,/tự tiếp tục/);
assert.match(backfill({status:'ready'}).note,/chưa có giao dịch giữ trống/);

// Exercise the renderer against IDs in the real page after folding its details.
const html=fs.readFileSync(path.join(__dirname,'../src/app/static/index.html'),'utf8');
const elements=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([,id])=>[id,{textContent:'',dataset:{},hidden:false,children:[],replaceChildren(...children){this.children=children;}}]));
const lookup=id=>{assert.ok(elements.has(id),`Data renderer references missing element ${id}`);return elements.get(id);};
Object.assign(context,{$:lookup,set:(id,value)=>{lookup(id).textContent=String(value);},
  fmt:(v,d=0)=>typeof v==='number'?v.toFixed(d):'_',money:v=>String(v),percent:v=>typeof v==='number'?`${v*100}%`:'_',
  dateTime:v=>v||'_',sourceTime:v=>v||'_',clock:v=>v||'_',
  node:(tag,cls,text)=>({tag,text,children:[],append(...children){this.children.push(...children);}}),
  fillList:(id,items)=>{lookup(id).children=items;},
  emptyTable:(id,cols,message)=>{lookup(id).children=[{message}];}});
context.window.lopmProductUX={priceCaption:r=>`Giá ${r.symbol}`};
const render=context.window.lopmDataView.render;
const sample={...payload,universe:'VN30',group:'all',available_universes:[{id:'VN30',label:'VN30'}],
  selected:{symbol:'FPT',valid:true,buy:{fill_ratio:1},sell:{fill_ratio:.5}},notional_vnd:1e9,
  ranking:[{symbol:'FPT',valid:true},{symbol:'ABC',valid:false}],
  data_status:{...payload.data_status,price_backfill:{status:'ready',archive:{bars:500,symbols:29},total_symbols:30,checked_symbols:30}}};
context.window.lopmDataView.renderGuide(sample);
render(sample);
assert.match(lookup('data-prices').textContent,/29.*30/);
assert.match(lookup('data-backfill-summary').textContent,/500.*29/);
assert.doesNotMatch(lookup('data-backfill-summary').textContent,/chưa có giao dịch/,'Long synchronization explanation belongs in expanded details.');
assert.match(lookup('data-backfill-note').textContent,/chưa có giao dịch/);
assert.match(lookup('data-reading-example').textContent,/FPT.*100%.*50%/);
const overviewExample=lookup('data-reading-example').textContent;
assert.equal(lookup('data-history-body').children.length,1);
assert.equal(lookup('data-coverage-note').hidden,false);
assert.equal(lookup('data-view-mode').dataset.mode,'saved');
render({...sample,ranking:[],data_status:{...sample.data_status,snapshots:0,days:[],price_backfill:{archive:{bars:0}}}});
assert.equal(lookup('data-reading-example').textContent,overviewExample,'Coverage updates must not replace the overview example.');
assert.match(lookup('data-backfill-summary').textContent,/chưa có nến/);
assert.equal(lookup('data-coverage-note').hidden,true);
render(null);
assert.equal(lookup('data-prices').textContent,'_');
assert.equal(lookup('data-history-body').children.length,0);
assert.equal(lookup('data-backfill-note').textContent,'');
assert.equal(lookup('data-reading-example').textContent,overviewExample);
context.window.lopmDataView.renderGuide(null);
assert.match(lookup('data-reading-example').textContent,/Tổng quan/);
console.log('Data coverage, compact renderer, real element IDs, missing/zero data and loading reset passed.');
