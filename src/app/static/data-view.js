"use strict";
(() => {
  const finite=v=>typeof v==='number'&&Number.isFinite(v);
  function model(payload){
    const coverage=payload.coverage||{},data=payload.data_status||{};
    const scope=coverage.scope||{symbols:coverage.visible_count,received_prices:null,received_books:null,valid_books:coverage.valid_book_count};
    const collector=coverage.collector||{symbols:coverage.collected_count,received_prices:coverage.received_prices,received_books:coverage.received_books};
    const days=(data.days||[]).filter(d=>/^\d{4}-\d{2}-\d{2}$/.test(d.day)&&finite(d.snapshots)&&d.snapshots>=0);
    return {scope,collector,days,snapshots:finite(data.snapshots)?data.snapshots:null,
      connection:data.stream_connected===true?'Đã kết nối nguồn SSI':data.stream_connected===false?'Chưa kết nối nguồn SSI':'Chưa có trạng thái kết nối',
      mode:payload.analysis?.mode==='live'?'Đang tính từ sổ trong phiên':payload.analysis?.mode==='saved'?'Đang dùng ảnh sổ đã lưu':'Chưa có sổ đủ dữ liệu để tính'};
  }
  function render(payload){
    if(!payload){
      for(const id of ['data-prices','data-books','data-valid-books'])set(id,'_');
      set('data-scope-caption','Đang tải dữ liệu để đối chiếu.');set('data-connection','Đang kiểm tra kết nối');set('data-view-mode','Đang tải dữ liệu');
      set('data-storage-summary','Đang đọc kho ảnh dữ liệu đã lưu.');
      set('data-backfill-status','Đang kiểm tra');set('data-backfill-summary','Đang đọc lịch sử giá đã lưu.');
      set('data-backfill-note','');
      set('data-expansion-note','');set('data-storage-policy','');set('data-volume-caption','');
      $('data-backfill-details').replaceChildren();$('data-backfill-progress').hidden=true;
      $('data-coverage-note').hidden=true;$('data-status-list').replaceChildren();$('data-view-details').replaceChildren();$('data-history-body').replaceChildren();return;
    }
    const view=model(payload),{scope,collector}=view,d=payload.data_status;
    const b=d.price_backfill||{},a=b.archive||{},background=d.background||{};
    const sync=backfillModel(b);
    set('data-backfill-status',sync.label);
    set('data-backfill-summary',finite(a.bars)?a.bars>0?`${fmt(a.bars,0)} nến đã lưu cho ${fmt(a.symbols,0)} mã.`:'Kho chưa có nến đã lưu.':'Chưa có thông tin kho nến.');
    set('data-backfill-note',sync.note);
    const day=value=>/^\d{4}-\d{2}-\d{2}$/.test(value||'')?value.split('-').reverse().join('/'):'_';
    fillList('data-backfill-details',[
      ['Khoảng đang bổ sung',b.requested_from&&b.requested_to?`${day(b.requested_from)} → ${day(b.requested_to)}`:'_'],
      ['Đã kiểm tra lịch sử',finite(b.total_symbols)&&b.total_symbols>0?`${fmt(b.checked_symbols||0,0)} / ${fmt(b.total_symbols,0)} mã`:'_'],
      ['Ngày có nến trong kho',a.first_day&&a.last_day?`${day(a.first_day)} → ${day(a.last_day)}`:'_'],
      ['Dung lượng kho nến',finite(a.bytes)?`${fmt(a.bytes/1048576,1)} MB`:'_'],
      ['Bộ thu khi đóng tab web',background.running?'Tiếp tục chạy nền':'Đang chạy cùng máy chủ'],
      ['Sau khi đăng nhập Windows',background.autostart?'Tự khởi động bộ thu':'Chưa bật tự khởi động']]);
    const progress=$('data-backfill-progress');progress.hidden=!(b.total_symbols>0);progress.max=Math.max(1,b.total_symbols||1);progress.value=b.checked_symbols||0;
    const count=(value,total)=>finite(value)&&finite(total)?`${fmt(value,0)} / ${fmt(total,0)} mã`:'_';
    set('data-prices',count(scope.received_prices,scope.symbols));set('data-books',count(scope.received_books,scope.symbols));set('data-valid-books',count(scope.valid_books,scope.symbols));
    set('data-scope-caption',`${payload.available_universes?.find(u=>u.id===payload.universe)?.label||payload.universe} · ${fmt(scope.symbols,0)} mã · toàn bộ ngành trong phạm vi.`);
    set('data-connection',view.connection);set('data-view-mode',view.mode);$('data-view-mode').dataset.mode=payload.analysis.mode;
    set('data-volume-caption',`Khối lượng khớp đã nhận trong phạm vi: ${count(scope.received_volumes,scope.symbols)}.`);
    const excluded=payload.invalid_symbols||(payload.ranking||[]).filter(row=>!row.valid).map(row=>row.symbol);
    $('data-coverage-note').hidden=!excluded.length;
    set('data-coverage-note',excluded.length?`Trên ảnh đang đối chiếu, chưa đủ dữ liệu để tính cho: ${excluded.slice(0,8).join(', ')}${excluded.length>8?` và ${excluded.length-8} mã khác`:''}. Các mã này không được dùng để tạo điều kiện Cảnh báo.`:'');
    fillList('data-status-list',[
      ['Ảnh sổ dùng để đối chiếu độ phủ',dateTime(payload.analysis.asof)],
      ['Bản dữ liệu thị trường đã ghi nhận',dateTime(payload.updated_at)],
      ['Bản tin SSI gần nhất',d.last_stream_at?dateTime(d.last_stream_at):'Chưa ghi nhận trong lần kết nối này'],
      ['Múi giờ hiển thị','Việt Nam · UTC+7']]);
    fillList('data-view-details',[
      ['Phạm vi bộ thu',finite(collector.symbols)?`${fmt(collector.symbols,0)} mã`:'_'],
      ['Đã nhận giá',count(collector.received_prices,collector.symbols)],
      ['Đã nhận tổng khối lượng khớp',count(collector.received_volumes,collector.symbols)],
      ['Có báo giá sổ lệnh',count(collector.received_books,collector.symbols)],
      ['Bản tin luồng từ lần kết nối này',fmt(d.received_events,0)],
      ['Bản tin luồng gần nhất',d.last_stream_at?dateTime(d.last_stream_at):'Chưa ghi nhận trong lần kết nối này'],
      ['Giá tổng hợp ngày trong bộ lọc',`${fmt(d.daily_statistics_received||0,0)} mã`],
      ['Giá từ nến ngày đã tải bù',`${fmt(d.ohlc_daily_received||0,0)} mã`],
      ['Kho bản tin gốc',d.raw_archive_status==='paused_capacity'?'Tạm dừng ghi vì đạt dung lượng; Phát lại vẫn lưu':d.raw_archive_status==='recording'?`Đang ghi · tối đa ${d.raw_archive_retention_days??7} ngày · ${fmt(d.raw_archive_budget_mb,0)} MB`:'_'],
      ['Múi giờ hiển thị','Việt Nam · UTC+7']]);
    set('data-storage-summary',finite(view.snapshots)?`Kho có ${fmt(view.snapshots,0)} ảnh dữ liệu trong ${view.days.length} ngày có dữ liệu.`:'Chưa có thông tin kho ảnh đã lưu.');
    $('data-history-body').replaceChildren(...view.days.map(day=>{
      const tr=node('tr');tr.append(node('td','',day.day.split('-').reverse().join('/')),node('td','',fmt(day.snapshots,0)),node('td','',`${clock(day.first)} → ${clock(day.last)}`));return tr;
    }));
    if(!view.days.length)emptyTable('data-history-body',3,'Chưa có ảnh dữ liệu đã lưu để phát lại.');
    const catalog=d.catalog_counts||{};
    set('data-expansion-note',Object.keys(catalog).length?`Danh mục SSI: ${Object.entries(catalog).map(([board,n])=>board+' '+fmt(n,0)+' cổ phiếu').join(' · ')}. Bộ thu đang theo dõi ${fmt(payload.coverage.collected_count,0)} mã.`:'');
    set('data-storage-policy',`Phát lại lưu ${d.history_retention_days??30} ngày lịch trên máy. Bản tin gốc lưu tối đa ${d.raw_archive_retention_days??7} ngày, giới hạn ${fmt((d.raw_archive_budget_mb??2048)/1024,1)} GB; có thể dọn ngày cũ sớm hơn khi đầy. Hai kho được lưu riêng. Độ phủ phụ thuộc vào thời gian bộ thu đã chạy.`);
  }
  function renderGuide(payload){
    const r=payload?.selected;
    if(!r){set('data-reading-example','Chọn mã và quy mô ở Tổng quan để xem ví dụ từ dữ liệu đang có.');set('data-alert-threshold','_');return;}
    const buy=r.buy||{},sell=r.sell||{};
    set('data-reading-example',r.valid?`Ở Tổng quan, quy mô ${money(payload.notional_vnd)} đồng của ${r.symbol} có lượng đối ứng mua ${percent(buy.fill_ratio)} và bán ${percent(sell.fill_ratio)} trên các mức SSI đã cấp, theo ảnh sổ ${dateTime(r.analysis_at||payload.analysis?.asof)}.`:`${r.symbol} ở Tổng quan chưa có sổ đủ điều kiện để minh họa tỷ lệ đáp ứng.`);
    set('data-alert-threshold',`${fmt((payload.alert_rules?.spread_threshold_bps??25)/100,2)}%`);
  }
  function backfillModel(b){
    const labels={starting:'Chuẩn bị tải bù',waiting:'Chờ dữ liệu danh mục',filling:'Đang tải bù',ready:'Đã kiểm tra',retrying:'Sẽ tự kiểm tra tiếp',backoff:'Đang chờ lượt SSI',stopped:'Chưa chạy tải bù'};
    return {label:labels[b.status]||'Đang kiểm tra',note:b.status==='filling'?'Lịch sử đang được bổ sung ở nền; bạn có thể tiếp tục xem bảng giá.':b.status==='backoff'?'Giữ dữ liệu đã lưu và tự tiếp tục khi đến lượt SSI.':b.status==='retrying'?'Giữ nến đã có; ứng dụng sẽ tự kiểm tra lại các khoảng còn thiếu.':b.status==='ready'?'Các khoảng đã kiểm tra được dùng lại; khoảng chưa có giao dịch giữ trống.':'Giá hiện tại được ưu tiên, lịch sử sẽ được bổ sung tự động.'};
  }
  window.lopmDataView={model,backfillModel,render,renderGuide};
})();
