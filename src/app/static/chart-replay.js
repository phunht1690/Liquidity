"use strict";
// Historical candles and recorded replay never assign to live quote/book state.
(() => {
  const engine=window.lopmChartEngine;
  const viewport=window.lopmChartViewport;
  let mode='current',archive=null,position=0,timer=null,loading=false,request=null,sequence=0;
  let history=null,historyKey='',historyRequest=null,historySequence=0,historyTimer=null,historyLoading=false;
  let liquidityArchive=null,liquidityKey='',liquidityRequest=null,liquiditySequence=0,liquidityLoading=false;
  const checked=id=>$(id).checked,type=()=>$('chart-type').value,priceMode=()=>$('chart-metric').value==='price';
  function compactStamp(value){
    const stamp=new Date(value||'');
    return Number.isFinite(stamp.getTime())?new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(stamp):'_';
  }
  function chartInfo(summary='',fields=[],note=''){
    set('chart-data-status',summary);$('chart-data-status').title=note;
    $('chart-source-fields').replaceChildren(...fields.map(([label,value])=>{const row=node('div');row.append(node('dt','',label),node('dd','',value||'_'));return row;}));
    set('chart-source-note',note);
  }
  function pause(){clearInterval(timer);timer=null;$('cache-play').textContent='Phát';$('cache-play').setAttribute('aria-pressed','false');$('cache-observation').setAttribute('aria-live','polite');$('telemetry-panel').classList.remove('is-playing');}
  function stopHistory(){clearTimeout(historyTimer);historyTimer=null;historyRequest?.abort();historyRequest=null;historySequence++;historyLoading=false;}
  function controls(){
    const price=priceMode(),replay=mode==='cache';
    $('chart-type-control').hidden=!price;$('chart-range-control').hidden=!price||replay;$('chart-timeframe-control').hidden=!price||replay;
    $('snapshot-window-control').hidden=price||replay;$('chart-custom-range').hidden=!price||replay||$('chart-range').value!=='custom';
    $('liquidity-day-control').hidden=price||replay;set('chart-title',price?'Diễn biến giá':'Chênh giá & lượng chờ');
    $('price-series-options').hidden=!price;$('liquidity-series-options').hidden=price;
    $('ma20-control').hidden=replay;$('ma50-control').hidden=replay;$('chart-type').querySelector('option[value=candles]').disabled=replay;
  }
  function settings(bars,prepared=null){
    const rows=prepared||(bars?history?.bars||[]:mode==='cache'?archive?.points||[]:state?.history||[]);
    $('chart-ma20').disabled=!bars||rows.length<20;$('chart-ma50').disabled=!bars||rows.length<50;
    const unit=[...$('chart-timeframe').options].find(o=>o.value===$('chart-timeframe').value)?.textContent||'';
    for(const period of [20,50]){
      const hint=`Trung bình giá đóng của ${period} nến; mỗi nến ${unit}.`+(!bars?' Chỉ dùng trên nến SSI.':rows.length<period?` Cần ít nhất ${period} nến; đang có ${rows.length}.`:'');
      $(`chart-ma${period}`).title=hint;$(`ma${period}-control`).title=hint;
    }
    $('chart-reference').disabled=!rows.some(p=>valid(p.reference_price_vnd));
    $('chart-average').disabled=!rows.some(p=>valid(p.avg_match_price_vnd)&&p.avg_match_price_vnd>0);
    $('chart-average').title='Giá bình quân khớp của phiên do SSI gửi; chỉ vẽ các mốc đã ghi, không tính lại từ nến.';
    return {bars,type:!bars&&type()==='candles'?'line':type(),volume:checked('chart-volume'),average:checked('chart-average')&&!$('chart-average').disabled,reference:checked('chart-reference')&&!$('chart-reference').disabled,
      ma20:bars&&checked('chart-ma20')&&rows.length>=20,ma50:bars&&checked('chart-ma50')&&rows.length>=50,timeframe:$('chart-timeframe').value,spread:checked('chart-spread'),depth:checked('chart-depth'),bid:checked('chart-bid-depth'),ask:checked('chart-ask-depth')};
  }
  function animatePlot(symbol,sourceKey){
    const key=[sourceKey,type(),...['chart-volume','chart-reference','chart-average','chart-ma20','chart-ma50','chart-spread','chart-depth','chart-bid-depth','chart-ask-depth'].map(id=>checked(id))].join('|');
    window.lopmChartMotion?.present($('history-chart'),key,{replay:mode==='cache',interacting:viewport.isInteracting()});
  }
  function snapshotKey(symbol,points){return [mode,$('chart-metric').value,symbol,mode==='cache'?archive?.day:$('liquidity-day').value,points[0]?.trading_date||(points[0]?.received_at||points[0]?.timestamp||'').slice(0,10)].join('|');}
  function plotSnapshots(points,symbol,allPoints=points){
    const view=viewport.prepare(allPoints,{key:snapshotKey(symbol,allPoints),metric:priceMode()?'price':'liquidity',onChange:redraw});
    const end=points.length-1,visible=allPoints.slice(view.bounds[0],Math.min(end,view.bounds[1])+1),opts={...settings(false),symbol,allPoints:view.points};
    if(priceMode())engine.price(visible,opts);else engine.liquidity(visible,opts);
    window.lopmWidgets?.chartIdentity(points,symbol,null);animatePlot(symbol,snapshotKey(symbol,allPoints));
  }
  function plotHistory(){
    if(!history)return;
    const points=engine.sessionAverage(history.bars||[],state?.history||[],history.timeframe,state?.updated_at),symbol=history.symbol,unit=[...$('chart-timeframe').options].find(o=>o.value===history.timeframe)?.textContent||history.timeframe;
    const dayLabel=value=>new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(value));
    const rangeLabel=history.range==='custom'?'Khoảng tùy chọn':[...$('chart-range').options].find(o=>o.value===history.range)?.textContent||history.range;
    const selected=state?.selected.symbol===symbol?state.selected:null;
    const view=viewport.prepare(points,{key:['history',symbol,history.range,history.timeframe,history.requested_from,history.requested_to].join('|'),bars:true,metric:'price',onChange:redraw});
    engine.price(view.points,{...settings(true,points),symbol,timeframe:history.timeframe,masterPoints:points});window.lopmWidgets?.chartIdentity(points,symbol,selected?.change_percent,selected?.price_asof_date||selected?.trading_date);animatePlot(symbol,['history',symbol,history.range,history.timeframe,history.requested_from,history.requested_to].join('|'));
    set('chart-mode-badge',history.local_archive?'SSI · Kho nến':'SSI · Nến giá');
    set('history-caption',`${rangeLabel} · ${unit}/nến · ${points.length} nến`);
    const from=points[0]?.timestamp,to=points.at(-1)?.timestamp;
    const periodTime=history.timeframe==='1d'?dayLabel:dateTime;
    chartInfo(points.length?`${history.refreshing?'Đang đồng bộ · lần trước':'Đồng bộ'} ${compactStamp(history.updated_at)}${history.complete_range===false?' · Một phần khoảng chọn':''}`:'_',[
      ['Nguồn',history.local_archive?'Nến SSI đã lưu trên máy':'API nến SSI'],
      ['Khoảng đã tải',points.length?`${periodTime(from)} → ${periodTime(to)}`:'_'],
      ['Nến cuối',to?periodTime(to):'_'],['Lần đồng bộ',dateTime(history.updated_at)],
      ['BQ phiên SSI',`${points.filter(p=>valid(p.avg_match_price_vnd)).length}/${points.length} nến có mốc đã ghi`]
    ],history.complete_range===false?'Mới có một phần nến trong khoảng chọn; các khoảng thiếu được giữ trống.':'Giá và khối lượng từng nến do SSI cung cấp. BQ phiên chỉ vẽ tại các mốc đã thu; khoảng thiếu mẫu được giữ trống.');
  }
  function historyParams(){
    if(!state)return null;
    const query={symbol:state.selected.symbol,range:$('chart-range').value,timeframe:$('chart-timeframe').value};
    if(query.range==='custom'){
      query.from=$('chart-from').value;query.to=$('chart-to').value;
      if(!query.from||!query.to||query.from>query.to){set('chart-range-note','Chọn ngày bắt đầu không sau ngày kết thúc.');return null;}
      if((Date.parse(query.to)-Date.parse(query.from))/86400000+1>366){set('chart-range-note','Chọn khoảng tối đa một năm.');return null;}
      if(query.to>$('chart-to').max){set('chart-range-note','Không chọn ngày trong tương lai.');return null;}
    }
    set('chart-range-note','');return query;
  }
  function refreshLater(delay=30000){clearTimeout(historyTimer);if(mode==='current'&&priceMode()&&!document.hidden&&currentView()==='overview')historyTimer=setTimeout(()=>loadHistory(true),delay);}
  async function loadHistory(passive=false){
    if(mode!=='current'||!priceMode())return;
    const query=historyParams();if(!query)return;
    historyRequest?.abort();const active=new AbortController(),version=++historySequence;
    historyRequest=active;historyLoading=true;historyKey=JSON.stringify(query);
    if(!passive||!history){history=null;viewport.pending();drawEmpty('history-chart');set('history-caption','Đang đọc nến SSI…');chartInfo('Đang đọc dữ liệu');}
    const timeout=setTimeout(()=>active.abort(),15000);
    try{
      const response=await fetch(`/api/price-history?${new URLSearchParams(query)}`,{cache:'no-store',signal:active.signal}),data=await response.json();
      if(version!==historySequence||mode!=='current'||!priceMode()||state?.selected.symbol!==query.symbol)return;
      if(!response.ok||data.source!=='ssi_fastconnect_ohlc'||data.symbol!==query.symbol)throw new Error('history_unavailable');
      history=data;plotHistory();refreshLater(data.refreshing?2000:30000);
    }catch(error){
      if(version!==historySequence||mode!=='current'||!priceMode())return;
      if(history)plotHistory();else{
        plotSnapshots(state?.history||[],query.symbol);set('chart-mode-badge','SSI · Bản đã thu');set('history-caption','Các lần nhận giá của phiên gần nhất');
        chartInfo('Giá đã thu trên máy',[['Nguồn','Bản tin giao dịch SSI đã lưu']],
          'Chưa có nến SSI cho khoảng yêu cầu. Đang dùng đường giá từ các lần đã nhận, không ghép thành nến.');
      }
      refreshLater(60000);
    }finally{clearTimeout(timeout);if(version===historySequence){historyLoading=false;historyRequest=null;}}
  }
  function stopLiquidity(){liquidityRequest?.abort();liquidityRequest=null;liquiditySequence++;liquidityLoading=false;}
  function syncLiquidityDays(payload){
    const select=$('liquidity-day'),chosen=select.value,days=[...(payload.data_status?.days||[])].reverse();
    const options=[['auto','Phiên gần nhất có sổ'],...days.map(d=>[d.day,d.day.split('-').reverse().join('/')])],key=JSON.stringify(options);
    if(select.dataset.options!==key){select.replaceChildren(...options.map(([v,t])=>option(v,t)));select.dataset.options=key;select.value=options.some(([v])=>v===chosen)?chosen:'auto';}
  }
  function plotLiquidity(payload){
    const explicit=$('liquidity-day').value!=='auto',live=!explicit&&payload.analysis.mode==='live';
    const points=live?payload.history||[]:liquidityArchive?.points||[],symbol=payload.selected.symbol;
    plotSnapshots(points,symbol);set('chart-mode-badge',live?'SSI · Đang theo dõi':'SSI · Phiên sổ đã lưu');
    const day=live?(payload.analysis.asof||'').slice(0,10):liquidityArchive?.day;
    set('history-caption',`${points.filter(p=>p.valid).length} bản sổ hợp lệ`);
    const last=points.filter(p=>p.valid).at(-1);
    chartInfo(last?`Sổ cuối ${compactStamp(last.received_at||last.timestamp)}`:'_',[
      ['Nguồn',live?'Báo giá SSI trong phiên':'Sổ SSI đã lưu'],['Phiên',day?day.split('-').reverse().join('/'):'_'],
      ['Bản sổ hợp lệ',`${points.filter(p=>p.valid).length}/${points.length}`],['Đơn vị','Chênh giá: bps · Giá trị chờ: tỷ đồng']
    ],'Lượng chờ cộng từ các mức SSI đã cấp, chưa phải giao dịch đã khớp. Đường ngắt khi sổ không hợp lệ hoặc thiếu mẫu. Chọn phiên chỉ đổi biểu đồ.');
  }
  async function loadLiquidity(payload){
    syncLiquidityDays(payload);
    const explicit=$('liquidity-day').value,day=explicit==='auto'?(payload.analysis.asof||'').slice(0,10):explicit;
    if(explicit==='auto'&&payload.analysis.mode==='live'){stopLiquidity();liquidityKey='';plotLiquidity(payload);return;}
    const query={symbol:payload.selected.symbol,universe:payload.universe,...(day?{day}:{})},key=JSON.stringify(query);
    if(key===liquidityKey&&(liquidityArchive||liquidityLoading)){if(liquidityArchive)plotLiquidity(payload);return;}
    stopLiquidity();liquidityKey=key;liquidityArchive=null;liquidityLoading=true;const version=++liquiditySequence,active=new AbortController();liquidityRequest=active;
    viewport.pending();drawEmpty('history-chart');set('history-caption','Đang đọc phiên sổ đã lưu…');chartInfo('Đang đọc dữ liệu');
    const timeout=setTimeout(()=>active.abort(),15000);
    try{
      const response=await fetch(`/api/chart-cache?${new URLSearchParams(query)}`,{cache:'no-store',signal:active.signal}),data=await response.json();
      if(version!==liquiditySequence||mode!=='current'||priceMode()||state?.selected.symbol!==query.symbol)return;
      if(!response.ok||data.source!=='ssi_fastconnect')throw new Error('liquidity_unavailable');
      liquidityArchive=data;plotLiquidity(state);if($('window-select').value!=='1440')viewport.trailing($('window-select').value);
    }catch(error){if(version!==liquiditySequence||mode!=='current'||priceMode())return;liquidityKey='';viewport.pending('Chưa đọc được phiên này.');drawEmpty('history-chart');chartInfo('_',[],'Chưa có chuỗi sổ cho lựa chọn này. Chọn một phiên khác; bảng giá và sổ bên ngoài vẫn giữ dữ liệu mới nhất.');}
    finally{clearTimeout(timeout);if(version===liquiditySequence){liquidityLoading=false;liquidityRequest=null;}}
  }
  function renderLive(payload){
    if(mode==='cache')return;controls();
    if(!payload){stopHistory();stopLiquidity();history=null;historyKey='';liquidityKey='';liquidityArchive=null;viewport.pending('Chưa có dữ liệu cho mã này.');drawEmpty('history-chart');chartInfo();window.lopmWidgets?.chartIdentity([],params?.symbol||'',null);return;}
    if(!priceMode()){
      stopHistory();loadLiquidity(payload);return;
    }
    const query=historyParams();if(!query)return;
    if(JSON.stringify(query)!==historyKey){stopHistory();history=null;loadHistory();}
    else if(history)plotHistory();else if(!historyLoading&&!historyTimer)loadHistory();
  }
  function renderFrames(){
    if(mode!=='cache'||!archive||loading)return;
    const points=archive.points||[],count=points.length;
    if(!count){drawEmpty('history-chart');set('cache-counter','_');set('cache-observation','_');set('history-caption','Phát lại');chartInfo('_',[],'Chưa có chuỗi đã lưu cho lựa chọn này.');return;}
    viewport.prepare(points,{key:snapshotKey(archive.symbol,points),metric:priceMode()?'price':'liquidity',onChange:redraw});
    const [start,end]=viewport.bounds();$('cache-position').min=start;$('cache-position').max=end;position=Math.min(Math.max(start,position),end);const point=points[position];plotSnapshots(points.slice(0,position+1),archive.symbol,points);
    $('cache-position').value=position;$('cache-position').setAttribute('aria-valuetext',`Bản ${position+1} trên ${count}, nhận lúc ${dateTime(point.received_at)}`);
    set('cache-counter',`${position+1} / ${count} bản`);set('cache-observation',`${archive.symbol} · ${dateTime(point.received_at)} · Giá ${fmt(point.last_price_vnd,0)} đ · Tổng KL ${fmt(point.volume_shares,0)} CP`);
    set('history-caption',`Phát lại · ${archive.universes?.find(u=>u.id===archive.universe)?.label||archive.universe}`);
    const available=priceMode()?archive.summary?.price_observations:archive.summary?.liquidity_observations;
    const selectedDay=archive.day.split('-').reverse().join('/');
    chartInfo(available===0?'_':`Bản đã thu ${compactStamp(point.received_at)}`,[
      ['Nguồn','Kho bản tin SSI đã thu'],['Phiên phát lại',selectedDay],['Bản đang xem',`${position+1}/${count}`],
      ['Giá có dữ liệu',fmt(archive.summary?.price_observations,0)],['Sổ hợp lệ',fmt(archive.summary?.liquidity_observations,0)]
    ],available===0?`Phiên ${selectedDay} chưa có ${priceMode()?'giá giao dịch':'sổ lệnh hợp lệ'} đã thu để phát lại.`:
      'Chỉ biểu đồ phát lại; bảng giá và sổ bên ngoài giữ dữ liệu riêng. Kho có thể chỉ gồm một phần phiên; các khoảng thiếu mẫu được giữ trống.');
    $('cache-start').disabled=position===start;
    $('cache-back').disabled=position===start;$('cache-next').disabled=position===end;
  }
  function setOptions(id,options,value){$(id).replaceChildren(...options.map(([v,t])=>option(v,t)));if(value)$(id).value=value;}
  async function loadArchive(query={}){
    pause();request?.abort();const active=new AbortController();request=active;const version=++sequence;loading=true;archive=null;
    $('cache-controls').querySelectorAll('button,select,input').forEach(el=>el.disabled=true);viewport.pending();drawEmpty('history-chart');set('history-caption','Đang đọc các lần đã lưu…');chartInfo('Đang đọc kho đã lưu');
    const timeout=setTimeout(()=>active.abort(),15000);
    try{
      const response=await fetch(`/api/chart-cache?${new URLSearchParams(query)}`,{cache:'no-store',signal:active.signal}),data=await response.json();
      if(!response.ok)throw new Error('archive_unavailable');if(version!==sequence||mode!=='cache')return;
      archive=data;position=Math.max(0,data.points.findIndex(p=>p.price_available));setOptions('cache-day',(data.days||[]).map(d=>[d.day,`${d.day.split('-').reverse().join('/')} · ${d.snapshots} bản`]),data.day);
      setOptions('cache-universe',(data.universes||[]).map(u=>[u.id,`${u.label||u.id} · ${u.count} mã`]),data.universe);setOptions('cache-symbol',(data.symbols||[]).map(s=>[s,s]),data.symbol);
      const count=data.points.length;$('cache-position').max=Math.max(0,count-1);$('cache-controls').querySelectorAll('button,select,input').forEach(el=>el.disabled=!count);
      $('cache-reload').disabled=false;$('cache-day').disabled=!data.days?.length;$('cache-play').disabled=count<2;$('cache-position').disabled=count<2;loading=false;renderFrames();
    }catch(error){
      if(version!==sequence||mode!=='cache')return;
      drawEmpty('history-chart');chartInfo('_',[],'Chưa đọc được dữ liệu cho lựa chọn này. Có thể chọn ngày hoặc mã khác.');
      for(const id of ['cache-day','cache-universe','cache-symbol'])$(id).disabled=!$(id).options.length;
      $('cache-reload').disabled=false;
    }
    finally{clearTimeout(timeout);if(version===sequence)loading=false;}
  }
  function switchMode(next){
    pause();stopHistory();stopLiquidity();mode=next;request?.abort();sequence++;$('chart-current').setAttribute('aria-pressed',String(mode==='current'));$('chart-cache').setAttribute('aria-pressed',String(mode==='cache'));
    $('cache-controls').hidden=mode!=='cache';$('telemetry-panel').classList.toggle('archive-mode',mode==='cache');controls();
    if(mode==='cache'){set('chart-mode-badge','Phát lại · riêng biểu đồ');if(type()==='candles')$('chart-type').value='line';if(archive){loading=false;renderFrames();}else loadArchive(state?{universe:state.universe,symbol:state.selected.symbol}:{});}
    else{loading=false;historyKey='';renderLive(state);}
  }
  function step(delta){pause();if(!archive)return;const [start,end]=viewport.bounds();position=Math.max(start,Math.min(end,position+delta));renderFrames();}
  function play(){
    if(timer!==null){pause();return;}if(!archive||loading||archive.points.length<2)return;const [start,end]=viewport.bounds();if(position>=end)position=start;
    $('cache-play').textContent='Tạm dừng';$('cache-play').setAttribute('aria-pressed','true');$('cache-observation').setAttribute('aria-live','off');$('telemetry-panel').classList.add('is-playing');
    renderFrames();timer=setInterval(()=>{position++;renderFrames();if(position>=viewport.bounds()[1])pause();},1000/Number($('cache-speed').value));
  }
  function compatibleTimeframes(){
    const range=$('chart-range').value,days=range==='custom'?Math.max(1,(Date.parse($('chart-to').value)-Date.parse($('chart-from').value))/86400000+1):({session:1,'1w':7,'1mo':31,'3mo':93,'1y':366}[range]||1);
    const max={'1m':7,'5m':35,'15m':100,'30m':200,'1h':366,'1d':366};[...$('chart-timeframe').options].forEach(o=>o.disabled=days>max[o.value]);
    if($('chart-timeframe').selectedOptions[0]?.disabled)$('chart-timeframe').value=[...$('chart-timeframe').options].find(o=>!o.disabled)?.value||'1d';
  }
  function rangeChanged(){
    $('chart-timeframe').value=({'15m':'1m','30m':'1m','1h':'1m','2h':'1m','4h':'5m',session:'5m','1w':'15m','1mo':'1h','3mo':'1d','1y':'1d',custom:'1d'})[$('chart-range').value];
    compatibleTimeframes();controls();historyKey='';renderLive(state);
  }
  function redraw(){controls();if(mode==='cache')renderFrames();else if(priceMode()&&history)plotHistory();else renderLive(state);}
  $('chart-current').addEventListener('click',()=>switchMode('current'));$('chart-cache').addEventListener('click',()=>switchMode('cache'));
  $('chart-metric').addEventListener('change',()=>{stopHistory();stopLiquidity();historyKey='';controls();mode==='cache'?renderFrames():renderLive(state);});
  for(const id of ['chart-type','chart-volume','chart-reference','chart-average','chart-ma20','chart-ma50','chart-spread','chart-depth','chart-bid-depth','chart-ask-depth'])$(id).addEventListener('change',redraw);
  $('liquidity-day').addEventListener('change',()=>{liquidityKey='';renderLive(state);});
  $('window-select').addEventListener('change',()=>viewport.trailing($('window-select').value));
  $('chart-range').addEventListener('change',rangeChanged);$('chart-timeframe').addEventListener('change',()=>{historyKey='';renderLive(state);});$('chart-apply-range').addEventListener('click',()=>{compatibleTimeframes();historyKey='';renderLive(state);});
  const replaySelection=()=>({day:$('cache-day').value,universe:$('cache-universe').value,symbol:$('cache-symbol').value});
  $('cache-day').addEventListener('change',()=>loadArchive({day:$('cache-day').value}));$('cache-universe').addEventListener('change',()=>loadArchive({day:$('cache-day').value,universe:$('cache-universe').value}));$('cache-symbol').addEventListener('change',()=>loadArchive(replaySelection()));
  $('cache-reload').addEventListener('click',()=>loadArchive(replaySelection()));$('cache-play').addEventListener('click',play);$('cache-start').addEventListener('click',()=>{pause();position=viewport.bounds()[0];renderFrames();});$('cache-back').addEventListener('click',()=>step(-1));$('cache-next').addEventListener('click',()=>step(1));
  $('cache-position').addEventListener('input',()=>{pause();position=Number($('cache-position').value);renderFrames();});$('cache-speed').addEventListener('change',()=>{if(timer!==null){pause();play();}});
  const dayFormat=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh'}),today=dayFormat.format(new Date());
  $('chart-from').value=dayFormat.format(new Date(Date.now()-31*86400000));$('chart-to').value=today;$('chart-from').max=today;$('chart-to').max=today;
  document.addEventListener('visibilitychange',()=>{if(document.hidden){pause();clearTimeout(historyTimer);historyTimer=null;}else if(mode==='current'&&priceMode())refreshLater(1000);});
  window.addEventListener('hashchange',()=>{if(currentView()!=='overview'){pause();clearTimeout(historyTimer);historyTimer=null;}else if(mode==='current'&&priceMode())refreshLater(1000);});
  window.lopmChart={isReplay:()=>mode==='cache',render:payload=>mode==='cache'?renderFrames():renderLive(payload)};controls();renderLive(state);
})();
