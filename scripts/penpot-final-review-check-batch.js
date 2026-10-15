if(penpot.currentPage.id!=='2714a049-ae7d-81a2-8008-b3966a11b139'||!storage.finalReviewBaseline)throw Error('Desktop baseline required');
const baseline=storage.finalReviewBaseline.shapes,baseMap=new Map(baseline.map(s=>[s.id,s]));
const authorized=new Set((storage.finalReviewEditsB||[]).filter(e=>e.change==='Resume existing scheduled draft instead of creating another').map(e=>e.id));
function root(p){while(p.parent&&p.parent!=='00000000-0000-0000-0000-000000000000'&&baseMap.has(p.parent))p=baseMap.get(p.parent);return p;}
function hidden(p){return p.hidden||(p.parent&&baseMap.has(p.parent)?hidden(baseMap.get(p.parent)):false);}
const appIds=new Set(baseline.filter(p=>p.type==='board'&&p.parent==='00000000-0000-0000-0000-000000000000'&&!p.hidden&&!/^(00|01|02|03|8|9|Retired)/.test(p.name)).map(p=>p.id));
const state=storage.finalReviewCheck||(storage.finalReviewCheck={cursor:0,missing:[],routes:[],unexpectedRoutes:[],overflow:[],invalidGeometry:[],mobileSnapshot:null});
for(const p of baseline.slice(state.cursor,state.cursor+700)){
 const s=penpot.currentPage.getShapeById(p.id);
 if(!s)state.missing.push(p.id);
 else {
  const actions=s.interactions.map(i=>({trigger:i.trigger,delay:i.delay,action:{...i.action,destination:i.action.destination?.id,relativeTo:i.action.relativeTo?.id}}));
  if(JSON.stringify(actions)!==JSON.stringify(p.interactions||[])){state.routes.push({id:p.id,name:p.name});if(!authorized.has(p.id))state.unexpectedRoutes.push(p.id);}
  const r=root(p);if(!hidden(p)&&!s.hidden&&appIds.has(r.id)){
   if(![s.x,s.y,s.width,s.height].every(Number.isFinite))state.invalidGeometry.push(p.id);
   if(p.id!==r.id&&(s.x<r.x-.5||s.x+s.width>r.x+r.width+.5))state.overflow.push({id:p.id,board:r.name,name:p.name});
  }
 }
 state.cursor++;
}
return {checked:state.cursor,remaining:baseline.length-state.cursor,missing:state.missing,authorizedRouteChanges:state.routes.length,unexpectedRoutes:state.unexpectedRoutes,invalidGeometry:state.invalidGeometry,horizontalOverflow:state.overflow};
