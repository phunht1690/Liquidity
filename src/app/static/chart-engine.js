"use strict";
(() => {
  const colors={price:'var(--chart-price)',reference:'var(--chart-reference)',average:'var(--chart-average)',ma20:'var(--chart-ma20)',ma50:'var(--chart-ma50)',depth:'var(--chart-depth)',buy:'var(--chart-up)',sell:'var(--chart-ask)',down:'var(--chart-down)',neutral:'var(--chart-neutral)'};
  const finite=v=>v!==null&&v!==undefined&&typeof v!=="boolean"&&Number.isFinite(Number(v));
  function movingAverage(rows,period){
    let sum=0,queue=[];
    return rows.map(row=>{
      const value=row.close;
      if(!finite(value)){queue=[];sum=0;return null;}
      queue.push(Number(value));sum+=Number(value);
      if(queue.length>period)sum-=queue.shift();
      return queue.length===period?sum/period:null;
    });
  }
  const trendColor=change=>finite(change)&&Number(change)>0?colors.buy:finite(change)&&Number(change)<0?colors.down:colors.neutral;
  function referenceChange(points,fallback=null,fallbackDay=null){
    const last=points.filter(p=>finite(p.last_price_vnd)).at(-1);
    if(!last)return null;
    if(finite(last.reference_price_vnd)&&last.reference_price_vnd>0)return (last.last_price_vnd/last.reference_price_vnd-1)*100;
    const day=last.trading_date||(last.timestamp||'').slice(0,10);
    return day&&day===fallbackDay&&finite(fallback)?Number(fallback):null;
  }
  function sparkline(id,points,change,label){
    const chart=typeof id==='string'?$(id):id;if(!chart)return;
    chart.setAttribute('viewBox','0 0 100 28');chart.replaceChildren();
    const rows=points.filter(p=>finite(p.last_price_vnd));
    chart.style.color=trendColor(change);chart.setAttribute('aria-label',label||'Đường giá thu nhỏ');
    chart.append(svg('title',{},label||'Giá đã ghi nhận trong phiên'));
    if(!rows.length){chart.append(svg('text',{x:50,y:18,'text-anchor':'middle',fill:colors.neutral,'font-size':12},'_'));return;}
    const values=rows.map(p=>Number(p.last_price_vnd)),low=Math.min(...values),high=Math.max(...values),span=Math.max(1,high-low,high*.005),center=(low+high)/2;
    const first=Date.parse(rows[0].timestamp),last=Date.parse(rows.at(-1).timestamp),timed=rows.every(p=>Number.isFinite(Date.parse(p.timestamp)))&&last>first;
    const x=(i,p)=>rows.length===1?50:3+(timed?(Date.parse(p.timestamp)-first)/(last-first):i/(rows.length-1))*94,y=p=>14-(p.last_price_vnd-center)/span*20;
    let d='',i=0,broken=true;
    for(const p of points){
      if(!finite(p.last_price_vnd)){broken=true;continue;}
      d+=`${broken||p.gap_before?'M':'L'}${x(i,p).toFixed(2)},${y(p).toFixed(2)} `;
      broken=false;i++;
    }
    chart.append(svg('path',{d,fill:'none',stroke:'currentColor','stroke-width':1.7,'stroke-linejoin':'round','stroke-linecap':'round'}));
    chart.append(svg('circle',{cx:x(rows.length-1,rows.at(-1)),cy:y(rows[rows.length-1]),r:1.8,fill:'currentColor'}));
  }
  function sessionAverage(bars,observations,timeframe,asof){
    const seconds={'1m':60,'5m':300,'15m':900,'30m':1800,'1h':3600}[timeframe];
    if(!seconds)return bars.map(p=>({...p,avg_match_price_vnd:null}));
    const limit=Date.parse(asof),source=(observations||[]).filter(p=>finite(p.avg_match_price_vnd)&&p.avg_match_price_vnd>0&&Number.isFinite(Date.parse(p.received_at||p.timestamp)))
      .map(p=>({...p,_stamp:Date.parse(p.received_at||p.timestamp)})).sort((a,b)=>a._stamp-b._stamp);
    let index=-1,previousDay=null;
    return bars.map(p=>{
      const end=Math.min(Date.parse(p.timestamp)+seconds*1000-1,Number.isFinite(limit)?limit:Infinity),day=p.trading_date||p.timestamp.slice(0,10);
      while(index+1<source.length&&source[index+1]._stamp<=end)index++;
      const observation=source[index],known=Date.parse(p.timestamp)<=end&&!!observation&&(observation.trading_date||observation.timestamp?.slice(0,10))===day&&end-observation._stamp<=90000;
      const result={...p,avg_match_price_vnd:known?Number(observation.avg_match_price_vnd):null,average_gap_before:previousDay!==day||!!observation?.gap_before};
      previousDay=day;return result;
    });
  }
  function line(chart,rows,value,x,y,color,series,{step=false,area=false,bottom=0,gaps=false,gapKey='gap_before',dashed=false}={}){
    let segment=[];
    function flush(){
      if(!segment.length)return;
      let d=segment.map((p,i)=>i?(step?`H${x(p)}V${y(value(p))}`:`L${x(p)},${y(value(p))}`):`M${x(p)},${y(value(p))}`).join(' ');
      if(area&&segment.length>1)chart.append(svg('path',{d:`${d} L${x(segment.at(-1))},${bottom} L${x(segment[0])},${bottom} Z`,fill:color,opacity:.1,'data-series':series+'-area'}));
      chart.append(segment.length===1?svg('circle',{cx:x(segment[0]),cy:y(value(segment[0])),r:2.7,fill:color,'data-series':series}):svg('path',{d,fill:'none',stroke:color,'stroke-width':series==='price'?2:1.5,'stroke-dasharray':dashed?'5 4':'none','stroke-linejoin':'round','data-series':series}));
      segment=[];
    }
    for(const row of rows){if(!finite(value(row))||(gaps&&row[gapKey]))flush();if(finite(value(row)))segment.push(row);}flush();
  }
  function legend(items){$('history-legend').replaceChildren(...items.map(([name,color])=>{const span=node('span','',`● ${name}`);span.style.color=color;return span;}));}
  function priceRows(points,master=points){
    const ma20=movingAverage(master,20),ma50=movingAverage(master,50),byStamp=new Map(master.map((p,i)=>[p.timestamp,[ma20[i],ma50[i]]]));
    return points.map((p,i)=>{const ma=byStamp.get(p.timestamp)||[];return {...p,_index:i,_ma20:ma[0],_ma50:ma[1]};});
  }
  function price(points,options={}){
    const bars=!!options.bars,rows=bars?priceRows(points,options.masterPoints||points):points.map((p,i)=>({...p,_index:i}));
    const displayTime=value=>options.timeframe==='1d'?new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(value)):dateTime(value);
    const usable=rows.filter(p=>finite(p.last_price_vnd));
    if(!usable.length){window.lopmChartViewport.idle();drawEmpty('history-chart');legend([]);set('history-tooltip','Chưa có điểm giá phù hợp trong khoảng đã chọn.');return;}
    const chart=$('history-chart'),width=Math.max(260,chart.clientWidth||600),height=Math.max(280,chart.clientHeight||320),left=width<450?53:64,right=18,top=16,bottom=28;
    const volume=!!options.volume,volumeHeight=volume?Math.round(height*.21):0,gap=volume?25:0,innerWidth=width-left-right,innerHeight=height-top-bottom-volumeHeight-gap;
    chart.setAttribute('viewBox',`0 0 ${width} ${height}`);chart.replaceChildren();chart.dataset.priceSource=bars?'ohlc':'observations';
    const all=options.allPoints||points,stamp=p=>Date.parse(p.received_at||p.timestamp||p.observation_at);
    const first=stamp(all[0]),last=stamp(all.at(-1)),timeSpan=Math.max(1,last-first);
    const domainRows=options.allPoints||points,domainIndex=new Map(domainRows.map((p,i)=>[p.timestamp,i]));
    const x=p=>bars?(domainRows.length===1?left+innerWidth/2:left+((domainIndex.get(p.timestamp)??p._index)+.5)/domainRows.length*innerWidth):left+(stamp(p)-first)/timeSpan*innerWidth;
    const values=usable.flatMap(p=>[Number(p.last_price_vnd),...(bars&&options.type==='candles'?[p.low,p.high]:[]),...(options.reference&&finite(p.reference_price_vnd)?[p.reference_price_vnd]:[]),...(options.average&&finite(p.avg_match_price_vnd)?[p.avg_match_price_vnd]:[]),...(options.ma20&&finite(p._ma20)?[p._ma20]:[]),...(options.ma50&&finite(p._ma50)?[p._ma50]:[])]);
    const low=Math.min(...values),high=Math.max(...values),pad=Math.max(1,(high-low)*.12,high*.001),min=low-pad,max=high+pad;
    const y=v=>top+(max-v)/(max-min)*innerHeight;
    for(let i=0;i<=4;i++){
      const yy=top+i/4*innerHeight;chart.append(svg('line',{x1:left,x2:width-right,y1:yy,y2:yy,class:'chart-grid'}),svg('text',{x:left-8,y:yy+3,'text-anchor':'end',class:'chart-label'},fmt(max-(max-min)*i/4,0)));
    }
    const labelStamp=(p,short)=>new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',...(short?{hour:'2-digit',minute:'2-digit',hour12:false}:{day:'2-digit',month:'2-digit',...(width>600?{year:'2-digit'}:{})})}).format(new Date(stamp(p)));
    const oneDay=usable[0].trading_date===usable.at(-1).trading_date;
    const tickCount=Math.min(width<500?3:5,Math.max(1,rows.length));
    for(let i=0;i<tickCount;i++){
      const index=tickCount===1?0:Math.round(i/(tickCount-1)*(rows.length-1)),p=rows[index];
      const xx=bars?x(p):left+(tickCount===1?.5:i/(tickCount-1))*innerWidth;
      const date=bars?labelStamp(p,oneDay&&options.timeframe!=='1d'):clock(new Date(first+(tickCount===1?0:i/(tickCount-1))*timeSpan).toISOString()).slice(0,5);
      chart.append(svg('text',{x:xx,y:height-6,'text-anchor':i===0?'start':i===tickCount-1?'end':'middle',class:'chart-label'},date));
    }
    if(bars&&options.type==='candles'){
      const candleWidth=Math.max(1.2,Math.min(17,innerWidth/domainRows.length*.65));
      for(const p of rows){
        const color=p.close>=p.open?colors.buy:colors.down;
        chart.append(svg('line',{x1:x(p),x2:x(p),y1:y(p.high),y2:y(p.low),stroke:color,'stroke-width':1,'data-series':'candles'}),svg('rect',{x:x(p)-candleWidth/2,y:Math.min(y(p.open),y(p.close)),width:candleWidth,height:Math.max(1,Math.abs(y(p.open)-y(p.close))),fill:color,'data-series':'candles'}));
      }
    }else line(chart,rows,p=>p.last_price_vnd,x,y,colors.price,'price',{step:options.type==='step',area:options.type==='area',bottom:top+innerHeight,gaps:!bars});
    const entries=bars&&options.type==='candles'?[['Nến tăng',colors.buy],['Nến giảm',colors.down]]:[[bars?'Giá đóng nến':'Giá khớp đã nhận',colors.price]];
    if(options.reference){line(chart,rows,p=>p.reference_price_vnd,x,y,colors.reference,'reference',{gaps:!bars,dashed:true});entries.push(['Tham chiếu',colors.reference]);}
    if(options.average){line(chart,rows,p=>p.avg_match_price_vnd,x,y,colors.average,'average',{gaps:true,gapKey:bars?'average_gap_before':'gap_before'});entries.push(['BQ phiên SSI đã ghi',colors.average]);}
    if(bars&&options.ma20){line(chart,rows,p=>p._ma20,x,y,colors.ma20,'ma20');entries.push(['MA20',colors.ma20]);}
    if(bars&&options.ma50){line(chart,rows,p=>p._ma50,x,y,colors.ma50,'ma50');entries.push(['MA50',colors.ma50]);}
    if(volume){
      const key=bars?'volume_shares':'interval_volume_shares',maxVolume=Math.max(1,...rows.filter(p=>finite(p[key])).map(p=>p[key])),base=top+innerHeight+gap+volumeHeight,barWidth=Math.max(1,Math.min(17,innerWidth/Math.max(1,domainRows.length)*.65));
      chart.append(svg('line',{x1:left,x2:width-right,y1:base,y2:base,class:'chart-grid'}));
      for(const p of rows)if(finite(p[key])){
        const hh=p[key]/maxVolume*volumeHeight,color=bars?(p.close>=p.open?colors.buy:colors.down):colors.price;
        chart.append(svg('rect',{x:x(p)-barWidth/2,y:base-hh,width:barWidth,height:hh,fill:color,class:'ohlc-volume','data-series':'volume'}));
      }
      chart.append(svg('text',{x:left+3,y:top+innerHeight+gap-5,class:'chart-annotation'},bars?'KL mỗi nến · CP':'KL giữa hai bản nhận · CP'));
      const compact=v=>v>=1e6?`${fmt(v/1e6,1)} tr`:v>=1e3?`${fmt(v/1e3,0)}k`:fmt(v,0);
      chart.append(svg('text',{x:width-right,y:top+innerHeight+gap-5,'text-anchor':'end',class:'chart-annotation'},`Cao nhất: ${compact(maxVolume)} CP`));
    }
    legend(entries);$('history-axes').replaceChildren(node('span','','Giá · đồng'),node('span','',volume?'Khối lượng · cổ phiếu':''));
    $('history-chart').setAttribute('aria-label',`${bars?'Giá SSI OHLC':'Các lần nhận giá đã lưu'} · ${options.symbol||''}`);
    const ctx={chart,width,height,left,right,top,bottom,innerWidth,innerHeight};
    window.lopmChartViewport.attach(ctx,rows,x,p=>{
      const text=bars?`${displayTime(p.timestamp)} · Mở ${fmt(p.open,0)} · Cao ${fmt(p.high,0)} · Thấp ${fmt(p.low,0)} · Đóng ${fmt(p.close,0)} đ · KL ${fmt(p.volume_shares,0)} CP${p.is_closed?'':' · nến đang hình thành'}`:`${dateTime(p.received_at||p.timestamp)} · Giá ${fmt(p.last_price_vnd,0)} đ · KL giữa hai lần nhận ${fmt(p.interval_volume_shares,0)} CP`;
      return {title:displayTime(p.received_at||p.timestamp),text,lines:[...(bars?[["Mở / Cao",`${fmt(p.open,0)} / ${fmt(p.high,0)} đ`],["Thấp / Đóng",`${fmt(p.low,0)} / ${fmt(p.close,0)} đ`]]:[["Giá khớp",`${fmt(p.last_price_vnd,0)} đ`]]),[bars?'KL nến':'KL giữa hai bản',`${fmt(p[bars?'volume_shares':'interval_volume_shares'],0)} CP`],...(options.reference?[["Tham chiếu",`${fmt(p.reference_price_vnd,0)} đ`,colors.reference]]:[]),...(options.average?[["BQ phiên SSI",`${fmt(p.avg_match_price_vnd,0)} đ`,colors.average]]:[]),...(options.ma20?[["MA20",`${fmt(p._ma20,0)} đ`,colors.ma20]]:[]),...(options.ma50?[["MA50",`${fmt(p._ma50,0)} đ`,colors.ma50]]:[]),...(p.gap_before?[["Khoảng trước điểm","Thiếu mẫu / đổi pha"]]:[])]};
    },p=>finite(p.last_price_vnd)?y(p.last_price_vnd):NaN);
    const tail=usable.at(-1);set('history-tooltip',bars?`${options.timeframe==='1d'?'Phiên':'Nến'} gần nhất: ${displayTime(tail.timestamp)} · Đóng ${fmt(tail.close,0)} đ · KL ${fmt(tail.volume_shares,0)} CP`:'Di chuyển trên biểu đồ để xem từng lần nhận. Khoảng mất dữ liệu được giữ trống.');
  }
  function liquidity(points,options={}){
    const rows=points.filter(p=>Number.isFinite(Date.parse(p.received_at||p.timestamp||p.observation_at)));
    const enabledKeys=[...(options.spread?['spread_bps']:[]),...(options.depth?['depth_min_vnd']:[]),...(options.bid?['depth_bid_vnd']:[]),...(options.ask?['depth_ask_vnd']:[])];
    const usable=rows.filter(p=>p.valid!==false&&enabledKeys.some(k=>finite(p[k])));
    if(!usable.length||!enabledKeys.length){window.lopmChartViewport.idle();drawEmpty('history-chart');legend([]);set('history-tooltip',enabledKeys.length?'Chưa có sổ hợp lệ trong đoạn này. Thử Toàn khoảng hoặc chọn phiên khác.':'Bật một đường để theo dõi.');return;}
    const chart=$('history-chart'),width=Math.max(260,chart.clientWidth||600),height=Math.max(280,chart.clientHeight||320),left=width<450?42:54,right=width<450?44:64,top=16,bottom=28,innerHeight=height-top-bottom,innerWidth=width-left-right,c={chart,width,height,left,right,top,bottom,innerHeight,innerWidth};
    chart.setAttribute('viewBox',`0 0 ${width} ${height}`);chart.replaceChildren();chart.dataset.priceSource='observations';
    const all=options.allPoints||rows,stamp=p=>Date.parse(p.received_at||p.timestamp||p.observation_at),first=stamp(all[0]),span=Math.max(1,stamp(all.at(-1))-first),x=p=>left+(stamp(p)-first)/span*innerWidth;
    const spreadMax=Math.max(1,...usable.filter(p=>finite(p.spread_bps)).map(p=>p.spread_bps))*1.12,depthKeys=[...(options.depth?['depth_min_vnd']:[]),...(options.bid?['depth_bid_vnd']:[]),...(options.ask?['depth_ask_vnd']:[])],hasDepth=depthKeys.length>0;
    const depthMax=Math.max(.01,...usable.flatMap(p=>depthKeys.map(k=>finite(p[k])?p[k]/1e9:0)))*1.12;
    for(let i=0;i<=4;i++){
      const yy=top+i/4*innerHeight;chart.append(svg('line',{x1:left,x2:width-right,y1:yy,y2:yy,class:'chart-grid'}));
      if(options.spread)chart.append(svg('text',{x:left-7,y:yy+3,'text-anchor':'end',class:'chart-label'},fmt(spreadMax*(1-i/4),1)));
      if(hasDepth)chart.append(svg('text',{x:width-right+7,y:yy+3,class:'chart-label'},fmt(depthMax*(1-i/4),2)));
    }
    const safe=rows.map(p=>({...p,...Object.fromEntries(['spread_bps','depth_min_vnd','depth_bid_vnd','depth_ask_vnd'].map(k=>[k,p.valid!==false?p[k]:null]))}));
    if(options.spread)line(chart,safe,p=>p.spread_bps,x,v=>top+(1-v/spreadMax)*innerHeight,colors.price,'spread',{gaps:true});
    for(const [enabled,key,color,name] of [[options.bid,'depth_bid_vnd',colors.buy,'bid-depth'],[options.ask,'depth_ask_vnd',colors.sell,'ask-depth']])if(enabled)line(chart,safe,p=>finite(p[key])?p[key]/1e9:null,x,v=>top+(1-v/depthMax)*innerHeight,color,name,{gaps:true});
    if(options.depth)line(chart,safe,p=>finite(p.depth_min_vnd)?p.depth_min_vnd/1e9:null,x,v=>top+(1-v/depthMax)*innerHeight,colors.depth,'depth',{gaps:true,dashed:true});
    for(let i=0;i<=3;i++)chart.append(svg('text',{x:left+i/3*innerWidth,y:height-8,'text-anchor':'middle',class:'chart-label'},clock(new Date(first+i/3*span).toISOString()).slice(0,5)));
    legend([...(options.spread?[['Chênh mua–bán',colors.price]]:[]),...(options.depth?[['Phía ít hơn · nét đứt',colors.depth]]:[]),...(options.bid?[['Chờ mua',colors.buy]]:[]),...(options.ask?[['Chờ bán',colors.sell]]:[])]);
    $('history-axes').replaceChildren(node('span','',options.spread?'Chênh · bps (100 bps = 1%)':''),node('span','',hasDepth?'Lượng chờ · tỷ đồng':''));
    set('history-tooltip','Đường ngắt khi sổ không hợp lệ, thiếu mẫu hoặc đổi phiên.');
    chart.setAttribute('aria-label',`Chênh giá và giá trị chờ trên các mức SSI đã cấp · ${options.symbol||''}`);
    window.lopmChartViewport.attach(c,rows,x,p=>{
      const good=p.valid!==false,text=good?`${dateTime(p.received_at||p.timestamp)} · Chênh ${fmt(p.spread_bps,2)} bps · Độ dày ${money(p.depth_min_vnd)} đồng`:`${dateTime(p.received_at||p.timestamp)} · Chưa có sổ hợp lệ tại thời điểm này`;
      return {title:dateTime(p.received_at||p.timestamp),text,lines:good?[["Chênh mua–bán",`${fmt(p.spread_vnd,0)} đ · ${fmt(p.spread_bps,2)} bps`,colors.price],[`Chờ mua · ${p.known_bid_levels??'_'} mức`,`${money(p.depth_bid_vnd)} đồng`,colors.buy],[`Chờ bán · ${p.known_ask_levels??'_'} mức`,`${money(p.depth_ask_vnd)} đồng`,colors.sell],["Phía ít hơn",`${money(p.depth_min_vnd)} đồng`,colors.depth]]:[["Trạng thái","Chưa có sổ hợp lệ"]]};
    },p=>p.valid===false?NaN:options.spread&&finite(p.spread_bps)?top+(1-p.spread_bps/spreadMax)*innerHeight:NaN);
  }
  window.lopmChartEngine={price,liquidity,sparkline,movingAverage,priceRows,sessionAverage,trendColor,referenceChange,colors};
})();
