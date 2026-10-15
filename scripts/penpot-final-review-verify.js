if(penpot.currentPage.id!=='2714a049-ae7d-81a2-8008-b3966a11b139'||!storage.finalReviewBaseline)throw Error('Live desktop baseline required');
const walk=s=>[s,...[...(s.children||[])].flatMap(walk)];
const all=walk(penpot.currentPage.root),by=new Map(all.map(s=>[s.id,s])),missing=[],routeChanges=[];
const action=i=>({trigger:i.trigger,delay:i.delay,action:{...i.action,destination:i.action.destination?.id,relativeTo:i.action.relativeTo?.id}});
for(const p of storage.finalReviewBaseline.shapes){const s=by.get(p.id);if(!s){missing.push(p.id);continue;}if(JSON.stringify((s.interactions||[]).map(action))!==JSON.stringify(p.interactions||[]))routeChanges.push({id:p.id,name:p.name});}
const edited=[...(storage.finalReviewEditsA||[]),...(storage.finalReviewEditsB||[])];
const changed=edited.map(e=>{const s=by.get(e.id);return {...e,characters:s.characters,fontSize:s.fontSize,lineHeight:s.lineHeight,x:s.x,y:s.y,width:s.width,height:s.height,align:s.align,verticalAlign:s.verticalAlign,hidden:s.hidden};});
const authorizedRoutes=new Set((storage.finalReviewEditsB||[]).filter(e=>e.change==='Resume existing scheduled draft instead of creating another').map(e=>e.id));
const unexpectedRouteChanges=routeChanges.filter(e=>!authorizedRoutes.has(e.id));
const header=by.get('0790ece5-2133-80b3-8008-c56eaa0e949d'),body=by.get('0790ece5-2133-80b3-8008-c56eaa0e9481'),helper=by.get('0790ece5-2133-80b3-8008-c572ecacc5c9');
const mobile=penpot.currentFile.pages.find(p=>p.id==='7966e618-213e-80ec-8008-b699123492b6');
const mobileSnapshot=walk(mobile.root).map(s=>({id:s.id,name:s.name,parent:s.parent?.id,x:s.x,y:s.y,w:s.width,h:s.height,text:s.characters,fills:s.fills,hidden:s.hidden,interactions:s.interactions.map(i=>({t:i.trigger,a:i.action.type,d:i.action.destination?.id}))}));
const hidden=s=>{let v=s;while(v){if(v.hidden)return true;v=v.parent;}return false;};
const roots=all.filter(s=>s.type==='board'&&s.parent?.id==='00000000-0000-0000-0000-000000000000'&&!s.hidden);
const journeyIds=new Set(storage.finalReviewBaseline.shapes.filter(s=>s.type==='board'&&s.parent==='00000000-0000-0000-0000-000000000000'&&!s.hidden&&!/^(00|01|02|03|8|9|Retired)/.test(s.name)).map(s=>s.id));
function root(s){while(s.parent&&s.parent.id!=='00000000-0000-0000-0000-000000000000')s=s.parent;return s;}
const horizontalOverflow=all.filter(s=>!hidden(s)&&journeyIds.has(root(s).id)&&s.id!==root(s).id&&(s.x<root(s).x-.5||s.x+s.width>root(s).x+root(s).width+.5)).map(s=>({name:s.name,board:root(s).name}));
const hiddenTargets=all.filter(s=>!hidden(s)).flatMap(s=>s.interactions.filter(i=>i.action.destination&&hidden(i.action.destination)).map(i=>({source:s.name,target:i.action.destination.name})));
const disabledActions=all.filter(s=>!hidden(s)&&s.getPluginData('prototype-availability')).filter(s=>s.interactions.some(i=>['click','mouse-enter'].includes(i.trigger))).map(s=>s.id);
const specimenFailures=all.filter(s=>s.type==='board'&&!hidden(s)&&/^Button \//.test(s.name)&&s.height<=64).flatMap(s=>[...(s.children||[])].filter(t=>t.type==='text'&&(t.align!=='center'||t.verticalAlign!=='center'||Math.abs(t.x+t.width/2-s.x-s.width/2)>.1||Math.abs(t.y+t.height/2-s.y-s.height/2)>.1)).map(t=>t.id));
const buttonFailures=(storage.buttonCentering?.pairs||[]).filter(p=>{const f=by.get(p.face),t=by.get(p.label);return !f||!t||t.align!=='center'||t.verticalAlign!=='center'||Math.abs(t.x+t.width/2-f.x-f.width/2)>.1||Math.abs(t.y+t.height/2-f.y-f.height/2)>.1;}).map(p=>p.label);
const hoverMismatch=[];for(const s of all.filter(s=>!hidden(s)))for(const i of s.interactions){if(i.trigger!=='mouse-enter'||i.action.type!=='open-overlay'||!i.action.destination?.name.startsWith('90 '))continue;const face=walk(i.action.destination).find(t=>t.name==='Hover / appearance'),base=s.interactions.find(t=>t.trigger==='click')?.action,hover=face?.interactions.find(t=>t.trigger==='click')?.action;if(base&&(!hover||base.destination?.id!==hover.destination?.id||base.type!==hover.type))hoverMismatch.push(s.id);}
return {missing,routeChanges,unexpectedRouteChanges,changed,journeyBoards:journeyIds.size,horizontalOverflow,hiddenTargets,disabledActions,specimenFailures,buttonLabelsChecked:(storage.buttonCentering?.pairs.length||0)+5,buttonFailures,hoverMismatch,headingFooterClearance:body.y+body.height-header.y-header.height,helperFitsTwoLines:helper.height>=Number(helper.fontSize)*Number(helper.lineHeight)*2,mobileSnapshot,presentationTesting:'Heuristic MCP and image checks only; no live pointer/keyboard or participant testing'};
