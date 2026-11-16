const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../src/app/static/index.html'),'utf8');
const elements=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([,id])=>[id,{textContent:'',children:[],replaceChildren(...children){this.children=children;}}]));
const get=id=>{assert.ok(elements.has(id),id);return elements.get(id);};
const node=(tag,cls,text)=>({tag,text,children:[],append(...children){this.children.push(...children);}});
const context={window:{},$:get,node,set:(id,value)=>get(id).textContent=String(value),fmt:v=>typeof v==='number'?String(v):'_',money:v=>typeof v==='number'?String(v):'_',signed:v=>String(v),dateTime:v=>v||'_',emptyTable:(id,n,text)=>get(id).children=[{text}]};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/liquidity-extras.js'),'utf8'),context);
const view=context.window.lopmLiquidityExtras;
const sample={universe:'HNX',selected:{reference_date:'2026-11-16',reference_price_vnd:13000,ceiling_price_vnd:14300,floor_price_vnd:11700,
  daily_statistics:{day:'2026-11-13',foreign_buy_shares:100,foreign_sell_shares:0,foreign_room_remaining_shares:5000,foreign_buy_value_raw:1320,foreign_value_unit:'provider_unverified'}},
  volume_context:{basis:'aligned_5m_candles',day:'2026-11-16',until:'09:25',slots:2,sessions:20,ratio:2,volume_shares:6000,average_volume_shares:3000},
  market_activity:{items:[{scope:'HNX',day:'2026-11-13',matched_value_vnd:5e9,negotiated_value_vnd:0,received_at:'2026-11-16T13:00:00+07:00'}]}};
const copy=JSON.stringify(sample);view.render(sample);
assert.equal(get('foreign-buy').textContent,'100');assert.equal(get('foreign-sell').textContent,'0');
assert.equal(get('foreign-net').textContent,'100');assert.equal(get('foreign-room').textContent,'5000');
assert.match(get('volume-context-basis').textContent,/09:25/);assert.match(get('volume-ratio').textContent,/2×/);
assert.match(get('market-activity-summary').textContent,/Toàn HNX/);assert.match(get('market-activity-summary').textContent,/13\/11\/2026/);
assert.equal(get('market-activity-body').children[0].children[2].text,'0 đồng');
assert.ok(![...elements.values()].some(e=>e.textContent.includes('1320')),'Unverified foreign currency must not leak into display.');
assert.equal(JSON.stringify(sample),copy);
view.render({...sample,selected:{daily_reference:sample.selected.daily_statistics}});
assert.equal(get('foreign-buy').textContent,'100');assert.match(get('foreign-caption').textContent,/13\/11\/2026/);
view.render({...sample,selected:{},market_activity:{items:[]},volume_context:{sessions:19,ratio:null}});
assert.equal(get('foreign-buy').textContent,'_');assert.equal(get('volume-ratio').textContent,'_');
view.clear();assert.equal(get('volume-context-basis').textContent,'');
console.log('Liquidity additions: dates, same-time volume, foreign share units, known zero and loading reset passed.');
