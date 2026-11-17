"use strict";
(() => {
  const button=document.getElementById('volume-details-toggle'),panel=document.getElementById('volume-comparison-popover');
  if(!button||!panel)return;
  const native=typeof panel.showPopover==='function';let scheduled=false;
  const isOpen=()=>native?panel.matches(':popover-open'):!panel.hidden;
  function position(){
    scheduled=false;if(!isOpen())return;
    const edge=16,width=document.documentElement.clientWidth,height=document.documentElement.clientHeight;
    panel.style.maxWidth=`${Math.max(0,width-edge*2)}px`;
    const rect=button.getBoundingClientRect(),box=panel.getBoundingClientRect();
    const left=Math.max(edge,Math.min(rect.left,width-box.width-edge));
    const below=rect.bottom+8,above=rect.top-box.height-8;
    const top=below+box.height<=height-edge?below:Math.max(edge,above);
    panel.style.left=`${left}px`;panel.style.top=`${top}px`;
  }
  function schedule(){if(isOpen()&&!scheduled){scheduled=true;requestAnimationFrame(position);}}
  function close(){
    if(!isOpen())return;
    if(native)panel.hidePopover();else{panel.hidden=true;panel.classList.remove('is-open');button.setAttribute('aria-expanded','false');}
  }
  if(native)panel.addEventListener('toggle',()=>{button.setAttribute('aria-expanded',String(isOpen()));schedule();});
  else{
    panel.removeAttribute('popover');panel.hidden=true;button.removeAttribute('popovertarget');
    button.addEventListener('click',()=>{
      if(isOpen()){close();return;}panel.hidden=false;panel.classList.add('is-open');button.setAttribute('aria-expanded','true');position();
    });
    document.addEventListener('click',event=>{if(isOpen()&&!panel.contains(event.target)&&!button.contains(event.target))close();});
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&isOpen()){close();button.focus({preventScroll:true});}});
  }
  panel.querySelector('[data-volume-close]').addEventListener('click',()=>{close();button.focus({preventScroll:true});});
  window.addEventListener('resize',schedule);window.addEventListener('scroll',schedule,{passive:true});
  window.addEventListener('hashchange',close);
  document.addEventListener('lopm:workspace-view',event=>{if(event.detail?.name==='overview'&&event.detail.value!=='stock')close();});
})();
