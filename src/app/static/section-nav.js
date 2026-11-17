"use strict";
(() => {
  const overview={stock:['stock-overview','Cổ phiếu & biểu đồ'],book:['book-section','Sổ lệnh & quy mô'],ranking:['ranking-panel','Bảng giá & ngành']};
  function update(){
    const view=document.body.dataset.view;
    const chosen=overview[document.body.dataset.overviewView]||overview.stock;
    const active=view==='overview'?chosen[0]:view==='methods'?(document.body.dataset.dataView==='guide'?'how-it-works':'data-status'):null;
    document.querySelectorAll('[data-section-target]').forEach(link=>{
      const current=link.dataset.sectionTarget===active;
      link.classList.toggle('is-current',current);
      if(link.getAttribute('role')!=='tab'){
        if(current)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
      }
    });
    const label=document.getElementById('current-overview-section');if(label)label.textContent=chosen[1];
  }
  window.addEventListener('hashchange',update);
  document.addEventListener('lopm:workspace-view',update);
  new MutationObserver(update).observe(document.body,{attributes:true,attributeFilter:['data-view','data-data-view','data-overview-view']});
  update();
})();
