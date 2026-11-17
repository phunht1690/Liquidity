"use strict";
(() => {
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
  const groups=new Map();
  function select(name,value,{focus=false,animate=false,navigate=false}={}){
    const group=groups.get(name),chosen=group?.tabs.find(tab=>tab.dataset.tabValue===value);
    if(!chosen)return;
    const changed=group.value!==value;
    group.value=value;
    for(const tab of group.tabs){
      const active=tab===chosen,panel=document.getElementById(tab.getAttribute('aria-controls'));
      tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;
      if(panel)panel.hidden=!active;
    }
    document.body.dataset[`${name}View`]=value;
    if(focus)chosen.focus({preventScroll:true});
    if(changed&&animate&&!reduced.matches){
      const panel=document.getElementById(chosen.getAttribute('aria-controls'));
      panel?.animate?.([{opacity:.45,transform:'translateY(4px)'},{opacity:1,transform:'none'}],{duration:180,easing:'ease-out'});
    }
    if(changed)document.dispatchEvent(new CustomEvent('lopm:workspace-view',{detail:{name,value}}));
    const hash=chosen.dataset.tabHash;
    if(navigate&&hash&&location.hash!==`#${hash}`)location.hash=hash;
  }
  for(const list of document.querySelectorAll('[data-workspace-tabs]')){
    const name=list.dataset.workspaceTabs,tabs=[...list.querySelectorAll('[role=tab]')];
    groups.set(name,{tabs,value:null});
    for(const tab of tabs){
      tab.addEventListener('click',event=>{if(tab.dataset.tabHash)event?.preventDefault();select(name,tab.dataset.tabValue,{animate:true,navigate:true});});
      tab.addEventListener('keydown',event=>{
        const index=tabs.indexOf(tab);
        const next=event.key==='ArrowRight'?(index+1)%tabs.length:event.key==='ArrowLeft'?(index+tabs.length-1)%tabs.length:event.key==='Home'?0:event.key==='End'?tabs.length-1:null;
        if(next===null)return;
        event.preventDefault();select(name,tabs[next].dataset.tabValue,{focus:true,animate:true,navigate:true});
      });
    }
    select(name,tabs.find(tab=>tab.getAttribute('aria-selected')==='true')?.dataset.tabValue||tabs[0]?.dataset.tabValue);
  }
  window.lopmWorkspaceUI={
    selectMarket:(value,options)=>select('market',value,options),
    selectBook:(value,options)=>select('book',value,options),
    syncOverviewRoute(hash,options){
      const routes={stock:'stock',chart:'stock',book:'book',cost:'book',ranking:'ranking'};
      if(hash==='overview'||hash==='')select('overview',groups.get('overview')?.value||'stock',options);
      else if(routes[hash])select('overview',routes[hash],options);
    },
    overviewView:()=>groups.get('overview')?.value||'stock',
    syncDataRoute(hash){
      if(hash==='how-it-works')select('data','guide');
      else if(['data','methods','data-status','data-fields','data-off-hours'].includes(hash))select('data','status');
      if(hash==='data-off-hours'){
        const details=document.getElementById('data-off-hours');if(details)details.open=true;
      }
    },
    marketView:()=>groups.get('market')?.value||'stocks'
  };
})();
