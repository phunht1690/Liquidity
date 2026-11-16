"use strict";
(() => {
  const preference=window.matchMedia('(prefers-reduced-motion: reduce)'),records=new WeakMap(),requests=new WeakMap(),ui=new WeakMap(),active=new Set();
  const time=()=>performance.now();
  function cancel(animations=[]){for(const animation of animations)animation.cancel();}
  function play(element,frames,options){
    if(preference.matches||document.hidden||!element?.animate)return null;
    const animation=element.animate(frames,{easing:'cubic-bezier(.22,.7,.3,1)',...options});active.add(animation);
    const clear=()=>active.delete(animation);animation.finished.then(clear,clear);return animation;
  }
  preference.addEventListener('change',()=>{if(preference.matches){cancel([...active]);active.clear();}});
  function reset(chart){cancel(records.get(chart)?.animations);records.delete(chart);requests.delete(chart);}
  function group(chart,nodes,layer){
    if(!nodes.length)return null;
    const container=document.createElementNS('http://www.w3.org/2000/svg','g');container.setAttribute('data-motion-layer',layer);
    chart.insertBefore(container,nodes[0]);container.append(...nodes);return container;
  }
  function requestView(chart){requests.set(chart,true);}
  function present(chart,key,{replay=false,interacting=false}={}){
    const previous=records.get(chart),requested=requests.get(chart);requests.delete(chart);cancel(previous?.animations);
    const now=time(),record={key,animations:[],lastView:previous?.lastView??-Infinity};records.set(chart,record);
    // Routine polling, replay frames, resizing and direct dragging stay immediate.
    if(preference.matches||document.hidden||replay||interacting||chart.clientWidth<=0||chart.clientHeight<=0)return;
    const nodes=[...chart.querySelectorAll('[data-series],[data-side],[data-cost-series]')];
    if(!nodes.length){records.delete(chart);return;}
    const enter=!previous||previous.key!==key,view=!enter&&requested&&now-record.lastView>=180;
    if(!enter&&!view)return;
    const volume=nodes.filter(n=>n.getAttribute('data-series')==='volume'),series=nodes.filter(n=>n.getAttribute('data-series')!=='volume');
    const data=group(chart,series,'series');
    if(enter){
      // Reveal existing geometry without morphing prices or bridging gaps.
      if(data)record.animations.push(play(data,[{opacity:.25,clipPath:'inset(0 100% 0 0)'},{opacity:1,clipPath:'inset(0 0% 0 0)'}],{duration:380}));
      const columns=group(chart,volume,'volume');
      if(columns){columns.style.transformBox='fill-box';columns.style.transformOrigin='center bottom';record.animations.push(play(columns,[{opacity:.18,transform:'scaleY(.35)'},{opacity:1,transform:'scaleY(1)'}],{duration:300,delay:45}));}
    }else{
      // A brief data-only fade accompanies a discrete zoom; axes never move.
      if(data)record.animations.push(play(data,[{opacity:.65},{opacity:1}],{duration:115}));
      record.lastView=now;
    }
    record.animations=record.animations.filter(Boolean);
  }
  function enter(element,kind='tooltip'){
    ui.get(element)?.cancel();
    const dialog=kind==='dialog',animation=play(element,dialog?[{opacity:.3,transform:'scale(.99)'},{opacity:1,transform:'scale(1)'}]:[{opacity:0,transform:'translateY(3px)'},{opacity:1,transform:'translateY(0)'}],{duration:dialog?170:105});
    if(animation)ui.set(element,animation);
  }
  window.lopmChartMotion={present,requestView,reset,enter};
})();
