"use strict";
(() => {
  const engine=window.lopmChartEngine;
  function chartIdentity(points,symbol,change,changeDay=null){
    const pct=engine.referenceChange(points,change,changeDay);
    set('chart-symbol-label',symbol||'_');set('chart-change-label',valid(pct)?signed(pct)+'%':'');
    $('chart-change-label').style.color=engine.trendColor(pct);
    engine.sparkline('chart-sparkline',points,pct,`${symbol||''} · ${valid(pct)?signed(pct)+'% so với tham chiếu':'giá trong khoảng đang xem'}`);
  }
  function depth(payload){
    const r=payload?.selected;
    if(!r?.valid){drawEmpty('depth-chart');set('depth-tooltip','_');set('depth-chart-asof','_');return;}
    const c=baseChart('depth-chart',55,24),{chart,width,height,left,right,top,innerWidth,innerHeight}=c;
    const sides=['bids','asks'].map((side,index)=>{
      let total=0;return r[side].filter(p=>valid(p.price)&&p.price>0&&valid(p.volume)&&p.volume>0).map(p=>{total+=p.price*p.volume;return {price:p.price,total,side:index===0?'Chờ mua':'Chờ bán'};});
    });
    const all=sides.flat();if(!all.length){drawEmpty('depth-chart');set('depth-tooltip','Hai phía hiện không có lượng chờ.');set('depth-chart-asof',`${r.symbol} · ${dateTime(r.analysis_at)}`);return;}const min=Math.min(...all.map(p=>p.price)),max=Math.max(...all.map(p=>p.price)),span=Math.max(1,max-min),highest=Math.max(1,...all.map(p=>p.total))*1.1;
    const x=p=>left+(p.price-min)/span*innerWidth,y=p=>top+(1-p.total/highest)*innerHeight;
    for(let i=0;i<=4;i++){const yy=top+i/4*innerHeight;chart.append(svg('line',{x1:left,x2:width-right,y1:yy,y2:yy,class:'chart-grid'}),svg('text',{x:left-7,y:yy+3,'text-anchor':'end',class:'chart-label'},fmt(highest*(1-i/4)/1e9,2)));}
    for(const [i,points] of sides.entries()){if(!points.length)continue;
      let d=points.map((p,j)=>j?`H${x(p)}V${y(p)}`:`M${x(p)},${y(p)}`).join(' ');
      const color=i===0?engine.colors.buy:engine.colors.sell;
      chart.append(svg('path',{d:`${d} L${x(points.at(-1))},${top+innerHeight} L${x(points[0])},${top+innerHeight}Z`,fill:color,opacity:.12}),svg('path',{d,fill:'none',stroke:color,'stroke-width':2,'data-side':i===0?'bid':'ask'}));
      points.forEach(p=>chart.append(svg('circle',{cx:x(p),cy:y(p),r:3,fill:color})));
    }
    const ordered=all.slice().sort((a,b)=>a.price-b.price),ticks=[...new Map((width<450?[ordered[0],ordered.at(-1)]:[ordered[0],ordered[Math.floor(ordered.length/3)],ordered[Math.floor(2*ordered.length/3)],ordered.at(-1)]).map(p=>[p.price,p])).values()];
    ticks.forEach((p,i)=>chart.append(svg('text',{x:x(p),y:height-8,'text-anchor':i===0?'start':i===ticks.length-1?'end':'middle',class:'chart-label'},fmt(p.price,0))));
    set('depth-chart-asof',`${r.symbol} · ${r.analysis_mode==='live'?'Trong phiên':'Ảnh sổ đã lưu'} · ${dateTime(r.analysis_at)}`);
    set('depth-tooltip','Di chuyển trên đường để xem giá trị chờ tích lũy.');
    chartInteraction(c,all.sort((a,b)=>a.price-b.price),x,'depth-tooltip',p=>`${p.side} · ${fmt(p.price,0)} đ · Tích lũy ${money(p.total)} đồng`);
    window.lopmChartMotion?.present(chart,`depth|${r.symbol}`);
  }
  function render(payload){
    const r=payload?.selected;
    const asof=$('market-price-asof');if(asof){const caption=window.lopmProductUX.priceCaption(r);asof.hidden=!caption;asof.textContent=caption;}
    depth(payload);
  }
  window.lopmWidgets={render,chartIdentity};
  render(state);
  window.addEventListener('resize',()=>{if(state)depth(state);});
})();
