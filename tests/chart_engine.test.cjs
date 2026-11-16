const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const sandbox={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/chart-engine.js'),'utf8'),sandbox);
const engine=sandbox.window.lopmChartEngine;
const bars=Array.from({length:21},(_,i)=>({close:i+1}));
const mean=engine.movingAverage(bars,20);
assert.equal(mean.slice(0,19).every(v=>v===null),true);
assert.equal(mean[19],10.5);assert.equal(mean[20],11.5);
// Zooming into the last two candles must retain MA values from earlier candles.
const master=bars.map((p,i)=>({...p,timestamp:`2026-11-${String(i+1).padStart(2,'0')}T09:15:00+07:00`}));
const zoomed=engine.priceRows(master.slice(19),master);
assert.equal(zoomed[0]._ma20,10.5);assert.equal(zoomed[1]._ma20,11.5);
assert.equal(master[19]._ma20,undefined);
assert.equal(engine.movingAverage([{close:null},...bars.slice(0,19)],20).every(v=>v===null),true);
// The mini-chart's color follows reference change, not its local slope.
assert.equal(engine.trendColor(1),engine.colors.buy);
assert.equal(engine.trendColor(-1),engine.colors.down);
assert.equal(engine.trendColor(null),engine.colors.neutral);
assert.equal(engine.trendColor(0),engine.colors.neutral);
// A historical range cannot inherit the current session's percentage/color.
const old=[{timestamp:'2026-11-06T14:45:00+07:00',trading_date:'2026-11-06',last_price_vnd:50100}];
assert.equal(engine.referenceChange(old,1.11,'2026-11-13'),null);
assert.equal(engine.referenceChange(old,-2,'2026-11-06'),-2);
assert.equal(engine.referenceChange([{...old[0],reference_price_vnd:50000}],9,'2026-11-13')>.19,true);
// Direct SVG targets support table rows; missing prices must break the path.
const chart={attrs:{},style:{},children:[],setAttribute(k,v){this.attrs[k]=v;},replaceChildren(){this.children=[];},append(...nodes){this.children.push(...nodes);}};
sandbox.svg=(tag,attrs,text)=>({tag,attrs,text});
engine.sparkline(chart,[{last_price_vnd:100},{last_price_vnd:null},{last_price_vnd:102},{last_price_vnd:101}],-1,'FPT');
assert.equal(chart.style.color,engine.colors.down);
assert.equal(chart.attrs['aria-label'],'FPT');
assert.equal((chart.children.find(n=>n.tag==='path').attrs.d.match(/M/g)||[]).length,2);
assert.equal((chart.children.find(n=>n.tag==='path').attrs.d.match(/L/g)||[]).length,1);
// Intraday points use exchange timestamps rather than equal poll spacing.
engine.sparkline(chart,[{timestamp:'2026-11-13T09:15:00+07:00',last_price_vnd:50000},{timestamp:'2026-11-13T09:20:00+07:00',last_price_vnd:50050},{timestamp:'2026-11-13T10:15:00+07:00',last_price_vnd:50000}],1,'FPT');
assert.match(chart.children.find(n=>n.tag==='path').attrs.d,/L10\.83,/);
// One price tick should not stretch into the entire miniature height.
const yValues=[...chart.children.find(n=>n.tag==='path').attrs.d.matchAll(/(?:M|L)[\d.]+,([\d.]+)/g)].map(m=>Number(m[1]));
assert.ok(Math.max(...yValues)-Math.min(...yValues)<5);
engine.sparkline(chart,[{timestamp:'2026-11-13T09:15:00+07:00',last_price_vnd:50000}],0,'Một điểm thật');
assert.equal(chart.children.find(n=>n.tag==='circle').attrs.cx,50);
assert.equal((chart.children.find(n=>n.tag==='path').attrs.d.match(/L/g)||[]).length,0);
// A genuine one-sided book can have depth while spread is unknown. Its available
// side must remain viewable; invalid observations still break the plotted path.
const elements={'history-chart':{...chart,children:[],dataset:{},clientWidth:600,clientHeight:320},'history-legend':{replaceChildren(){}},'history-axes':{replaceChildren(){}}};
let empty=false,attached=null;
sandbox.$=id=>elements[id];sandbox.drawEmpty=()=>{empty=true;};sandbox.set=()=>{};
sandbox.node=(tag,classes,text)=>({tag,classes,text,style:{}});
sandbox.fmt=v=>v===null||v===undefined?'_':String(v);sandbox.money=sandbox.fmt;
sandbox.clock=()=>"09:15";sandbox.dateTime=v=>v;
sandbox.window.lopmChartViewport={idle(){},attach(c,rows,x,describe){attached={rows,describe};}};
const bookRows=[0,1,2,3].map((i)=>({received_at:`2026-11-13T09:15:${String(i*10).padStart(2,'0')}+07:00`,valid:i!==1,spread_bps:null,depth_min_vnd:0,depth_bid_vnd:(i+1)*1e9,depth_ask_vnd:0}));
engine.liquidity(bookRows,{bid:true});
assert.equal(empty,false);
const pathNode=elements['history-chart'].children.find(n=>n.attrs?.['data-series']==='bid-depth'&&n.tag==='path');
assert.ok(pathNode);assert.equal(pathNode.attrs.d.includes('NaN'),false);
assert.ok(attached.describe(bookRows[1]).text.includes('Chưa có sổ hợp lệ'));
engine.liquidity(bookRows,{});assert.equal(empty,true);
// Actual SSI averages are aligned to candle end, never reconstructed from OHLC.
const intraday=['09:15','09:20','09:25','09:30'].map(time=>({timestamp:`2026-11-16T${time}:00+07:00`,trading_date:'2026-11-16',last_price_vnd:50100,close:50100,open:50000,high:50200,low:49900,volume_shares:100}));
const averages=[['09:19:50',50000],['09:24:55',50050],['09:30:00',99999]].map(([time,average])=>({timestamp:`2026-11-16T${time}+07:00`,trading_date:'2026-11-16',avg_match_price_vnd:average}));
const aligned=engine.sessionAverage(intraday,averages,'5m','2026-11-16T09:27:00+07:00');
assert.deepEqual(Array.from(aligned,p=>p.avg_match_price_vnd),[50000,50050,null,null]);
assert.equal(engine.sessionAverage(intraday,averages,'1d',null).every(p=>p.avg_match_price_vnd===null),true);
assert.equal(engine.sessionAverage(intraday,averages.map(p=>({...p,trading_date:'2026-11-13'})),'5m','2026-11-16T09:27:00+07:00').every(p=>p.avg_match_price_vnd===null),true);
engine.price(aligned,{bars:true,type:'line',timeframe:'5m',average:true,masterPoints:aligned});
const averagePath=elements['history-chart'].children.find(n=>n.attrs?.['data-series']==='average');
assert.ok(averagePath);assert.equal(averagePath.attrs.d.includes('NaN'),false);
assert.ok(attached.describe(aligned[0]).lines.some(line=>line[0]==='BQ phiên SSI'));
console.log('Chart averages, missing baselines and reference-change colors passed.');
