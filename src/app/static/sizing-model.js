"use strict";
(() => {
  const finite=value=>typeof value==='number'&&Number.isFinite(value);
  const inRange=value=>finite(value)&&value>=100_000_000&&value<=5_000_000_000;
  // Reuse the server-validated book. Resizing never turns an invalid book valid.
  function resizeRow(row,notional){
    if(!row?.valid||!finite(row.sizing_price_vnd)||row.sizing_price_vnd<=0)return row;
    const lot=finite(row.lot_size)&&row.lot_size>0?Math.trunc(row.lot_size):100;
    const requested=Math.floor(notional/row.sizing_price_vnd/lot)*lot;
    const result={...row};
    for(const [side,book] of [['buy','asks'],['sell','bids']]){
      let remaining=requested,value=0;
      for(const level of (row[book]||[]).slice(0,row.book_level_limit||10)){
        if(!finite(level.price)||level.price<=0||!finite(level.volume)||level.volume<=0)continue;
        const take=Math.min(remaining,level.volume);
        value+=take*level.price;remaining-=take;
        if(remaining<=0)break;
      }
      const filled=requested-remaining,vwap=filled?value/filled:null;
      const mid=finite(row.mid)&&row.mid>0?row.mid:null;
      result[side]={requested_shares:requested,filled_shares:filled,unfilled_shares:remaining,
        fill_ratio:requested?filled/requested:null,vwap,
        slip_bps:vwap&&mid?(side==='buy'?vwap-mid:mid-vwap)/mid*10000:null,
        filled_value_vnd:value,reference_notional_vnd:notional,lot_size_assumed:lot,
        sizing_price_vnd:row.sizing_price_vnd,sizing_basis:row.sizing_basis,
        flag:!requested?'below_one_lot':remaining?'partial_visible_levels':'complete'};
    }
    result.fill_ratio=finite(result.buy.fill_ratio)&&finite(result.sell.fill_ratio)?Math.min(result.buy.fill_ratio,result.sell.fill_ratio):null;
    return result;
  }
  function resize(payload,notional){
    if(!payload||!inRange(notional))return null;
    const ranking=payload.ranking.map(row=>resizeRow(row,notional));
    const selected=resizeRow(payload.selected,notional),alerts=[];
    const threshold=payload.alert_rules?.spread_threshold_bps??25;
    for(const row of ranking){
      if(!row.valid)continue;
      const buy=row.buy||{},sell=row.sell||{},reasons=[];
      if([buy,sell].some(side=>finite(side.fill_ratio)&&side.fill_ratio<1))reasons.push({kind:'capacity',label:'Chưa đủ khối lượng chờ',buy_fill:buy.fill_ratio,sell_fill:sell.fill_ratio});
      if(finite(row.spread_bps)&&row.spread_bps>threshold)reasons.push({kind:'spread',label:'Vượt ngưỡng chênh giá',value_bps:row.spread_bps,value_vnd:row.spread_vnd,value_ticks:row.spread_ticks,threshold_bps:threshold});
      if(reasons.length)alerts.push({symbol:row.symbol,group:row.group,reasons,
        priority:reasons[0].kind==='capacity'?'capacity':'spread',buy_fill:buy.fill_ratio,sell_fill:sell.fill_ratio,
        spread_bps:row.spread_bps,spread_vnd:row.spread_vnd,spread_ticks:row.spread_ticks,
        analysis_at:row.analysis_at,analysis_mode:row.analysis_mode});
    }
    const shortage=a=>Math.min(...[a.buy_fill,a.sell_fill].map(value=>finite(value)?value:1));
    alerts.sort((a,b)=>Number(a.priority!=='capacity')-Number(b.priority!=='capacity')||shortage(a)-shortage(b)||(b.spread_bps||0)-(a.spread_bps||0)||a.symbol.localeCompare(b.symbol));
    // Observation history belongs to a particular amount; wait for the server's
    // matching history instead of reusing runs recorded for the previous amount.
    return {...payload,notional_vnd:notional,selected,ranking,alerts,alert_history:[],
      kpis:{...payload.kpis,attention_count:alerts.length},sizing_preview:true};
  }
  window.lopmSizingModel={inRange,resizeRow,resize};
})();
