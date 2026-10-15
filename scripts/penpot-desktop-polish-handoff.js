const boards=[...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden);
const by=p=>boards.find(b=>b.name.startsWith(p+' •'));
const walk=s=>[s,...(s.children||[]).flatMap(walk)];
const targets=(b,n)=>walk(b).filter(s=>s.name===n||s.name===n+' / label').flatMap(s=>s.interactions).map(i=>i.action?.destination?.id).filter(Boolean);
const checks=[];
for(const [from,to]of [['200','11R'],['201','11C'],['202','11W'],['203','11P'],['210','11R'],['211','11C'],['212','11W'],['213','11P']]){const n=from.startsWith('21')?'Action / Open calendar event':'Action / Open event';checks.push({check:from+' opens '+to,pass:targets(by(from),n).every(id=>id===by(to).id)&&targets(by(from),n).length>0});}
for(const [control,dest]of [['Action / Text size','50T'],['Action / Language','50L']])checks.push({check:control+' is independent',pass:targets(by('50'),control).includes(by(dest).id)});
for(const p of ['50T','50L']){const b=by(p);checks.push({check:p+' leaves contrast and motion off',pass:['Settings / contrast state','Settings / motion state'].every(n=>walk(b).find(s=>s.name===n)?.characters==='Off')});}
checks.push({check:'Past event registration disabled',pass:targets(by('11P'),'Action / Register').length===0});
const guide=by('03');penpot.viewport.zoomIntoView([guide]);
penpot.currentPage.setPluginData('desktop-final-verification',JSON.stringify({date:'2026-10-08',scope:'desktop',boards:boards.length,checks,method:'MCP route inspection and visual PNG review; not participant testing'}));
return {boards:boards.length,checks,focusedBoard:guide.name,readyFor:'participant prototype review',flows:penpot.currentPage.flows.map(f=>f.name)};
