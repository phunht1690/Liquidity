"use strict";
(() => {
  const model=window.lopmChartViewModel,panel=$('telemetry-panel'),chart=$('history-chart'),nav=$('chart-navigator');
  let source=[],coords=[],selected=[0,0],identity='',bars=false,metric='price',change=()=>{},context=null,gesture=null,pinned=false,chosen=0,expanded=false,restore=null;
  let remembered=null,redrawFrame=null;
  const full=()=>selected[0]===0&&selected[1]===Math.max(0,source.length-1);
  const zoom=(factor,anchor=.5)=>bars?model.zoom(selected,factor,source.length,anchor):model.zoomDomain(selected,factor,coords,anchor);
  const shift=(current,fraction)=>bars?model.pan(current,fraction*(current[1]-current[0]),source.length):model.panDomain(current,fraction*(coords[current[1]]-coords[current[0]]),coords);
  const timeLabel=p=>dateTime(p?.received_at||p?.timestamp||p?.observation_at);
  const formatStamp=(p,options)=>Number.isFinite(model.stamp(p))?new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',...options}).format(new Date(model.stamp(p))):'_';
  const dayLabel=p=>formatStamp(p,{day:'2-digit',month:'2-digit',year:'numeric'});
  const timePart=(p,seconds=false)=>formatStamp(p,{hour:'2-digit',minute:'2-digit',...(seconds?{second:'2-digit'}:{}),hour12:false});
  function rangeLabel(){
    const start=source[selected[0]],end=source[selected[1]],a=dayLabel(start),b=dayLabel(end),daily=bars&&$('chart-timeframe').value==='1d';
    const seconds=!bars&&model.stamp(end)-model.stamp(start)<900000;
    const span=daily?(a===b?a:`${a} → ${b}`):a===b?`${a} · ${timePart(start,seconds)} – ${timePart(end,seconds)}`:`${a} ${timePart(start)} → ${b} ${timePart(end)}`;
    return span+(full()?'':` · ${selected[1]-selected[0]+1}/${source.length} ${bars?'nến':'bản'}`);
  }
  function schedule(){if(redrawFrame===null)redrawFrame=requestAnimationFrame(()=>{redrawFrame=null;change();});}
  function clearHover(){pinned=false;$('chart-hover-card').hidden=true;context?.cross?.setAttribute('opacity',0);context?.dot?.setAttribute('opacity',0);}
  function apply(next,preset=null){
    const value=model.range(next[0],next[1],source.length);
    if(value[0]===selected[0]&&value[1]===selected[1])return;
    selected=value;if(metric==='liquidity')$('window-select').value=preset||(full()?'1440':'custom');if(!gesture)window.lopmChartMotion?.requestView(chart);clearHover();schedule();
  }
  function prepare(points,options={}){
    const nextKey=options.key||'',same=nextKey===identity,wasFull=full(),oldEnd=source.length-1,follow=selected[1]===oldEnd;
    const previous=source.length?[model.stamp(source[selected[0]]),model.stamp(source[selected[1]])]:null;
    source=points;bars=!!options.bars;metric=options.metric||'price';coords=model.coordinates(source,bars);change=options.onChange||change;
    if(!same||!previous){selected=[0,Math.max(0,source.length-1)];if(metric==='liquidity')$('window-select').value='1440';clearHover();}
    else if(wasFull)selected=[0,Math.max(0,source.length-1)];
    else{
      const times=source.map(model.stamp),end=model.nearest(times,previous[1]),start=model.nearest(times,previous[0]);
      selected=model.range(start,end,source.length);
      if(follow&&source.length>oldEnd+1)selected=bars?model.pan(selected,source.length-1-selected[1],source.length):model.panDomain(selected,1-coords[selected[1]],coords);
    }
    identity=nextKey;renderNavigator();
    return {points:source.slice(selected[0],selected[1]+1),bounds:[...selected]};
  }
  function pending(message='Đang đọc dữ liệu…'){
    window.lopmChartMotion?.reset(chart);
    source=[];coords=[];selected=[0,0];identity='';context=null;clearHover();nav.replaceChildren();
    set('chart-visible-range',message);set('chart-navigator-caption','_');$('chart-reset').hidden=true;
    $('history-legend').replaceChildren();set('history-tooltip','');$('window-select').disabled=true;
    for(const id of ['chart-zoom-in','chart-zoom-out','chart-reset','chart-pan','chart-select'])$(id).disabled=true;
  }
  function trailing(minutes){
    if(!source.length)return;
    if(Number(minutes)>=1440){apply([0,source.length-1],'1440');return;}
    const good=source.map((p,i)=>({p,i})).filter(({p})=>p.valid!==false&&(valid(p.spread_bps)||valid(p.depth_min_vnd)));
    const last=good.at(-1)?.i??source.length-1,cutoff=model.stamp(source[last])-Number(minutes)*60000;
    const first=source.findIndex(p=>model.stamp(p)>=cutoff);apply([Math.max(0,first),last],String(minutes));
  }
  function pathSegments(rows,value,x,y){
    let d='',broken=true;
    for(const {p,i} of rows){const v=value(p);if(!valid(v)){broken=true;continue;}d+=`${broken||p.gap_before?'M':'L'}${x(i).toFixed(2)},${y(Number(v)).toFixed(2)} `;broken=false;}
    return d;
  }
  function renderNavigator(){
    const focusedHandle=nav.contains(document.activeElement)?document.activeElement.dataset.handle:null;
    nav.replaceChildren();const n=source.length,width=Math.max(260,nav.clientWidth||600),height=76,left=12,right=12,inner=width-left-right;
    nav.setAttribute('viewBox',`0 0 ${width} ${height}`);
    const enabled=n>1;
    $('window-select').disabled=!enabled;
    for(const id of ['chart-zoom-in','chart-zoom-out','chart-reset','chart-pan','chart-select'])$(id).disabled=!enabled;
    $('chart-zoom-in').disabled=!enabled||selected[1]-selected[0]<=1;
    $('chart-zoom-out').disabled=!enabled||full();$('chart-reset').disabled=!enabled||full();$('chart-reset').hidden=!enabled||full();
    if(!n){set('chart-visible-range','Chưa có điểm trong khoảng này.');set('chart-navigator-caption','_');return;}
    set('chart-visible-range',rangeLabel());
    set('chart-navigator-caption',bars?'Toàn khoảng đã tải':'Toàn phiên đã lưu');
    const x=i=>left+coords[i]*inner,rows=source.map((p,i)=>({p,i}));
    const lines=metric==='price'?[[p=>p.last_price_vnd,'var(--chart-price)']]:[['chart-spread','spread_bps','var(--chart-price)'],['chart-depth','depth_min_vnd','var(--chart-depth)'],['chart-bid-depth','depth_bid_vnd','var(--chart-up)'],['chart-ask-depth','depth_ask_vnd','var(--chart-ask)']].filter(([id])=>$(id).checked).map(([,key,color])=>[p=>p.valid!==false?p[key]:null,color]);
    // Each overview series is normalized separately; numeric scales belong to the main chart.
    for(const [value,color] of lines){
      const values=source.map(value).filter(valid);if(!values.length)continue;
      const lo=Math.min(...values),hi=Math.max(...values),span=Math.max(1,hi-lo),y=v=>18+(hi-v)/span*36;
      // Keep gaps and extrema while limiting DOM/path work for long recordings.
      const sampled=[];const step=Math.max(1,Math.ceil(rows.length/500));
      for(let j=0;j<rows.length;j+=step){
        const bucket=rows.slice(j,j+step),indices=new Set([0,bucket.length-1]);let min=0,max=0;
        bucket.forEach((r,k)=>{if(valid(value(r.p))&&(!valid(value(bucket[min].p))||value(r.p)<value(bucket[min].p)))min=k;if(valid(value(r.p))&&(!valid(value(bucket[max].p))||value(r.p)>value(bucket[max].p)))max=k;if(!valid(value(r.p))||r.p.gap_before)indices.add(k);});
        indices.add(min);indices.add(max);[...indices].sort((a,b)=>a-b).forEach(k=>sampled.push(bucket[k]));
      }
      nav.append(svg('path',{d:pathSegments(sampled,value,x,y),fill:'none',stroke:color,'stroke-width':1.25,opacity:.7}));
    }
    const a=x(selected[0]),b=x(selected[1]);
    nav.append(svg('rect',{x:left,y:8,width:Math.max(0,a-left),height:54,class:'navigator-shade'}),svg('rect',{x:b,y:8,width:Math.max(0,width-right-b),height:54,class:'navigator-shade'}),svg('rect',{x:a,y:8,width:Math.max(1,b-a),height:54,class:'navigator-selection','data-handle':'move'}));
    for(const [xx,handle,index] of [[a,'start',0],[b,'end',1]]){
      const grip=svg('rect',{x:xx-5,y:8,width:10,height:54,rx:3,class:'navigator-handle','data-handle':handle,role:'slider',tabindex:enabled?0:-1,'aria-label':index?'Điểm kết thúc khoảng xem':'Điểm bắt đầu khoảng xem','aria-orientation':'horizontal','aria-disabled':String(!enabled),'aria-valuemin':index&&enabled?selected[0]+1:0,'aria-valuemax':index?Math.max(0,n-1):Math.max(0,selected[1]-1),'aria-valuenow':selected[index],'aria-valuetext':timeLabel(source[selected[index]])});
      nav.append(grip,svg('line',{x1:xx,x2:xx,y1:27,y2:43,class:'navigator-grip','pointer-events':'none'}));
      if(focusedHandle===handle)grip.focus({preventScroll:true});
    }
    const sameDay=dayLabel(source[0])===dayLabel(source.at(-1));
    const edge=p=>sameDay&&!(bars&&$('chart-timeframe').value==='1d')?timePart(p):dayLabel(p);
    nav.append(svg('text',{x:left,y:75,class:'chart-label'},edge(source[0])),svg('text',{x:width-right,y:75,'text-anchor':'end',class:'chart-label'},edge(source.at(-1))));
  }
  function navIndex(event){const rect=nav.getBoundingClientRect(),width=Math.max(260,nav.clientWidth||600),f=((event.clientX-rect.left)/rect.width*width-12)/(width-24);return model.nearest(coords,Math.max(0,Math.min(1,f)));}
  nav.addEventListener('pointerdown',event=>{
    if(source.length<2||event.button!==0)return;event.preventDefault();
    const index=navIndex(event),handle=event.target.dataset.handle||'select',kind=handle==='move'&&full()?'select':handle;
    gesture={surface:'nav',kind,start:index,initial:[...selected],moved:false};nav.setPointerCapture(event.pointerId);
  });
  nav.addEventListener('pointermove',event=>{
    if(gesture?.surface!=='nav')return;const i=navIndex(event),g=gesture;g.moved=true;
    if(g.kind==='move')apply(bars?model.pan(g.initial,i-g.start,source.length):model.panDomain(g.initial,coords[i]-coords[g.start],coords));
    else if(g.kind==='start')apply([Math.min(i,g.initial[1]-1),g.initial[1]]);
    else if(g.kind==='end')apply([g.initial[0],Math.max(i,g.initial[0]+1)]);
    else apply([g.start,i]);
  });
  nav.addEventListener('pointerup',event=>{if(gesture?.surface==='nav'){if(!gesture.moved&&gesture.kind==='select'){const i=navIndex(event);apply(bars?model.pan(selected,i-(selected[0]+selected[1])/2,source.length):model.panDomain(selected,coords[i]-(coords[selected[0]]+coords[selected[1]])/2,coords));}gesture=null;}});
  nav.addEventListener('pointercancel',()=>{gesture=null;});
  nav.addEventListener('dblclick',()=>apply([0,source.length-1]));
  nav.addEventListener('keydown',event=>{
    const handle=event.target.dataset.handle;if(source.length<2||!['start','end'].includes(handle)||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();const index=handle==='start'?0:1,min=index?selected[0]+1:0,max=index?source.length-1:selected[1]-1,step=event.shiftKey?Math.max(1,Math.round(source.length*.05)):1;
    const value=event.key==='Home'?min:event.key==='End'?max:Math.max(min,Math.min(max,selected[index]+(event.key==='ArrowRight'?step:-step)));
    apply(index?[selected[0],value]:[value,selected[1]]);
  });
  function cursor(event){const rect=chart.getBoundingClientRect();return (event.clientX-rect.left)/rect.width*context.width;}
  function hover(index,event){
    if(!context?.rows.length)return;chosen=Math.max(0,Math.min(context.rows.length-1,index));
    const p=context.rows[chosen],xx=context.x(p),description=context.describe(p);
    context.cross.setAttribute('x1',xx);context.cross.setAttribute('x2',xx);context.cross.setAttribute('opacity',.65);
    if(context.pointY){const yy=context.pointY(p);context.dot.setAttribute('opacity',Number.isFinite(yy)?1:0);context.dot.setAttribute('cx',xx);context.dot.setAttribute('cy',Number.isFinite(yy)?yy:0);}
    set('history-tooltip',`${pinned?'Đã ghim · ':''}${description.text}`);
    const card=$('chart-hover-card'),wasHidden=card.hidden;card.replaceChildren(node('strong','',description.title),...description.lines.map(([name,value,color])=>{const row=node('div');const label=node('span','',name),val=node('b','',value);if(color)val.style.color=color;row.append(label,val);return row;}),node('small','',pinned?'Bấm biểu đồ hoặc Esc để bỏ ghim':'Bấm để ghim · ← → xem điểm liền kề'));
    card.hidden=false;const holder=chart.parentElement,rect=chart.getBoundingClientRect(),box=holder.getBoundingClientRect(),cardWidth=Math.min(280,box.width-16);
    card.style.width=`${cardWidth}px`;card.style.left=`${Math.max(4,Math.min(box.width-cardWidth-4,(xx/context.width)*rect.width+(rect.left-box.left)+14))}px`;
    card.style.top=`${Math.max(4,Math.min(holder.clientHeight-card.offsetHeight-4,event?event.clientY-box.top+12:28))}px`;
    if(wasHidden)window.lopmChartMotion?.enter(card);
  }
  function attach(c,rows,x,describe,pointY){
    const pinnedAt=pinned&&context?.rows[chosen]?model.stamp(context.rows[chosen]):null;
    context={...c,rows,x,describe,pointY,cross:svg('line',{x1:0,x2:0,y1:c.top,y2:c.height-c.bottom,class:'chart-crosshair',opacity:0}),dot:svg('circle',{r:3.5,class:'chart-hover-dot',opacity:0})};
    c.chart.append(context.cross,context.dot);chosen=rows.length-1;$('chart-hover-card').hidden=!(pinnedAt!==null&&rows.length);
    context.xs=rows.map(x);remembered=null;
    if(pinnedAt!==null&&rows.length){chosen=model.nearest(rows.map(model.stamp),pinnedAt);requestAnimationFrame(()=>{if(pinned)hover(chosen);});}
  }
  chart.addEventListener('pointerdown',event=>{
    if(!context||source.length<2||event.button!==0)return;
    const xx=cursor(event);if(xx<context.left||xx>context.width-context.right)return;
    gesture={surface:'main',startX:xx,clientY:event.clientY,initial:[...selected],moved:false,kind:$('chart-pan').getAttribute('aria-pressed')==='true'?'move':'select'};
    chart.setPointerCapture(event.pointerId);
  });
  chart.addEventListener('pointermove',event=>{
    if(!context)return;
    const xx=Math.max(context.left,Math.min(context.width-context.right,cursor(event)));
    if(gesture?.surface==='main'){
      const g=gesture;if(Math.abs(xx-g.startX)<5&&!g.moved)return;g.moved=true;clearHover();
      if(g.kind==='move'){apply(shift(g.initial,(g.startX-xx)/context.innerWidth));return;}
      let brush=chart.querySelector('.chart-main-brush');if(!brush){brush=svg('rect',{class:'chart-main-brush',y:context.top,height:context.height-context.top-context.bottom});chart.append(brush);}
      brush.setAttribute('x',Math.min(xx,g.startX));brush.setAttribute('width',Math.abs(xx-g.startX));return;
    }
    if(!pinned)hover(model.nearest(context.xs,xx),event);
  });
  chart.addEventListener('pointerup',event=>{
    if(!context)return;const g=gesture;gesture=null;chart.querySelector('.chart-main-brush')?.remove();
    if(g?.surface==='main'&&g.moved){
      if(g.kind==='select'){
        const xx=cursor(event),visibleCoords=coords.slice(g.initial[0],g.initial[1]+1),first=visibleCoords[0],span=visibleCoords.at(-1)-first;
        const index=value=>model.nearest(coords,first+Math.max(0,Math.min(1,(value-context.left)/context.innerWidth))*span);
        apply([index(g.startX),index(xx)]);
      }return;
    }
    pinned=!pinned;hover(model.nearest(context.xs,cursor(event)),event);
  });
  chart.addEventListener('pointercancel',()=>{gesture=null;chart.querySelector('.chart-main-brush')?.remove();});
  chart.addEventListener('pointerleave',()=>{if(!pinned&&!gesture)clearHover();});
  chart.addEventListener('dblclick',()=>{clearHover();apply([0,source.length-1]);});
  chart.addEventListener('wheel',event=>{if(!event.ctrlKey||source.length<2||!context)return;event.preventDefault();apply(zoom(event.deltaY<0?.75:1.4,(cursor(event)-context.left)/context.innerWidth));},{passive:false});
  chart.addEventListener('keydown',event=>{
    if(event.key==='Escape'){if(pinned){event.preventDefault();event.stopPropagation();}clearHover();return;}
    if(event.key==='ArrowLeft'||event.key==='ArrowRight'){
      event.preventDefault();if(event.shiftKey)apply(shift(selected,(event.key==='ArrowRight'?1:-1)*Math.max(.1,1/Math.max(1,selected[1]-selected[0]))));
      else{pinned=true;hover(chosen+(event.key==='ArrowRight'?1:-1));}
    }else if(['+','=','-','Home'].includes(event.key)){event.preventDefault();apply(event.key==='Home'?[0,source.length-1]:zoom(event.key==='-'?1.5:.65));}
  });
  for(const id of ['chart-select','chart-pan'])$(id).addEventListener('click',()=>{for(const other of ['chart-select','chart-pan'])$(other).setAttribute('aria-pressed',String(id===other));chart.dataset.gesture=id==='chart-pan'?'pan':'select';});
  $('chart-zoom-in').addEventListener('click',()=>apply(zoom(.65)));
  $('chart-zoom-out').addEventListener('click',()=>apply(zoom(1.5)));
  $('chart-reset').addEventListener('click',()=>apply([0,source.length-1]));
  const dialog=$('chart-dialog'),navigatorPanel=$('chart-navigator-panel');
  function showSettings(show){
    if(window.lopmDisclosure)window.lopmDisclosure.setExpanded($('chart-settings'),show);else $('chart-settings').hidden=!show;
    $('chart-settings-toggle').textContent='Nâng cao';
    $('chart-settings-toggle').setAttribute('aria-expanded',String(show));
    $('chart-settings-toggle').setAttribute('aria-label',show?'Thu gọn tùy chọn nâng cao':'Mở tùy chọn nâng cao');
  }
  $('chart-settings-toggle').addEventListener('click',()=>{showSettings(window.lopmDisclosure?!window.lopmDisclosure.isExpanded($('chart-settings')):$('chart-settings').hidden);schedule();});
  document.addEventListener('lopm:disclosure-settled',event=>{if(event.detail?.id==='chart-settings')schedule();});
  function closeExpanded(){if(!expanded)return;dialog.close();}
  dialog.addEventListener('close',()=>{
    if(!expanded)return;expanded=false;navigatorPanel.hidden=true;restore.marker.replaceWith(panel);document.body.style.overflow=restore.overflow;
    $('chart-expand').textContent='⛶ Mở rộng';$('chart-expand').setAttribute('aria-expanded','false');panel.classList.remove('chart-expanded');
    window.scrollTo({top:restore.scroll,behavior:'instant'});$('chart-expand').focus({preventScroll:true});clearHover();schedule();
  });
  $('chart-expand').addEventListener('click',()=>{
    if(expanded){closeExpanded();return;}const marker=document.createComment('chart-home');panel.before(marker);restore={marker,scroll:window.scrollY,overflow:document.body.style.overflow};
    expanded=true;dialog.append(panel);navigatorPanel.hidden=false;panel.classList.add('chart-expanded');document.body.style.overflow='hidden';
    $('chart-expand').textContent='✕ Thu nhỏ';$('chart-expand').setAttribute('aria-expanded','true');dialog.showModal();dialog.scrollTop=0;window.lopmChartMotion?.enter(dialog,'dialog');clearHover();schedule();
  });
  window.addEventListener('hashchange',()=>{if(expanded)closeExpanded();});
  const observer=new ResizeObserver(entries=>{const width=Math.round(entries[0].contentRect.width),height=Math.round(entries[0].contentRect.height),key=`${width}|${height}`;if(remembered!==key&&width>0){remembered=key;schedule();}});observer.observe(chart);
  window.lopmChartViewport={prepare,attach,pending,trailing,idle:()=>{clearHover();context=null;},isInteracting:()=>!!gesture,bounds:()=>[...selected],reset:()=>apply([0,source.length-1])};
  navigatorPanel.hidden=true;showSettings(false);pending();
})();
