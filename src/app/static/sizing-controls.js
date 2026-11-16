"use strict";
(() => {
  const byId=id=>document.getElementById(id),root=byId('sizing-controls');
  const slider=byId('notional-slider'),amount=byId('notional-amount');
  const presets=[...root.querySelectorAll('[data-notional]')];
  let change=null,current=1_000_000_000,view='overview';
  const label=value=>value>=1e9?`${(value/1e9).toLocaleString('vi-VN',{maximumFractionDigits:3})} tỷ đồng`:`${(value/1e6).toLocaleString('vi-VN',{maximumFractionDigits:0})} triệu đồng`;
  function showAmount(value){
    current=value;slider.value=String(value);
    if(document.activeElement!==amount)amount.value=String(value/1e6);
    byId('notional-output').textContent=label(value);
    slider.setAttribute('aria-valuetext',label(value));
    for(const button of presets)button.setAttribute('aria-pressed',String(Number(button.dataset.notional)===value));
  }
  function submit(value){
    if(!window.lopmSizingModel.inRange(value))return;
    amount.removeAttribute('aria-invalid');byId('sizing-validation').hidden=true;showAmount(value);
    change?.(value);
  }
  slider.addEventListener('input',()=>submit(Number(slider.value)));
  amount.addEventListener('input',()=>{
    const value=Number(amount.value)*1e6;
    if(amount.value!==''&&Number.isInteger(value/1e6)&&window.lopmSizingModel.inRange(value))submit(value);
    else{amount.setAttribute('aria-invalid','true');byId('sizing-validation').hidden=false;}
  });
  amount.addEventListener('blur',()=>{amount.value=String(current/1e6);amount.removeAttribute('aria-invalid');byId('sizing-validation').hidden=true;});
  for(const button of presets)button.addEventListener('click',()=>submit(Number(button.dataset.notional)));
  function mount(nextView){
    view=nextView;
    const slot=byId(view==='alerts'?'alerts-sizing-slot':'book-sizing-slot');
    if(root.parentElement!==slot)slot.append(root);
  }
  function sync(payload){
    if(payload)showAmount(payload.notional_vnd);
    const row=payload?.selected;
    const usable=r=>r?.valid&&typeof r.sizing_price_vnd==='number'&&r.sizing_price_vnd>0;
    const enabled=!!payload&&(view==='alerts'?payload.ranking.some(usable):usable(row));
    slider.disabled=amount.disabled=!enabled;for(const button of presets)button.disabled=!enabled;
    byId('sizing-context').textContent=!payload?'Đang tải sổ lệnh để tính.':view==='alerts'?`Áp dụng cho ${payload.ranking.length} mã trong phạm vi và ngành đã chọn.`:`${row.symbol} · ${row.analysis_mode==='live'?'Sổ trong phiên':'Ảnh sổ đã lưu'} · ${row.analysis_at?dateTime(row.analysis_at):'chưa có sổ đủ dữ liệu'}`;
    const shares=row?.buy?.requested_shares;
    byId('sizing-shares').textContent=view==='alerts'?'Mỗi mã được quy đổi theo giá và lô riêng.':enabled&&Number.isFinite(shares)?`${shares.toLocaleString('vi-VN')} cổ phiếu ${row.symbol} · làm tròn theo lô ${row.lot_size.toLocaleString('vi-VN')}.`:'Chưa có sổ đủ dữ liệu để quy đổi.';
    byId('sizing-status').textContent=!enabled?'Chờ sổ đủ dữ liệu':payload.sizing_preview?'Đã tính theo số tiền vừa chọn':'Tự cập nhật khi thay đổi số tiền';
    root.dataset.preview=String(!!payload?.sizing_preview);
    byId('sizing-current-amount').textContent=label(current);
  }
  window.lopmSizingControls={mount,sync,onChange(callback){change=callback;}};
})();
