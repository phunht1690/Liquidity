"use strict";
(() => {
  const finite=v=>typeof v==='number'&&Number.isFinite(v);
  const kinds=a=>(a.reasons||[]).map(r=>r.kind);
  const fill=a=>Math.min(...['buy_fill','sell_fill'].map(k=>finite(a[k])?a[k]:1));
  const spread=a=>finite(a.spread_bps)?a.spread_bps:0;
  function select(alerts,{kind='all',search='',sort='shortage'}={}){
    const term=search.trim().toUpperCase();
    return alerts.filter(a=>(kind==='all'||kinds(a).includes(kind))&&(!term||a.symbol.includes(term))).sort((a,b)=>{
      if(sort==='symbol')return a.symbol.localeCompare(b.symbol);
      if(sort==='spread')return spread(b)-spread(a)||fill(a)-fill(b)||a.symbol.localeCompare(b.symbol);
      return Number(!kinds(a).includes('capacity'))-Number(!kinds(b).includes('capacity'))||fill(a)-fill(b)||spread(b)-spread(a)||a.symbol.localeCompare(b.symbol);
    });
  }
  function summary(payload){
    const alerts=payload.alerts||[],coverage=payload.coverage||{};
    return {total:alerts.length,capacity:alerts.filter(a=>kinds(a).includes('capacity')).length,
      spread:alerts.filter(a=>kinds(a).includes('spread')).length,
      eligible:coverage.valid_book_count??payload.ranking.filter(r=>r.valid).length,
      visible:coverage.visible_count??payload.ranking.length};
  }
  function csv(payload,items){
    const headers=['source','universe','group','notional_vnd','analysis_mode','analysis_at','analysis_dataset_id','spread_threshold_bps',
      'symbol','conditions','buy_fill_percent','sell_fill_percent','spread_vnd','spread_percent','spread_ticks','first_observed_at','last_observed_at','observed_duration_seconds'];
    const scale=(value,n)=>finite(value)?Math.round(value*n*1e6)/1e6:null;
    const cell=value=>{
      if(value===null||value===undefined)return '""';
      let text=String(value);
      if(typeof value==='string'&&/^[=+\-@\t\r]/.test(text))text="'"+text;
      return '"'+text.replaceAll('"','""')+'"';
    };
    return '\ufeff'+[headers,...items.map(a=>[payload.source,payload.universe,payload.group,payload.notional_vnd,a.analysis_mode,
      a.analysis_at,payload.analysis_dataset_id,payload.alert_rules?.spread_threshold_bps??25,a.symbol,
      (a.reasons||[]).map(r=>r.label).join('; '),scale(a.buy_fill,100),scale(a.sell_fill,100),a.spread_vnd,scale(a.spread_bps,.01),a.spread_ticks,a.observation?.first_at,a.observation?.last_at,a.observation?.duration_seconds])]
      .map(row=>row.map(cell).join(',')).join('\r\n')+'\r\n';
  }
  window.lopmAlertModel={select,summary,csv};
})();
