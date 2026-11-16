const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const sandbox={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/sizing-model.js'),'utf8'),sandbox);
const model=sandbox.window.lopmSizingModel;
// VSI's observed sparse book: all requested amounts exceed visible liquidity.
const row={symbol:'VSI',group:'Xây dựng',valid:true,mid:19225,sizing_price_vnd:19225,sizing_basis:'mid',lot_size:100,
  bids:[{price:19000,volume:1000},{price:18100,volume:200},{price:null,volume:0}],
  asks:[{price:19450,volume:100},{price:20100,volume:100},{price:null,volume:0}],
  spread_bps:450/19225*10000,spread_vnd:450,spread_ticks:9,analysis_at:'2026-11-13T13:26:06+07:00',analysis_mode:'saved'};
const payload={selected:row,ranking:[row],notional_vnd:1e9,alerts:[],alert_history:[{symbol:'VSI'}],alert_rules:{spread_threshold_bps:25},kpis:{},analysis:{mode:'saved'}};
const before=JSON.stringify(payload);
const small=model.resize(payload,1e8),large=model.resize(payload,5e9);
assert.equal(small.selected.buy.requested_shares,5200);
assert.equal(large.selected.buy.requested_shares,260000);
assert.equal(small.selected.buy.filled_shares,200);
assert.equal(small.selected.sell.filled_shares,1200);
assert.equal(small.selected.buy.vwap,19775);
assert.equal(small.selected.sell.vwap,18850);
assert.equal(small.selected.buy.filled_value_vnd,3955000);
assert.equal(small.selected.sell.filled_value_vnd,22620000);
assert.equal(large.selected.buy.filled_value_vnd,small.selected.buy.filled_value_vnd);
assert.ok(large.selected.buy.fill_ratio<small.selected.buy.fill_ratio);
assert.equal(small.alerts.length,1);
assert.deepEqual(Array.from(small.alerts[0].reasons,r=>r.kind),['capacity','spread']);
assert.equal(small.alert_history.length,0);
assert.equal(small.sizing_preview,true);
assert.equal(JSON.stringify(payload),before);
// Complete capacity changes as the amount passes into a second price level.
const deep={...row,mid:50000,sizing_price_vnd:50000,spread_bps:20,
  bids:[{price:49950,volume:2000},{price:49900,volume:10000}],
  asks:[{price:50050,volume:2000},{price:50100,volume:10000}]};
assert.equal(model.resizeRow(deep,1e8).buy.vwap,50050);
assert.ok(model.resizeRow(deep,5e8).buy.vwap>50050);
assert.equal(model.resizeRow(deep,5e8).buy.fill_ratio,1);
assert.ok(model.resizeRow(deep,1e9).buy.fill_ratio<1);
const oneSide={...deep,mid:null,asks:[],sizing_basis:'last_trade_or_reference'};
assert.equal(model.resizeRow(oneSide,1e8).buy.fill_ratio,0);
assert.equal(model.resizeRow(oneSide,1e8).buy.vwap,null);
assert.equal(model.resizeRow(oneSide,1e8).sell.slip_bps,null);
const belowLot={...deep,sizing_price_vnd:2_000_000};
assert.equal(model.resizeRow(belowLot,1e8).buy.requested_shares,0);
assert.equal(model.resizeRow(belowLot,1e8).buy.fill_ratio,null);
const invalid={...row,valid:false,buy:null,sell:null};
assert.equal(model.resizeRow(invalid,1e9),invalid);
assert.equal(model.resize(payload,NaN),null);
assert.equal(model.resize(payload,0),null);
assert.equal(model.resize(payload,5e9+1),null);
assert.equal(model.resize(payload,1e8-1),null);
const ten={...row,mid:50050,sizing_price_vnd:50050,book_level_limit:10,
  bids:Array.from({length:10},(_,i)=>({price:50000-i*100,volume:1000})),
  asks:Array.from({length:10},(_,i)=>({price:50100+i*100,volume:1000}))};
const extended=model.resizeRow(ten,200e6);
assert.equal(extended.buy.requested_shares,3900);assert.equal(extended.buy.fill_ratio,1);
assert.equal(extended.buy.filled_value_vnd,195960000);
assert.equal(model.resizeRow({...ten,asks:ten.asks.slice(0,3)},200e6).buy.fill_ratio,3000/3900);
console.log('Immediate resizing: real sparse book, level transitions, one-sided/invalid books, lot boundaries, alerts and immutable state passed.');
