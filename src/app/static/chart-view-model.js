"use strict";
// Pure range math shared by the navigator, zoom buttons and keyboard gestures.
(() => {
  const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
  const stamp=p=>Date.parse(p?.received_at||p?.timestamp||p?.observation_at);
  function range(start,end,count){
    if(count<2)return [0,Math.max(0,count-1)];
    let a=clamp(Math.round(Math.min(start,end)),0,count-1),b=clamp(Math.round(Math.max(start,end)),0,count-1);
    if(a===b){if(b<count-1)b++;else a--;}
    return [a,b];
  }
  function pan(current,delta,count){
    if(count<2)return range(0,0,count);
    const size=current[1]-current[0],start=clamp(Math.round(current[0]+delta),0,count-1-size);
    return [start,start+size];
  }
  function zoom(current,factor,count,anchor=.5){
    if(count<2)return range(0,0,count);
    anchor=clamp(anchor,0,1);
    const size=clamp(Math.round((current[1]-current[0])*factor),1,count-1);
    const start=clamp(Math.round(current[0]+(current[1]-current[0])*anchor-size*anchor),0,count-1-size);
    return [start,start+size];
  }
  function nearest(values,value){
    if(!values.length)return 0;
    let lo=0,hi=values.length-1;
    while(lo<hi){const mid=(lo+hi)>>1;if(values[mid]<value)lo=mid+1;else hi=mid;}
    return lo>0&&Math.abs(values[lo-1]-value)<=Math.abs(values[lo]-value)?lo-1:lo;
  }
  function coordinates(points,bars=false){
    const times=points.map(stamp),first=times[0],span=times.at(-1)-first;
    return points.map((_,i)=>bars||!(span>0)?(points.length<2?.5:i/(points.length-1)):(times[i]-first)/span);
  }
  function panDomain(current,delta,coords){
    if(coords.length<2)return range(0,0,coords.length);
    const width=coords[current[1]]-coords[current[0]],start=clamp(coords[current[0]]+delta,0,1-width);
    return range(nearest(coords,start),nearest(coords,start+width),coords.length);
  }
  function zoomDomain(current,factor,coords,anchor=.5){
    if(coords.length<2)return range(0,0,coords.length);
    anchor=clamp(anchor,0,1);const oldWidth=coords[current[1]]-coords[current[0]],width=clamp(oldWidth*factor,0,1);
    const start=clamp(coords[current[0]]+oldWidth*anchor-width*anchor,0,1-width);
    return range(nearest(coords,start),nearest(coords,start+width),coords.length);
  }
  window.lopmChartViewModel={range,pan,zoom,nearest,coordinates,stamp,panDomain,zoomDomain};
})();
