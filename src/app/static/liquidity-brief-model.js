"use strict";
(() => {
  const finite=v=>typeof v==='number'&&Number.isFinite(v);
  const nonnegative=v=>finite(v)&&v>=0;
  const ratio=v=>finite(v)&&v>=0&&v<=1;
  const median=values=>{
    if(!values.length)return null;
    const a=[...values].sort((x,y)=>x-y),i=Math.floor(a.length/2);
    return a.length%2?a[i]:(a[i-1]+a[i])/2;
  };
  const fmt=(v,d=0)=>finite(v)?v.toLocaleString('vi-VN',{minimumFractionDigits:d,maximumFractionDigits:d}):'_';
  const pct=(v,d=1)=>ratio(v)?fmt(v*100,d)+'%':'_';
  const money=v=>!nonnegative(v)?'_':v>=1e9?fmt(v/1e9,2)+' tỷ đồng':fmt(v/1e6,1)+' triệu đồng';
  const date=v=>{
    if(typeof v!=='string'||!Number.isFinite(Date.parse(v)))return '_';
    return new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(v));
  };
  const day=v=>{const m=/^(\d{4})[-/](\d{2})[-/](\d{2})/.exec(v||'');return m?`${m[3]}/${m[2]}/${m[1]}`:'_';};
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const filters=[['all','Tất cả'],['complete','Đủ quy mô hai phía'],['capacity','Thiếu lượng chờ'],['spread','Chênh giá vượt ngưỡng'],['valid','Có sổ dùng được']];

  function threshold(payload){return nonnegative(payload?.alert_rules?.spread_threshold_bps)?payload.alert_rules.spread_threshold_bps:25;}
  function bookUsable(row,payload){
    const anchor=Date.parse(payload?.analysis?.asof||''),stamp=Date.parse(row?.analysis_at||'');
    return row?.valid===true&&Number.isFinite(anchor)&&Number.isFinite(stamp)&&stamp===anchor;
  }
  function flags(row,payload){
    const valid=bookUsable(row,payload),buy=row?.buy?.fill_ratio,sell=row?.sell?.fill_ratio;
    const comparable=valid&&ratio(buy)&&ratio(sell);
    return {valid,spread:valid&&nonnegative(row.spread_bps)&&row.spread_bps>threshold(payload),
      capacity:valid&&[buy,sell].some(v=>ratio(v)&&v<1),
      capacityKnown:valid&&[buy,sell].some(ratio),comparable,
      complete:comparable&&buy===1&&sell===1};
  }
  function filterRows(payload,id='all',rows=payload?.ranking||[]){
    return rows.filter(r=>id==='all'||!!flags(r,payload)[id]);
  }
  function turnoverRecord(row){
    if(row.turnover_basis==='ssi_daily_summary'&&nonnegative(row.turnover_vnd))return {day:row.turnover_day,value:row.turnover_vnd};
    const d=row.daily_reference;
    return d?.source==='ssi_securities_summary'&&nonnegative(d.turnover_vnd)?{day:d.day,value:d.turnover_vnd}:null;
  }
  function turnoverDay(payload){
    const current=(payload?.runtime?.now||payload?.updated_at||'9999-12-31').slice(0,10);
    return (payload?.ranking||[]).map(turnoverRecord).filter(r=>r&&/^\d{4}-\d{2}-\d{2}$/.test(r.day||'')&&r.day<=current)
      .map(r=>r.day).sort().at(-1)||null;
  }
  function summarize(payload,rows=payload?.ranking||[]){
    const spreads=[],depths=[];
    let books=0,wide=0,partial=0,capacityKnown=0,comparable=0,complete=0,priced=0;
    for(const row of rows){
      if(finite(row.last_price_vnd)&&row.last_price_vnd>0)priced++;
      const f=flags(row,payload);
      if(!f.valid)continue;
      books++;if(f.spread)wide++;if(f.capacity)partial++;if(f.capacityKnown)capacityKnown++;
      if(f.comparable)comparable++;if(f.complete)complete++;
      if(nonnegative(row.spread_bps))spreads.push(row.spread_bps);
      if(nonnegative(row.depth_min_vnd))depths.push(row.depth_min_vnd);
    }
    const targetDay=turnoverDay(payload),turnovers=rows.map(turnoverRecord).filter(r=>r&&targetDay&&r.day===targetDay);
    return {total:rows.length,priced,books,wide,partial,capacityKnown,comparable,complete,
      turnoverDay:targetDay,turnoverCount:turnovers.length,turnoverVnd:turnovers.length?turnovers.reduce((sum,r)=>sum+r.value,0):null,
      spreadCount:spreads.length,depthCount:depths.length,medianSpreadBps:median(spreads),medianDepthVnd:median(depths),
      completeRatio:comparable?complete/comparable:null,thresholdBps:threshold(payload)};
  }
  function sectors(payload,sort='depth'){
    const groups=new Map();
    for(const row of payload?.ranking||[]){const name=row.group||'Khác';if(!groups.has(name))groups.set(name,[]);groups.get(name).push(row);}
    const result=[...groups].map(([name,rows])=>({name,...summarize(payload,rows)}));
    const metric=sort==='spread'?'medianSpreadBps':sort==='turnover'?'turnoverVnd':'medianDepthVnd';
    result.sort((a,b)=>sort==='name'?a.name.localeCompare(b.name,'vi'):Number(!finite(a[metric]))-Number(!finite(b[metric]))||
      (finite(a[metric])&&finite(b[metric])?(sort==='spread'?a[metric]-b[metric]:b[metric]-a[metric]):0)||a.name.localeCompare(b.name,'vi'));
    return result;
  }
  function attention(payload){
    return (payload?.ranking||[]).filter(r=>{const f=flags(r,payload);return f.capacity||f.spread;}).sort((a,b)=>{
      const af=flags(a,payload),bf=flags(b,payload);
      const shortage=r=>Math.min(...[r.buy?.fill_ratio,r.sell?.fill_ratio].filter(ratio),1);
      return Number(!af.capacity)-Number(!bf.capacity)||shortage(a)-shortage(b)||(b.spread_bps||0)-(a.spread_bps||0)||a.symbol.localeCompare(b.symbol);
    });
  }
  function reasons(row,payload){
    const f=flags(row,payload),items=[];
    if(f.capacity)items.push(`Lượng chờ đáp ứng mua ${pct(row.buy?.fill_ratio)}, bán ${pct(row.sell?.fill_ratio)}`);
    if(f.spread)items.push(`Chênh giá ${fmt(row.spread_bps/100,3)}%, vượt mức theo dõi ${fmt(threshold(payload)/100,3)}%`);
    return items.join(' · ');
  }
  function scopeLabel(payload){return payload?.available_universes?.find(u=>u.id===payload.universe)?.label||payload?.universe||'_';}
  function priceDay(row){return day(row.price_asof_date||row.statistics_day||row.trading_date||row.trade_time);}

  function reportHTML(payload,generatedAt=new Date().toISOString()){
    if(!payload||payload.sizing_preview)throw new Error('Chờ đồng bộ số tiền trước khi xuất.');
    const stats=summarize(payload),groups=sectors(payload),watch=attention(payload),scope=scopeLabel(payload);
    const esc=escape;
    const metric=(title,value,note)=>`<article><span>${esc(title)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></article>`;
    const bodyRows=groups.map(g=>`<tr><th scope="row">${esc(g.name)}</th><td>${g.books}/${g.total}</td><td>${esc(finite(g.medianSpreadBps)?fmt(g.medianSpreadBps/100,3)+'%':'_')}<small>${g.spreadCount} mã có chênh giá</small></td><td>${esc(money(g.medianDepthVnd))}<small>${g.depthCount} mã có độ dày</small></td><td>${esc(pct(g.completeRatio))}<small>${g.complete}/${g.comparable} mã có thể tính hai phía</small></td><td>${esc(money(g.turnoverVnd))}<small>${g.turnoverCount}/${g.total} mã · ${esc(day(g.turnoverDay))}</small></td></tr>`).join('');
    const marketRows=(payload.market_activity?.items||[]).map(item=>`<tr><th scope="row">${esc(item.scope)}</th><td>${esc(day(item.day))}</td><td>${esc(money(item.matched_value_vnd))}</td><td>${esc(money(item.negotiated_value_vnd))}</td></tr>`).join('');
    const notes=watch.map(r=>`<tr><th scope="row">${esc(r.symbol)}</th><td>${esc(r.group)}</td><td>${esc(reasons(r,payload))}</td></tr>`).join('');
    const rows=(payload.ranking||[]).map(r=>{
      const f=flags(r,payload),usable=f.valid;
      return `<tr><th scope="row">${esc(r.symbol)}<small>${esc(r.name)}</small></th><td>${esc(r.group)}</td><td>${esc(fmt(r.last_price_vnd))}<small>${esc(priceDay(r))}</small></td><td>${esc(usable&&nonnegative(r.spread_bps)?fmt(r.spread_bps/100,3)+'%':'_')}</td><td>${esc(usable?money(r.depth_min_vnd):'_')}<small>Mua ${esc(r.known_bid_levels??'_')} mức · bán ${esc(r.known_ask_levels??'_')} mức</small></td><td>${esc(usable?pct(r.buy?.fill_ratio):'_')}</td><td>${esc(usable?pct(r.sell?.fill_ratio):'_')}</td><td>${usable?'Có sổ đối chiếu':'_'}<small>${esc(usable?date(r.analysis_at):'')}</small></td></tr>`;
    }).join('');
    return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>LOPM · Tóm tắt thanh khoản ${esc(scope)}</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#172635;font:14px/1.65 Arial,sans-serif}main{max-width:1200px;margin:36px auto;padding:30px;background:white;border:1px solid #dce3eb;border-radius:12px}h1{font-size:30px;line-height:1.2;margin:10px 0}h2{font-size:20px;margin:0 0 8px}p{margin:8px 0;color:#526577}.eyebrow{letter-spacing:.16em;font-size:11px;color:#277a86}.context{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:18px;background:#f1f6f8;border-radius:7px;margin:20px 0}.context b{color:#172635}.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.kpis article{border:1px solid #dce3eb;border-radius:7px;padding:16px}.kpis span,.kpis small{display:block;color:#526577}.kpis strong{display:block;font-size:26px;margin:7px 0;color:#156b79}.kpis small{font-size:11px}section{margin-top:28px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;padding:11px 10px;border-bottom:1px solid #e4e9ee;vertical-align:top}thead th{background:#eef3f7;color:#526577}td small,th small{display:block;color:#687b8b;font-weight:400;font-size:10px}details{border:1px solid #dce3eb;border-radius:7px;padding:14px;margin-top:22px}summary{cursor:pointer;font-weight:bold}footer{border-top:1px solid #dce3eb;margin-top:28px;padding-top:15px;color:#526577;font-size:11px}.empty{text-align:center;padding:20px;color:#687b8b}@media(max-width:700px){main{margin:0;padding:18px;border-radius:0}.kpis{grid-template-columns:1fr 1fr}.context{grid-template-columns:1fr}h1{font-size:25px}table{min-width:650px}}@media print{body{background:white}main{margin:0;border:0;padding:0;max-width:none}.table-wrap{overflow:visible}thead{display:table-header-group}tr{break-inside:avoid}details{break-before:page}summary{color:#526577}}
</style></head><body><main><header><div class="eyebrow">LOPM / SSI FASTCONNECT</div><h1>Bản tóm tắt thanh khoản</h1><p>${esc(scope)} · ${esc(payload.group==='all'?'Tất cả ngành':payload.group)}</p></header>
<div class="context"><div>Quy mô kiểm tra: <b>${esc(money(payload.notional_vnd))}</b></div><div>Ảnh sổ đối chiếu: <b>${esc(date(payload.analysis?.asof))}</b></div><div>Độ phủ giá: <b>${stats.priced}/${stats.total} mã</b></div><div>Tạo bản tóm tắt: <b>${esc(date(generatedAt))}</b></div></div>
<div class="kpis">${metric('Sổ dùng được',`${stats.books}/${stats.total}`,'mã trong phạm vi đang chọn')}${metric('Chênh giá vượt ngưỡng',stats.spreadCount?`${stats.wide}/${stats.spreadCount}`:'_',`mã có chênh giá · ngưỡng ${fmt(stats.thresholdBps/100,3)}%`)}${metric('Chưa đủ lượng chờ',stats.capacityKnown?`${stats.partial}/${stats.capacityKnown}`:'_','mã có dữ liệu tính mức đáp ứng')}${metric('Chênh giá trung vị',finite(stats.medianSpreadBps)?fmt(stats.medianSpreadBps/100,3)+'%':'_',`tính từ ${stats.spreadCount} mã`)}</div>
<p>Thống kê trên cùng ảnh sổ đối chiếu. Mỗi chỉ tiêu chỉ dùng các mã đủ dữ liệu cho chính chỉ tiêu đó; dấu “_” là phần chưa xác định.</p>
<section><h2>Thanh khoản theo ngành</h2><p>Độ dày là giá trị chờ phía ít hơn trên các mức SSI đã cấp (tối đa 10 mỗi phía). Tỷ lệ đáp ứng áp dụng cho quy mô ghi phía trên.</p><div class="table-wrap"><table><thead><tr><th>Ngành</th><th>Sổ dùng được</th><th>Chênh giá trung vị</th><th>Độ dày trung vị</th><th>Đủ quy mô hai phía</th><th>Giá trị đã khớp</th></tr></thead><tbody>${bodyRows||'<tr><td colspan="6" class="empty">Chưa có dữ liệu trong phạm vi này.</td></tr>'}</tbody></table></div></section>
${marketRows?`<section><h2>Khớp lệnh &amp; thỏa thuận thị trường</h2><p>Phiên riêng theo nguồn SSI. VN30/VN100 nằm trong HOSE; không cộng gộp các dòng.</p><div class="table-wrap"><table><thead><tr><th>Phạm vi</th><th>Phiên</th><th>Giá trị khớp</th><th>Giá trị thỏa thuận</th></tr></thead><tbody>${marketRows}</tbody></table></div></section>`:''}
<section><h2>Mã cần kiểm tra · ${watch.length} mã</h2><p>Điều kiện quan sát được trên ảnh sổ, kèm số liệu cụ thể.</p><div class="table-wrap"><table><thead><tr><th>Mã</th><th>Ngành</th><th>Điều cần kiểm tra</th></tr></thead><tbody>${notes||'<tr><td colspan="3" class="empty">Chưa ghi nhận điều kiện trên các mã đủ dữ liệu.</td></tr>'}</tbody></table></div></section>
<details><summary>Bảng số liệu của toàn bộ ${stats.total} mã trong phạm vi</summary><p>Giá có thể thuộc các phiên khác nhau; ngày của từng mã được ghi dưới giá. Các bộ lọc riêng tại bảng giá không thay đổi phạm vi bản tóm tắt.</p><div class="table-wrap"><table><thead><tr><th>Mã / doanh nghiệp</th><th>Ngành</th><th>Giá · đồng / ngày</th><th>Chênh giá</th><th>Độ dày</th><th>Đáp ứng mua</th><th>Đáp ứng bán</th><th>Sổ đối chiếu</th></tr></thead><tbody>${rows}</tbody></table></div></details>
<footer>Nguồn: SSI FastConnect; LOPM tính các chỉ tiêu từ dữ liệu nhận được. Đây là bản chụp tại thời điểm ghi trên báo cáo. Lượng chờ có thể thay đổi hoặc bị hủy; ước tính dùng các mức giá thực nhận, tối đa 10 mỗi phía và chưa gồm phí, thuế. Không phải khuyến nghị đầu tư.</footer></main></body></html>`;
  }
  window.lopmLiquidityBriefModel={finite,ratio,median,fmt,pct,money,date,day,filters,bookUsable,flags,filterRows,summarize,sectors,turnoverDay,attention,reasons,scopeLabel,reportHTML};
})();
