const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const sandbox={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/alert-model.js'),'utf8'),sandbox);
const model=sandbox.window.lopmAlertModel;
const alerts=[
  {symbol:'AAA',buy_fill:1,sell_fill:.9,spread_bps:30,reasons:[{kind:'capacity',label:'Thiếu lượng chờ'}]},
  {symbol:'ZZZ',buy_fill:.1,sell_fill:1,spread_bps:60,spread_vnd:100,spread_ticks:2,reasons:[{kind:'capacity',label:'Thiếu lượng chờ'},{kind:'spread',label:'Vượt ngưỡng'}]},
  {symbol:'BBB',buy_fill:1,sell_fill:1,spread_bps:90,reasons:[{kind:'spread',label:'Vượt ngưỡng'}]}
];
const symbols=rows=>Array.from(rows,r=>r.symbol);
assert.deepEqual(symbols(model.select(alerts)),['ZZZ','AAA','BBB']);
assert.deepEqual(symbols(model.select(alerts,{sort:'spread'})),['BBB','ZZZ','AAA']);
assert.deepEqual(symbols(model.select(alerts,{sort:'symbol'})),['AAA','BBB','ZZZ']);
assert.deepEqual(symbols(model.select(alerts,{kind:'spread',search:' zZ '})),['ZZZ']);
assert.equal(model.select(alerts,{search:'NONE'}).length,0);
assert.deepEqual(alerts.map(r=>r.symbol),['AAA','ZZZ','BBB']);
const payload={source:'ssi_fastconnect',universe:'VN30',group:'all',notional_vnd:1e9,analysis_dataset_id:'saved-1',
  alert_rules:{spread_threshold_bps:50},alerts,ranking:[],coverage:{valid_book_count:3,visible_count:4}};
assert.deepEqual({...model.summary(payload)},{total:3,capacity:2,spread:2,eligible:3,visible:4});
const exported=model.csv(payload,model.select(alerts,{search:'ZZZ'}));
assert.ok(exported.startsWith('\ufeff"source"'));
assert.ok(exported.includes('"50","ZZZ"'));
assert.equal(exported.split('\r\n').filter(Boolean).length,2);
assert.ok(exported.includes('"10","100","100","0.6","2"'));
const injected={...alerts[0],symbol:'=SUM(1,2)',reasons:[{label:'A "quoted" condition'}]};
const escaped=model.csv(payload,[injected]);
assert.ok(escaped.includes('"\'=SUM(1,2)"'));
assert.ok(escaped.includes('"A ""quoted"" condition"'));
console.log('Alert sorting, overlapping counts, search, threshold metadata and CSV escaping passed.');
