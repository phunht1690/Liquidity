const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const sandbox={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/app/static/chart-view-model.js'),'utf8'),sandbox);
const m=sandbox.window.lopmChartViewModel,plain=v=>Array.from(v);
assert.deepEqual(plain(m.range(8,2,10)),[2,8]);
assert.deepEqual(plain(m.range(-100,100,10)),[0,9]);
assert.deepEqual(plain(m.range(9,9,10)),[8,9]);
assert.deepEqual(plain(m.range(0,0,1)),[0,0]);
assert.deepEqual(plain(m.zoom([0,99],.5,100)),[25,75]);
assert.deepEqual(plain(m.zoom([25,75],10,100)),[0,99]);
assert.deepEqual(plain(m.pan([20,40],-99,100)),[0,20]);
assert.deepEqual(plain(m.pan([20,40],99,100)),[79,99]);
assert.deepEqual(plain(m.zoom([10,30],.5,100,0)),[10,20]);
assert.deepEqual(plain(m.zoom([10,30],.5,100,1)),[20,30]);
assert.deepEqual(plain(m.zoom([0,0],.5,1)),[0,0]);
// A sparse recording uses actual elapsed time; candle navigation uses candle order.
const points=[0,5,60].map(minute=>({timestamp:new Date(Date.UTC(2026,10,13,2,15)+minute*60000).toISOString()}));
assert.equal(m.coordinates(points)[1],5/60);
assert.equal(m.coordinates(points,true)[1],.5);
assert.equal(m.nearest(m.coordinates(points),.1),1);
assert.equal(m.nearest(m.coordinates(points),.9),2);
assert.equal(m.nearest([],1),0);
assert.equal(m.coordinates([points[0]])[0],.5);
// A receiver outage changes sample density. Panning and zooming observations
// must operate on elapsed time, not stretch the window to keep the same count.
const irregular=[0,.05,.1,.15,.2,.25,.3,.6,.7,.8,.9,1];
assert.deepEqual(plain(m.panDomain([2,6],.5,irregular)),[7,9]);
assert.ok(Math.abs(irregular[9]-irregular[7]-.2)<1e-10);
assert.deepEqual(plain(m.zoomDomain([0,11],.2,irregular,.75)),[7,9]);
assert.deepEqual(plain(m.panDomain([7,9],9,irregular)),[9,11]);
// Clamp every combination: panning cannot alter range width or exceed the source.
for(let count=2;count<80;count++)for(let start=0;start<count-1;start++){
  const range=m.range(start,start+7,count),moved=m.pan(range,count/2,count),zoomed=m.zoom(range,.6,count,.8);
  assert.equal(moved[1]-moved[0],range[1]-range[0]);
  for(const r of [moved,zoomed])assert.ok(r[0]>=0&&r[1]<count&&r[1]>r[0]);
}
console.log('Chart selection, zoom anchors, pan bounds and sparse-time navigation passed.');
