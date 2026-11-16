"use strict";
(() => {
  const groups={
    overview:{label:'current-overview-section',names:{"stock-overview":"Cổ phiếu & biểu đồ","book-section":"Sổ lệnh & quy mô","ranking-panel":"Bảng giá"}},
    methods:{names:{"data-status":"Dữ liệu","how-it-works":"Hướng dẫn"}}
  };
  let scheduled=false;
  function update(){
    scheduled=false;const group=groups[document.body.dataset.view];
    const threshold=window.matchMedia("(max-width:767px)").matches?155:98;
    const sections=Object.keys(group?.names||{}).map(id=>document.getElementById(id)).filter(el=>el&&!el.closest('[hidden]'));
    let active=sections[0]?.id;
    for(const section of sections)if(section.getBoundingClientRect().top<=threshold)active=section.id;
    document.querySelectorAll("[data-section-target]").forEach(link=>{
      const current=!!group&&link.dataset.sectionTarget===active;
      link.classList.toggle("is-current",current);
      if(current)link.setAttribute("aria-current","location");else link.removeAttribute("aria-current");
    });
    if(group?.label){const label=document.getElementById(group.label);if(label)label.textContent=group.names[active]||Object.values(group.names)[0];}
  }
  function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(update);}}
  window.addEventListener("scroll",schedule,{passive:true});window.addEventListener("resize",schedule);
  window.addEventListener("hashchange",schedule);new MutationObserver(schedule).observe(document.body,{attributes:true,attributeFilter:["data-view","data-data-view"]});
  update();
})();
