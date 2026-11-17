"use strict";
(() => {
  const finite=v=>typeof v==='number'&&Number.isFinite(v),nonnegative=v=>finite(v)&&v>=0;
  function render(payload){
    const r=payload?.selected,context=payload?.volume_context;
    if(!r){clear();return;}
    set('price-reference-day',`Phiên tham chiếu ${(r.reference_date||'').split('-').reverse().join('/')||'_'}`);
    let priceDay=r.price_asof_date;
    if(!priceDay&&!['ssi_daily_close','ssi_ohlc_daily','ssi_ohlc_bar'].includes(r.price_basis)){
      const match=/^(\d{4})[-/](\d{2})[-/](\d{2})/.exec(r.trade_time||'');
      if(match)priceDay=`${match[1]}-${match[2]}-${match[3]}`;
    }
    $('price-reference-day').hidden=!!r.reference_date&&r.reference_date===priceDay;
    $('price-limit-line').title=`Phiên tham chiếu ${(r.reference_date||'').split('-').reverse().join('/')||'_'}`;
    for(const [id,value] of [['reference',r.reference_price_vnd],['ceiling',r.ceiling_price_vnd],['floor',r.floor_price_vnd]])
      set(`price-${id}-value`,finite(value)&&value>0?`${fmt(value,0)} đ`:'_');
    const daily=context?.basis==='daily',day=(context?.day||'').split('-').reverse().join('/')||'_';
    set('volume-context-label',daily?'KL so với 20 phiên':'KL so với cùng thời điểm');
    set('volume-ratio',finite(context?.ratio)?`${fmt(context.ratio,2)}×`:'_');
    const basis=daily?'Cả phiên':context?.until?`Đến ${context.until}`:'Chưa có nến hoàn tất';
    set('volume-context-summary',context?`TB 20 phiên · ${basis.toLocaleLowerCase('vi-VN')} · ${day}`:'_');
    set('volume-context-basis',context?`${basis} · ${day} · ${finite(context.sessions)?context.sessions:'_'}/20 phiên đủ dữ liệu`:'Đang đọc lịch sử đã lưu.');
    set('volume-current-value',nonnegative(context?.volume_shares)?fmt(context.volume_shares,0):'_');
    set('volume-average-value',nonnegative(context?.average_volume_shares)?fmt(context.average_volume_shares,0):'_');
    set('volume-context-values',context?`${daily?'So sánh khối lượng cả phiên.':`So cùng ${finite(context.slots)?context.slots:'_'} nến 5 phút đã hoàn tất.`} Có ${finite(context.sessions)?context.sessions:'_'}/20 phiên trước đủ dữ liệu; chưa đủ 20 phiên thì tỷ lệ giữ _.`:'');
    const d=r.daily_statistics||r.daily_reference||{},buy=d.foreign_buy_shares,sell=d.foreign_sell_shares;
    set('foreign-buy',nonnegative(buy)?fmt(buy,0):'_');set('foreign-sell',nonnegative(sell)?fmt(sell,0):'_');
    set('foreign-net',nonnegative(buy)&&nonnegative(sell)?signed(buy-sell,0):'_');
    $('foreign-net').className=nonnegative(buy)&&nonnegative(sell)?buy>sell?'foreign-net-positive':buy<sell?'foreign-net-negative':'':'';
    set('foreign-room',nonnegative(d.foreign_room_remaining_shares)?fmt(d.foreign_room_remaining_shares,0):'_');
    set('stock-foreign-title',`Khối ngoại · phiên ${(d.day||'').split('-').reverse().join('/')||'_'}`);
    set('foreign-caption',`SSI tổng hợp${d.received_at?` · nhận ${dateTime(d.received_at)}`:''}`);
    const items=payload.market_activity?.items||[],chosen=items.find(item=>item.scope===payload.universe);
    set('market-activity-summary',chosen?`Toàn ${chosen.scope} · khớp ${money(chosen.matched_value_vnd)} đồng · phiên ${chosen.day.split('-').reverse().join('/')}`:`Toàn ${payload.universe} · _`);
    const rows=items.map(item=>{
      const tr=node('tr');tr.append(node('th','',item.scope),node('td','',nonnegative(item.matched_value_vnd)?money(item.matched_value_vnd)+' đồng':'_'),
        node('td','',nonnegative(item.negotiated_value_vnd)?money(item.negotiated_value_vnd)+' đồng':'_'),node('td','',item.day.split('-').reverse().join('/')),node('td','',dateTime(item.received_at)));return tr;
    });
    $('market-activity-body').replaceChildren(...rows);
    if(!rows.length)emptyTable('market-activity-body',5,'_');
  }
  function clear(){
    for(const id of ['volume-ratio','volume-context-summary','volume-current-value','volume-average-value','foreign-buy','foreign-sell','foreign-net','foreign-room','market-activity-summary'])set(id,'_');
    set('volume-context-label','KL so với cùng thời điểm');set('stock-foreign-title','Khối ngoại · phiên _');$('foreign-net').className='';
    $('price-reference-day').hidden=false;$('price-limit-line').title='';
    for(const id of ['price-reference-value','price-ceiling-value','price-floor-value'])set(id,'_');
    for(const id of ['price-reference-day','volume-context-basis','volume-context-values','foreign-caption'])set(id,'');
    emptyTable('market-activity-body',5,'_');
  }
  window.lopmLiquidityExtras={render,clear};
})();
