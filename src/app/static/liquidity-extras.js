"use strict";
(() => {
  const finite=v=>typeof v==='number'&&Number.isFinite(v),nonnegative=v=>finite(v)&&v>=0;
  function render(payload){
    const r=payload?.selected,context=payload?.volume_context;
    if(!r){clear();return;}
    set('price-limit-line',`Phiên ${(r.reference_date||'').split('-').reverse().join('/')||'_'} · TC ${fmt(r.reference_price_vnd,0)} · Trần ${fmt(r.ceiling_price_vnd,0)} · Sàn ${fmt(r.floor_price_vnd,0)} đ`);
    set('volume-ratio',finite(context?.ratio)?`${fmt(context.ratio,2)}× bình quân`:'_');
    const basis=context?.basis==='daily'?'Cả phiên':context?.until?`Đến ${context.until} · cùng ${context.slots} nến 5 phút`:'Chưa có nến hoàn tất';
    set('volume-context-basis',context?`${basis} · ${(context.day||'').split('-').reverse().join('/')||'_'} · ${context.sessions}/20 phiên trước đủ dữ liệu`:'Đang đọc lịch sử đã lưu.');
    set('volume-context-values',context?`KL so sánh ${fmt(context.volume_shares,0)} CP · bình quân ${fmt(context.average_volume_shares,0)} CP. Chỉ so cùng các mốc đã có dữ liệu.`:'');
    const d=r.daily_statistics||r.daily_reference||{},buy=d.foreign_buy_shares,sell=d.foreign_sell_shares;
    set('foreign-buy',nonnegative(buy)?fmt(buy,0):'_');set('foreign-sell',nonnegative(sell)?fmt(sell,0):'_');
    set('foreign-net',nonnegative(buy)&&nonnegative(sell)?signed(buy-sell,0):'_');
    set('foreign-room',nonnegative(d.foreign_room_remaining_shares)?fmt(d.foreign_room_remaining_shares,0):'_');
    set('foreign-caption',`SSI tổng hợp · phiên ${(d.day||'').split('-').reverse().join('/')||'_'} · đơn vị cổ phiếu`);
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
    for(const id of ['volume-ratio','foreign-buy','foreign-sell','foreign-net','foreign-room','market-activity-summary'])set(id,'_');
    for(const id of ['price-limit-line','volume-context-basis','volume-context-values','foreign-caption'])set(id,'');
    emptyTable('market-activity-body',5,'_');
  }
  window.lopmLiquidityExtras={render,clear};
})();
