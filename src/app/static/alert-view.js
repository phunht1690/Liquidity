"use strict";
(() => {
  const model=window.lopmAlertModel,byId=id=>document.getElementById(id);
  function filters(){return {kind:byId('alert-kind').value,search:byId('alert-search').value,sort:byId('alert-sort').value};}
  function meter(value,label){
    const wrap=node('div','alert-fill'),text=node('strong','',percent(value));wrap.append(text);
    if(valid(value)){
      const bar=node('span','alert-fill-track'),ink=node('span','alert-fill-ink');
      ink.style.width=`${Math.max(0,Math.min(1,value))*100}%`;bar.classList.toggle('is-complete',value>=1);
      bar.setAttribute('role','progressbar');bar.setAttribute('aria-label',label);bar.setAttribute('aria-valuemin','0');bar.setAttribute('aria-valuemax','100');bar.setAttribute('aria-valuenow',String(Math.round(value*1000)/10));bar.append(ink);wrap.append(bar);
    }
    return wrap;
  }
  function explainCapacity(row){
    const group=node('div','alert-capacity-grid');
    for(const [side,label,opposite] of [['buy','Đáp ứng mua','chờ bán'],['sell','Đáp ứng bán','chờ mua']]){
      const values=row?.[side]||{},card=node('article','alert-capacity-side');
      card.append(node('h4','',label),meter(values.fill_ratio,label),
        node('p','',`${fmt(values.filled_shares,0)} / ${fmt(values.requested_shares,0)} CP có lượng ${opposite}.`));
      if(valid(values.unfilled_shares)&&values.unfilled_shares>0)card.append(node('small','alert-shortage',`Còn thiếu ${fmt(values.unfilled_shares,0)} CP trên các mức SSI đã cấp.`));
      group.append(card);
    }
    return group;
  }
  function detail(item,row){
    const articles=[];
    if(item.observation){
      const o=item.observation,section=node('article','alert-observation');
      const seconds=Math.max(0,Number(o.duration_seconds)||0);
      section.append(node('h3','','Khoảng đã quan sát'),node('p','',`Bắt đầu ghi nhận: ${dateTime(o.first_at)}`),node('p','',`Cập nhật trong phiên: ${dateTime(o.last_at)}`),node('p','',`Đã theo dõi ${seconds<60?fmt(seconds,0)+' giây':fmt(seconds/60,1)+' phút'}. Thời điểm bắt đầu là lúc ứng dụng nhìn thấy điều kiện.`));
      articles.push(section);
    }
    for(const reason of item.reasons){
      const article=node('article','product-alert-reason');
      if(reason.kind==='capacity'){
        article.append(node('h3','','Lượng chờ chưa đáp ứng quy mô'),explainCapacity(row));
      }else{
        article.append(node('h3','','Vượt ngưỡng chênh giá'));
        const values=node('dl','alert-spread-values');
        for(const [label,value] of [['Chênh mua–bán',`${fmt(reason.value_vnd??item.spread_vnd,0)} đ`],
          ['So với giá giữa',`${fmt(reason.value_bps/100,3)}%`],['Số bước giá',fmt(reason.value_ticks??item.spread_ticks,1)],
          ['Ngưỡng đang theo dõi',`${fmt(reason.threshold_bps/100,2)}%`]])values.append(node('dt','',label),node('dd','',value));
        article.append(values);
        if(valid(item.spread_ticks)&&item.spread_ticks<=1)article.append(node('p','alert-rule-note','Chênh một bước giá vẫn có thể vượt ngưỡng % đã chọn. Kết quả này không tự xác nhận bất thường thanh khoản.'));
      }
      articles.push(article);
    }
    return articles;
  }
  function render(payload,selectedSymbol,onSelect){
    const exportButton=byId('export-button');
    if(!payload){
      for(const id of ['alert-total-count','alert-capacity-count','alert-spread-count'])set(id,'_');
      set('alerts-context','Đang tải dữ liệu sổ lệnh để kiểm tra.');set('alert-filter-count','Đang tải dữ liệu…');set('alert-coverage','');
      byId('alert-body').replaceChildren();set('alerts-empty','Đang tải dữ liệu để kiểm tra.');byId('alerts-empty').hidden=false;
      set('alert-title','Chọn một cổ phiếu');set('alert-company-name','');set('alert-time','');byId('alert-detail').replaceChildren();byId('alert-open-book').disabled=true;
      return selectedSymbol;
    }
    const stats=model.summary(payload),items=model.select(payload.alerts,filters()),lookup=new Map(payload.ranking.map(r=>[r.symbol,r]));
    if(!items.some(a=>a.symbol===selectedSymbol))selectedSymbol=items[0]?.symbol||null;
    const selected=items.find(a=>a.symbol===selectedSymbol),threshold=payload.alert_rules?.spread_threshold_bps??25;
    set('alert-total-count',`${stats.total} / ${stats.eligible}`);set('alert-capacity-count',stats.capacity);set('alert-spread-count',stats.spread);
    set('alert-threshold-caption',`Trên ${fmt(threshold/100,2)}% giá giữa`);
    document.querySelectorAll('[data-alert-kind]').forEach(card=>card.setAttribute('aria-pressed',String(card.dataset.alertKind===byId('alert-kind').value)));
    set('alerts-context',`${payload.universe} · ${stats.visible} mã trong phạm vi và ngành đã chọn · quy mô ${money(payload.notional_vnd)} đồng.`);
    set('alerts-mode',payload.analysis.mode==='live'?'Đang theo dõi trong phiên':payload.analysis.mode==='saved'?'Kết quả từ ảnh sổ đã lưu':'Đang chờ sổ đủ dữ liệu');
    byId('alerts-mode').dataset.mode=payload.analysis.mode;
    set('alert-filter-count',stats.eligible?`${items.length} / ${stats.total} mã cần kiểm tra`:'Chưa có mã đủ dữ liệu để đánh giá');
    set('alert-coverage',`Đã đánh giá ${stats.eligible}/${stats.visible} mã trong bộ lọc. ${stats.visible>stats.eligible?`${stats.visible-stats.eligible} mã chưa đủ dữ liệu sổ lệnh.`:''}`);
    const pending=byId('alert-threshold-form').dataset.pending==='true';
    if(!pending&&document.activeElement!==byId('alert-spread-threshold'))byId('alert-spread-threshold').value=String(threshold/100);
    if(pending&&Math.abs(Number(byId('alert-spread-threshold').value)*100-threshold)<.001){
      delete byId('alert-threshold-form').dataset.pending;byId('alert-threshold-apply').disabled=false;
    }
    if(byId('alert-threshold-form').dataset.pending!=='true')set('alert-rules-note',`Ngưỡng theo dõi ${fmt(threshold/100,2)}% có thể điều chỉnh; không phải kết luận bất thường.`);
    byId('alert-body').replaceChildren(...items.map(a=>{
      const tr=node('tr',a.symbol===selectedSymbol?'selected':''),symbol=node('td','alert-ticker'),row=lookup.get(a.symbol),reasons=node('td','alert-reasons');
      symbol.append(node('b','',a.symbol),node('small','',row?.group||a.group));
      for(const r of a.reasons)reasons.append(node('span','alert-condition-badge',r.kind==='capacity'?'Thiếu lượng chờ':'Vượt ngưỡng chênh giá'));
      if(a.reasons.some(r=>r.kind==='spread'))reasons.append(node('small','alert-spread-caption',`${fmt(a.spread_vnd,0)} đ · ${fmt(a.spread_bps/100,3)}% · ${fmt(a.spread_ticks,0)} bước giá`));
      const buy=node('td'),sell=node('td'),action=node('td'),button=node('button','button compact','Xem');
      buy.append(meter(a.buy_fill,`Đáp ứng mua ${a.symbol}`));sell.append(meter(a.sell_fill,`Đáp ứng bán ${a.symbol}`));
      button.setAttribute('aria-label',`Xem chi tiết cảnh báo ${a.symbol}`);button.addEventListener('click',()=>onSelect(a.symbol));action.append(button);
      tr.append(symbol,reasons,buy,sell,action);return tr;
    }));
    byId('alerts-empty').hidden=items.length>0;
    set('alerts-empty',!stats.eligible?'Chưa đủ dữ liệu sổ lệnh để đánh giá.':stats.total?'Không có mã phù hợp với bộ lọc.':'Không có mã thỏa điều kiện theo dõi với quy mô và ngưỡng đã chọn.');
    set('alert-title',selected?.symbol||'Chọn một cổ phiếu');set('alert-company-name',selected?(lookup.get(selected.symbol)?.name||selected.group):'Kết quả chi tiết xuất hiện khi bạn chọn một mã trong danh sách.');
    set('alert-time',selected?`${selected.analysis_mode==='live'?'Sổ trong phiên':'Ảnh sổ đã lưu'} · ${dateTime(selected.analysis_at)}`:'');
    byId('alert-detail').replaceChildren(...(selected?detail(selected,lookup.get(selected.symbol)):[]));byId('alert-open-book').disabled=!selected;
    if(currentView()==='alerts')exportButton.disabled=!!payload.sizing_preview||!items.length||byId('alert-threshold-form').dataset.pending==='true';
    return selectedSymbol;
  }
  function download(payload){
    if(!payload)return;const items=model.select(payload.alerts,filters());if(!items.length)return;
    const url=URL.createObjectURL(new Blob([model.csv(payload,items)],{type:'text/csv;charset=utf-8'})),anchor=node('a');
    anchor.href=url;anchor.download=`LOPM_CanhBao_${payload.universe}_${payload.analysis.asof?.slice(0,10)||payload.updated_at.slice(0,10)}.csv`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast(`Đã xuất ${items.length} mã trong danh sách cảnh báo.`);
  }
  function requestFinished(){
    // A failed refresh must not lock the user's Apply control.
    if(byId('alert-threshold-form').dataset.pending==='true')byId('alert-threshold-apply').disabled=false;
  }
  window.lopmAlertsView={render,download,requestFinished};
})();
