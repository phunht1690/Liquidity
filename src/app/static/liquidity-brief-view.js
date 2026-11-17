"use strict";
(() => {
  const model=window.lopmLiquidityBriefModel,$=id=>document.getElementById(id);
  let payload=null,active='all',expanded=false,filterChange=()=>{},groupChange=()=>{};
  const put=(id,value)=>{const e=$(id);if(e)e.textContent=String(value);};
  const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e;};
  function refreshFilters(next,baseRows=next?.ranking||[]){
    for(const button of document.querySelectorAll('[data-liquidity-filter]')){
      const id=button.dataset.liquidityFilter,selected=active===id;
      button.setAttribute('aria-pressed',String(selected));button.disabled=!next;
    }
    const select=$('liquidity-filter');
    for(const [id,label] of model.filters){
      const option=[...select.options].find(o=>o.value===id);
      if(option)option.textContent=`${label} · ${next?model.fmt(model.filterRows(next,id,baseRows).length,0):'_'}`;
    }
    select.value=active;select.disabled=!next;
    const label=model.filters.find(([id])=>id===active)?.[1]||'Tất cả';
    put('liquidity-filter-note',active==='all'?'Số mã trong từng lựa chọn tính sau tìm kiếm và danh sách theo dõi.':`${label} · theo ảnh sổ và quy mô đang xem; áp dụng cùng tìm kiếm và danh sách theo dõi.`);
  }
  function sectorCell(value,note){const td=node('td','',value);if(note)td.append(node('small','',note));return td;}
  function renderSectors(next){
    const groups=model.sectors(next,$('sector-sort').value),shown=expanded?groups:groups.slice(0,6);
    const body=$('sector-liquidity-body'),focused=body.contains(document.activeElement)?document.activeElement:null,existing=new Map([...body.children].map(r=>[r.dataset.sector,r]));
    const rows=shown.map(g=>{
      let tr=existing.get(g.name);
      if(!tr){tr=node('tr');tr.dataset.sector=g.name;const th=node('th');th.scope='row';const button=node('button','sector-name',g.name);button.type='button';button.addEventListener('click',()=>{window.lopmWorkspaceUI?.selectMarket('stocks');groupChange(g.name);});th.append(button);tr.append(th);}
      tr.classList.toggle('selected',next.group===g.name);
      const button=tr.querySelector('button');button.setAttribute('aria-label',`Lọc ngành ${g.name}`);
      while(tr.children.length>1)tr.lastElementChild.remove();
      tr.append(sectorCell(`${g.books}/${g.total}`,'mã trong ngành'),
        sectorCell(model.finite(g.medianSpreadBps)?model.fmt(g.medianSpreadBps/100,3)+'%':'_',`${g.spreadCount} mã có chênh giá`),
        sectorCell(model.money(g.medianDepthVnd),`${g.depthCount} mã có độ dày`),
        sectorCell(model.pct(g.completeRatio),`${g.complete}/${g.comparable} mã tính được hai phía`),
        sectorCell(model.money(g.turnoverVnd),`${g.turnoverCount}/${g.total} mã · ${model.day(g.turnoverDay)}`));
      return tr;
    });
    if(rows.length){body.replaceChildren(...rows);if(focused&&body.contains(focused))focused.focus({preventScroll:true});}
    else{const tr=node('tr'),td=node('td','empty-row','Chưa có dữ liệu trong phạm vi này.');td.colSpan=6;tr.append(td);body.replaceChildren(tr);}
    const limit=$('sector-expand');limit.hidden=groups.length<=6;limit.textContent=expanded?'Thu gọn':`Xem tất cả ${groups.length} ngành`;limit.setAttribute('aria-expanded',String(expanded));
    $('sector-reset').hidden=next.group==='all';
    put('sector-liquidity-caption',`${groups.length} ngành · bấm tên ngành để xem bảng giá của ngành đó. Mỗi chỉ tiêu ghi rõ số mã có dữ liệu.`);
    put('sector-turnover-day',`Phiên ${model.day(model.turnoverDay(next))}`);
  }
  function render(next){
    if(!next){clear();return;}
    payload=next;const stats=model.summarize(next);
    put('brief-books',`${model.fmt(stats.books,0)}/${model.fmt(stats.total,0)}`);
    put('brief-books-note','mã trong phạm vi');
    put('brief-wide',stats.spreadCount?`${model.fmt(stats.wide,0)}/${model.fmt(stats.spreadCount,0)}`:'_');
    const threshold=String(Number((stats.thresholdBps/100).toFixed(3))).replace('.',',');
    put('brief-wide-note',`mã · ngưỡng ${threshold}%`);
    put('brief-partial',stats.capacityKnown?`${model.fmt(stats.partial,0)}/${model.fmt(stats.capacityKnown,0)}`:'_');
    put('brief-partial-note','mã tính được mức đáp ứng');
    put('brief-spread',model.finite(stats.medianSpreadBps)?model.fmt(stats.medianSpreadBps/100,3)+'%':'_');
    put('brief-spread-note',`${stats.spreadCount} mã có chênh giá`);
    put('brief-basis',`Sổ ${model.date(next.analysis?.asof)} · Quy mô ${model.money(next.notional_vnd)}${next.sizing_preview?' · Đang đồng bộ':''}`);
    put('ranking-basis','Giá theo thời điểm từng mã.');
    for(const button of document.querySelectorAll('[data-brief-export]'))button.disabled=!!next.sizing_preview;
    renderSectors(next);
  }
  function clear(){
    payload=null;for(const id of ['brief-books','brief-wide','brief-partial','brief-spread'])put(id,'_');
    for(const id of ['brief-books-note','brief-wide-note','brief-partial-note','brief-spread-note'])put(id,'Đang nhận dữ liệu.');
    put('ranking-basis','Đang nhận dữ liệu trong phạm vi đã chọn.');
    put('brief-basis','Đang nhận dữ liệu trong phạm vi đã chọn.');put('brief-export-result','');
    put('sector-liquidity-caption','Đang nhận dữ liệu theo ngành.');
    const tr=node('tr'),td=node('td','empty-row','_');td.colSpan=6;tr.append(td);$('sector-liquidity-body').replaceChildren(tr);put('sector-turnover-day','');
    for(const button of document.querySelectorAll('[data-brief-export]'))button.disabled=true;
    $('sector-expand').hidden=true;$('sector-reset').hidden=true;refreshFilters(null);
  }
  for(const button of document.querySelectorAll('[data-liquidity-filter]'))button.addEventListener('click',()=>{
    active=button.dataset.liquidityFilter;window.lopmWorkspaceUI?.selectMarket('stocks');filterChange();
    if(button.dataset.filterJump==='true')location.hash='ranking';
  });
  $('liquidity-filter').addEventListener('change',event=>{
    active=model.filters.some(([id])=>id===event.target.value)?event.target.value:'all';filterChange();
  });
  $('sector-sort').addEventListener('change',()=>{if(payload)renderSectors(payload);});
  $('sector-expand').addEventListener('click',()=>{expanded=!expanded;if(payload)renderSectors(payload);});
  $('sector-reset').addEventListener('click',()=>groupChange('all'));
  for(const button of document.querySelectorAll('[data-brief-export]'))button.addEventListener('click',()=>{
    if(!payload||payload.sizing_preview)return;
    const snapshot=payload,now=new Date().toISOString(),html=model.reportHTML(snapshot,now);
    const url=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'})),a=document.createElement('a');
    const sourceDay=(snapshot.analysis?.asof||snapshot.updated_at||now).slice(0,10);
    a.href=url;a.download=`LOPM_ThanhKhoan_${snapshot.universe}_${sourceDay}.html`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    put('brief-export-result',`Đã xuất bản tóm tắt ${model.scopeLabel(snapshot)} · ảnh sổ ${model.date(snapshot.analysis?.asof)}.`);
  });
  window.lopmLiquidityBrief={render,clear,refreshFilters,filterRows:(p,rows)=>model.filterRows(p,active,rows),filterId:()=>active,
    pending(){for(const button of document.querySelectorAll('[data-brief-export]'))button.disabled=true;put('brief-export-result','');},
    resetFilter(){active='all';expanded=false;},onFilterChange(callback){filterChange=callback;},onGroupChange(callback){groupChange=callback;}};
})();
