"use strict";
// One height transition for native details and custom disclosure buttons.
(() => {
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)'),states=new WeakMap();
  const native=el=>el.tagName==='DETAILS';
  const isExpanded=el=>states.get(el)?.expanded??(native(el)?el.open:!el.hidden);
  function setExpanded(el,expanded){
    if(!el)return;
    const prior=states.get(el);
    if(prior?.expanded===expanded)return expanded;
    const from=el.getBoundingClientRect().height;
    if(prior?.animation){prior.animation.onfinish=null;prior.animation.cancel();}
    el.style.height='';el.style.overflow='';
    const finish=()=>{
      if(native(el))el.open=expanded;else el.hidden=!expanded;
      el.style.height='';el.style.overflow='';el.removeAttribute('data-disclosure-moving');
      states.delete(el);
      document.dispatchEvent(new CustomEvent('lopm:disclosure-settled',{detail:{id:el.id,expanded}}));
    };
    if(reduced.matches||!el.animate||!el.isConnected||el.parentElement?.closest('[hidden]')){
      finish();return expanded;
    }
    // Measure the natural destination, retaining content during collapse.
    if(native(el))el.open=expanded;else el.hidden=!expanded;
    const to=el.getBoundingClientRect().height;
    if(native(el))el.open=true;else el.hidden=false;
    if(Math.abs(to-from)<1){finish();return expanded;}
    el.style.overflow='hidden';el.dataset.disclosureMoving=expanded?'opening':'closing';
    const box=getComputedStyle(el),adjust=box.boxSizing==='border-box'?0:
      ['paddingTop','paddingBottom','borderTopWidth','borderBottomWidth'].reduce((sum,key)=>sum+(parseFloat(box[key])||0),0);
    const animation=el.animate([{height:`${Math.max(0,from-adjust)}px`},{height:`${Math.max(0,to-adjust)}px`}],
      {duration:220,easing:'cubic-bezier(.22,.68,.25,1)',fill:'both'});
    states.set(el,{expanded,animation});
    animation.onfinish=()=>{animation.onfinish=null;finish();animation.cancel();};
    return expanded;
  }
  document.addEventListener('click',event=>{
    const summary=event.target.closest?.('summary'),details=summary?.parentElement;
    if(!details||!native(details)||event.defaultPrevented||event.button>0)return;
    if(event.target.closest('a,button,input,select,textarea'))return;
    event.preventDefault();setExpanded(details,!isExpanded(details));
  });
  window.lopmDisclosure={setExpanded,toggle:el=>setExpanded(el,!isExpanded(el)),isExpanded};
})();
