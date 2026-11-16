"use strict";
(() => {
  const byId=id=>document.getElementById(id);
  let backendOK=false,lastSuccess=0;
  const watchKey='lopm-watchlist-v1';
  let watch=new Set();
  try{watch=new Set(JSON.parse(localStorage.getItem(watchKey)||'[]').filter(s=>typeof s==='string'&&/^[A-Z0-9]{2,6}$/.test(s)).slice(0,100));}catch{}
  function watchToggle(symbol){
    if(watch.has(symbol))watch.delete(symbol);else if(watch.size<100)watch.add(symbol);
    try{localStorage.setItem(watchKey,JSON.stringify([...watch]));}catch{}
    renderRanking();
  }
  function baseFiltered(payload){
    const term=byId('stock-search').value.trim().toLocaleUpperCase('vi-VN'),only=byId('ranking-watchlist-only').checked;
    return (payload?.ranking||[]).filter(r=>(!only||watch.has(r.symbol))&&(!term||`${r.symbol} ${r.name||''} ${r.market_code||''}`.toLocaleUpperCase('vi-VN').includes(term)));
  }
  function filtered(payload){const rows=baseFiltered(payload);return window.lopmLiquidityBrief?.filterRows(payload,rows)||rows;}
  function priceCaption(row){
    if(row?.price_basis==='ssi_daily_close')return `Đóng cửa ${(row.price_asof_date||'').split('-').reverse().join('/')} · SSI tổng hợp ngày`;
    if(row?.price_basis==='ssi_ohlc_daily')return `Đóng cửa ${(row.price_asof_date||'').split('-').reverse().join('/')} · nến ngày SSI`;
    if(row?.price_basis==='ssi_ohlc_bar')return `Đóng nến ${dateTime(row.price_asof_bar)} · SSI`;
    return row?.trade_time?`Khớp lúc ${sourceTime(row.trade_time)} · SSI`:'';
  }
  function paintFreshness(){
    if(typeof state==='undefined'||!state)return;
    const status=window.lopmDashboardModel.connection(state,backendOK);
    document.body.dataset.connection=status.mode==='reconnecting'?'cached':'connected';
    set('connection-label',status.mode==='saved'?'Ảnh đã lưu':status.label);set('auto-update-state',status.automatic);
    const r=state.selected||{},caption=priceCaption(r);
    set('last-updated',caption?`Giá ${r.symbol||''} · ${caption.replace(/^Khớp lúc /,'').replace(/ · SSI(?: tổng hợp ngày)?$/,'')}`:'Giá _');
    byId('last-updated').title=caption||'Chưa có thời điểm giá.';
    set('book-updated',state.analysis?.asof?`Sổ ${dateTime(state.analysis.asof)}`:'Sổ _');
    byId('book-updated').title='Thời điểm ảnh sổ dùng để tính chênh giá, lượng chờ và mức đáp ứng.';
    const banner=byId('reference-banner');banner.hidden=status.mode!=='reconnecting';
    if(!banner.hidden)set('reference-banner',lastSuccess?`Đang nối lại cập nhật. Giữ bản đã nhận; đồng bộ gần nhất ${dateTime(new Date(lastSuccess).toISOString())}.`:'Đang nối lại nguồn dữ liệu. Ứng dụng sẽ tự thử lại.');
    byId('auto-update-state').title=lastSuccess?`Đồng bộ với ứng dụng lúc ${dateTime(new Date(lastSuccess).toISOString())}. Tự nhận dữ liệu mới khi có.`:'Ứng dụng sẽ tự nhận dữ liệu mới và tự thử lại khi mất kết nối.';
    if(status.mode!=='reconnecting')return;
    set('alerts-mode','Điều kiện trên bản đã lưu');
    byId('export-button').disabled=true;byId('data-export').disabled=true;
  }
  function scopeHint(payload){
    const scope=payload.coverage.scope||{},pilot=payload.available_universes.find(u=>u.id===payload.universe)?.pilot;
    const label=payload.available_universes.find(u=>u.id===payload.universe)?.label||payload.universe;
    set('scope-data-note',`${label} · ${payload.group==='all'?'Tất cả ngành':payload.group} · có giá ${scope.received_prices??0}/${scope.symbols??0} mã.${pilot?' Danh mục thử nghiệm đã lưu.':''}`);
  }
  function renderExtra(payload){
    const r=payload.selected,d=r.daily_statistics||{};
    const day=r.statistics_day||r.turnover_day||d.day||r.trading_date;
    set('daily-stats-caption',day?`Thống kê phiên ${day.split('-').reverse().join('/')}`:'Thống kê phiên gần nhất');
    set('daily-turnover',r.turnover_basis==='ssi_daily_summary'&&valid(r.turnover_vnd)?money(r.turnover_vnd)+' đồng':'_');
    set('daily-open',valid(r.open_price_vnd)?fmt(r.open_price_vnd,0)+' đ':'_');
    set('daily-range',valid(r.low_price_vnd)&&valid(r.high_price_vnd)?`${fmt(r.low_price_vnd,0)} – ${fmt(r.high_price_vnd,0)} đ`:'_');
    set('daily-stat-source',d.day?`SSI tổng hợp ngày · nhận ${dateTime(d.received_at)}. Giá trị khớp là số liệu nguồn cung cấp.`:r.statistics_source==='ssi_ohlc_daily'?`Giá và khối lượng: nến ngày SSI · nhận ${dateTime(r.statistics_received_at)}. Giá trị khớp chỉ hiện khi có số liệu tổng hợp ngày.`:'Dữ liệu SSI; ô chưa có số liệu được giữ “_”.');
    scopeHint(payload);
    const trades=payload.recent_trades||[];
    set('trade-history-count',fmt(trades.length,0));
    set('trade-history-caption',trades.length?`${r.symbol} · ${trades.length} giao dịch gần nhất đã ghi nhận`:`${r.symbol} · chưa có giao dịch trong kho ghi nhận`);
    const body=byId('trade-history-body');body.replaceChildren(...trades.map(t=>{
      const tr=node('tr');tr.append(node('td','',dateTime(t.timestamp)),node('td','',fmt(t.price_vnd,0)),node('td','',fmt(t.quantity_shares,0)),node('td',t.side==='B'?'green-text':t.side==='S'?'red-text':'',t.side==='B'?'Mua chủ động':t.side==='S'?'Bán chủ động':'_'));return tr;
    }));
    if(!trades.length)emptyTable('trade-history-body',4,'Chưa ghi nhận giao dịch của mã này.');
    const events=payload.alert_history||[];
    byId('alert-history-body').replaceChildren(...events.map(e=>{
      const tr=node('tr');tr.append(node('td','',e.symbol),node('td','',e.kind==='capacity'?'Thiếu lượng chờ':'Vượt ngưỡng chênh giá'),node('td','',`${clock(e.first_at)} → ${clock(e.last_at)}`),node('td','',e.resolved_at?'Đã kết thúc ghi nhận':'Có tại lần ghi nhận cuối'));return tr;
    }));
    if(!events.length)emptyTable('alert-history-body',4,'Lịch sử được ghi khi bộ thu theo dõi trong phiên; chưa có ghi nhận cho bộ lọc này.');
    window.lopmLiquidityExtras?.render(payload);byId('main-content').setAttribute('aria-busy','false');paintFreshness();
  }
  function clear(){
    window.lopmLiquidityExtras?.clear();
    for(const id of ['daily-turnover','daily-open','daily-range'])set(id,'_');
    for(const id of ['daily-stat-source','scope-data-note','cost-sizing-note'])set(id,'');
    set('daily-stats-caption','Thống kê phiên gần nhất');set('trade-history-caption','Đang đọc giao dịch của mã đã chọn.');set('trade-history-count','_');
    byId('trade-history-body').replaceChildren();byId('alert-history-body').replaceChildren();
  }
  window.lopmProductUX={baseFiltered,filtered,isWatched:s=>watch.has(s),watchToggle,priceCaption,render:renderExtra,clear};
  window.lopmFreshness={received(){backendOK=true;lastSuccess=Date.now();},lost(){backendOK=false;paintFreshness();},paint:paintFreshness};
  setInterval(paintFreshness,10000);
})();
