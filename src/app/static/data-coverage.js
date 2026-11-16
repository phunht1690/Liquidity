"use strict";
(() => {
  const key='lopm-data-universe-v1',allowed=['VN30','VN100','HOSE','HNX','UPCOM'];
  const select=document.getElementById('data-universe-select');
  let universe='VN30',payload=null,controller=null,version=0,lastAttempt=null,lastSuccess=0,connected=false;
  try{const saved=localStorage.getItem(key);if(allowed.includes(saved))universe=saved;}catch{}
  const put=(id,text)=>{const el=document.getElementById(id);if(el)el.textContent=String(text);};
  const visible=()=>document.body.dataset.view==='methods'&&document.body.dataset.dataView==='status'&&!document.hidden;
  function paint(){
    const status=document.getElementById('data-source-status');
    status.dataset.connection=connected&&payload?.data_status?.stream_connected===true?'connected':'cached';
    put('data-auto-update',connected?'Tự cập nhật':payload?'Tự thử lại':'Đang nhận dữ liệu');
    const a=payload?.analysis;
    put('data-source-time',payload?`${a?.mode==='live'?'Sổ trong phiên':'Ảnh sổ'} ${dateTime(a?.asof)} · Bản ghi ${dateTime(payload.updated_at)}`:'Đang đọc dữ liệu SSI trong phạm vi đã chọn.');
    status.title=lastSuccess?`Đồng bộ với ứng dụng lúc ${dateTime(new Date(lastSuccess).toISOString())}.`:'Ứng dụng tự nhận bản mới và tự thử lại.';
    if(payload&&!connected){put('data-connection','Đang nối lại ứng dụng');put('data-view-mode','Đang giữ bản đã nhận');}
  }
  function options(data){
    syncSelect('data-universe-select',data.available_universes.map(u=>[u.id,`${u.label||u.id} · ${u.count} mã`]),universe);
  }
  async function refresh(force=false){
    if(!visible()||controller||!force&&lastAttempt!==null&&Date.now()-lastAttempt<5000)return;
    const request=new AbortController(),identity=++version,scope=universe;
    controller=request;lastAttempt=Date.now();
    const timeout=setTimeout(()=>request.abort(),12000);
    try{
      const response=await fetch(`/api/data-coverage?${new URLSearchParams({universe:scope})}`,{signal:request.signal,cache:'no-store'});
      const data=await response.json();
      if(identity!==version)return;
      if(!response.ok||response.status!==200||data.mode!=='data_coverage'||data.source!=='ssi_fastconnect'||data.universe!==scope||data.group!=='all')throw Error('coverage_unavailable');
      payload=data;connected=true;lastSuccess=Date.now();options(data);window.lopmDataView.render(data);paint();
    }catch{
      if(identity!==version)return;
      connected=false;paint();
    }finally{clearTimeout(timeout);if(controller===request)controller=null;}
  }
  function activate(){
    if(visible()){
      if(payload){options(payload);window.lopmDataView.render(payload);}else window.lopmDataView.render(null);
      paint();refresh(true);
    }else if(controller){version++;controller.abort();controller=null;}
  }
  select.addEventListener('change',()=>{
    const next=select.value;if(next===universe||!allowed.includes(next))return;
    universe=next;version++;controller?.abort();controller=null;payload=null;connected=false;lastSuccess=0;lastAttempt=null;
    try{localStorage.setItem(key,universe);}catch{}
    window.lopmDataView.render(null);paint();refresh(true);
  });
  setInterval(()=>refresh(),5000);
  window.lopmDataCoverage={activate,refresh};
})();
