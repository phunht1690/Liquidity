const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const box={window:{}};
for(const file of ['liquidity-brief-model.js','sizing-model.js'])vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static',file),'utf8'),box);
const m=box.window.lopmLiquidityBriefModel,sizing=box.window.lopmSizingModel;
const asof='2026-11-13T14:29:55+07:00';
const row=(symbol,extra={})=>({symbol,name:symbol,group:'Ngân hàng',valid:true,analysis_at:asof,last_price_vnd:10000,
  spread_bps:20,depth_min_vnd:200e6,buy:{fill_ratio:1},sell:{fill_ratio:1},...extra});
const rows=[row('AAA'),row('BBB',{spread_bps:40,depth_min_vnd:0,buy:{fill_ratio:0}}),
  row('CCC',{group:'Công nghệ',last_price_vnd:null,spread_bps:null,depth_min_vnd:null,buy:null,sell:null}),
  row('DDD',{group:'Công nghệ',valid:false,spread_bps:9999}),
  row('EEE',{analysis_at:'2026-11-12T14:29:55+07:00',spread_bps:9999}),
  row('FFF',{group:'Công nghệ',spread_bps:null,depth_min_vnd:50e6,buy:{fill_ratio:.4},sell:null})];
const p={source:'ssi_fastconnect',ranking:rows,selected:rows[0],analysis:{mode:'saved',asof},universe:'HOSE',group:'all',
  notional_vnd:1e9,alert_rules:{spread_threshold_bps:25},available_universes:[{id:'HOSE',label:'HOSE'}]};
const original=JSON.stringify(p),s=m.summarize(p);
assert.equal(s.total,6);assert.equal(s.priced,5);assert.equal(s.books,4);
assert.equal(s.spreadCount,2);assert.equal(s.medianSpreadBps,30);
assert.equal(s.depthCount,3);assert.equal(s.medianDepthVnd,50e6); // Known zero counts; missing data does not.
assert.equal(s.capacityKnown,3);assert.equal(s.partial,2);assert.equal(s.comparable,2);
assert.equal(s.complete,1);assert.equal(s.completeRatio,.5);assert.equal(s.wide,1);
assert.deepEqual(Array.from(m.filterRows(p,'valid'),r=>r.symbol),['AAA','BBB','CCC','FFF']);
assert.deepEqual(Array.from(m.filterRows(p,'capacity'),r=>r.symbol),['BBB','FFF']);
assert.deepEqual(Array.from(m.filterRows(p,'complete'),r=>r.symbol),['AAA']);
assert.deepEqual(Array.from(m.filterRows(p,'spread'),r=>r.symbol),['BBB']);
assert.equal(m.filterRows(p,'all').length,6);
const groups=m.sectors(p),bank=groups.find(g=>g.name==='Ngân hàng'),tech=groups.find(g=>g.name==='Công nghệ');
assert.equal(bank.total,3);assert.equal(bank.books,2);assert.equal(bank.medianDepthVnd,100e6);
assert.equal(tech.total,3);assert.equal(tech.books,2);assert.equal(tech.medianSpreadBps,null);
assert.equal(tech.medianDepthVnd,50e6);assert.equal(tech.completeRatio,null);
const empty=m.summarize({...p,ranking:[rows[3],rows[4]]});
assert.equal(empty.books,0);assert.equal(empty.medianSpreadBps,null);assert.equal(empty.completeRatio,null);
assert.equal(m.summarize({...p,analysis:{}}).books,0);
assert.equal(m.pct(2),'_');assert.equal(m.pct(-1),'_');assert.equal(m.pct(0),'0,0%');

// The quick filters and sector ratios follow the actual existing size model,
// including an immediate complete -> partial transition without any API request.
const deep=row('GGG',{mid:10000,sizing_price_vnd:10000,lot_size:100,
  bids:[{price:9990,volume:100000}],asks:[{price:10010,volume:100000}]});
const sized={...p,ranking:[deep],selected:deep,alerts:[],alert_history:[]};
const low=sizing.resize(sized,1e8),high=sizing.resize(sized,5e9);
assert.equal(m.summarize(low).complete,1);assert.equal(m.summarize(low).partial,0);
assert.equal(m.summarize(high).complete,0);assert.equal(m.summarize(high).partial,1);
assert.deepEqual(Array.from(m.attention(high),r=>r.symbol),Array.from(high.alerts,r=>r.symbol));
assert.deepEqual(Array.from(m.filterRows(high,'capacity'),r=>r.symbol),['GGG']);
assert.equal(m.sectors(high)[0].completeRatio,0);
assert.throws(()=>m.reportHTML(high),/đồng bộ/);

const report=m.reportHTML({...p,private_token:'NEVER_EXPORT_THIS',ranking:[...rows,
  row('XXX',{name:'<img src="https://invalid" onerror="alert(1)">',group:'<script>alert(1)</script>'})]},'2026-11-15T21:30:00+07:00');
assert.ok(report.startsWith('<!doctype html>'));
assert.ok(report.includes('default-src \'none\''));
assert.ok(!/<(script|iframe|img|link)\b/i.test(report));
assert.ok(report.includes('&lt;img'));assert.ok(!report.includes('NEVER_EXPORT_THIS'));
assert.ok(report.includes('13/11/2026'));assert.ok(report.includes('15/11/2026'));
assert.ok(report.includes('toàn bộ 7 mã'));
assert.ok(report.includes('BBB'));assert.ok(report.includes('FFF'));
assert.ok(report.includes('40,0%'));assert.ok(report.includes('0,0%'));
assert.equal(JSON.stringify(p),original);
// Sector trading value has its own date and coverage, independent of valid books.
const traded={...p,updated_at:'2026-11-16T13:00:00+07:00',ranking:[
  row('AAA',{turnover_basis:'ssi_daily_summary',turnover_day:'2026-11-13',turnover_vnd:1e9}),
  row('BBB',{turnover_basis:'ssi_daily_summary',turnover_day:'2026-11-12',turnover_vnd:999e9}),
  row('CCC',{group:'Công nghệ',valid:false,turnover_basis:'ssi_daily_summary',turnover_day:'2026-11-13',turnover_vnd:0}),
  row('DDD',{turnover_basis:'ssi_daily_summary',turnover_day:'2099-01-01',turnover_vnd:999e9})]};
const totals=m.summarize(traded);assert.equal(totals.turnoverDay,'2026-11-13');
assert.equal(totals.turnoverCount,2);assert.equal(totals.turnoverVnd,1e9);
assert.equal(m.sectors(traded,'turnover').find(g=>g.name==='Công nghệ').turnoverVnd,0);
const previous=m.summarize({...traded,ranking:[row('AAA',{daily_reference:{source:'ssi_securities_summary',day:'2026-11-13',turnover_vnd:2e9}}),
  row('BBB',{daily_reference:{source:'ssi_securities_summary',day:'2026-11-12',turnover_vnd:999e9}})]});
assert.equal(previous.turnoverDay,'2026-11-13');assert.equal(previous.turnoverCount,1);assert.equal(previous.turnoverVnd,2e9);
const marketReport=m.reportHTML({...traded,market_activity:{items:[{scope:'<img src=x onerror=alert(1)>',day:'2026-11-13',matched_value_vnd:1e9,negotiated_value_vnd:0}]}});
assert.ok(marketReport.includes('Khớp lệnh &amp; thỏa thuận thị trường'));
assert.ok(marketReport.includes('&lt;img'));assert.ok(!/<img\b/.test(marketReport));
console.log('Liquidity summaries: metric-specific coverage, missing/zero/one-sided data, common snapshot, sectors, immediate sizing, alert parity and safe standalone HTML passed.');
