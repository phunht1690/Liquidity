"use strict";
(() => {
  function symbolsForGroup(symbols,group='all'){
    return (symbols||[]).filter(row=>group==='all'||row.group===group);
  }
  function selectedSymbol(symbols,group,preferred){
    const eligible=symbolsForGroup(symbols,group);
    return eligible.some(row=>row.symbol===preferred)?preferred:eligible[0]?.symbol||null;
  }
  function connection(payload,backendOK){
    if(!backendOK)return {mode:'reconnecting',label:'Đang nối lại cập nhật tự động',automatic:'Tự động thử lại'};
    if(payload?.analysis?.mode==='live')return {mode:'live',label:'Đang cập nhật SSI',automatic:'Tự cập nhật'};
    if(payload?.analysis?.mode==='saved')return {mode:'saved',label:payload.phase_code==='closed'?'Dữ liệu phiên gần nhất':'Dữ liệu SSI đã lưu',automatic:'Tự cập nhật'};
    return {mode:'waiting',label:'Đang chờ dữ liệu SSI',automatic:'Tự cập nhật'};
  }
  window.lopmDashboardModel={symbolsForGroup,selectedSymbol,connection};
})();
