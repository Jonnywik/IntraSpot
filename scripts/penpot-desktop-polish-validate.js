const boards=[...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden);
const walk=s=>[s,...[...(s.children||[])].flatMap(walk)];
const shapes=walk(penpot.currentPage.root),ids=new Set(shapes.map(s=>s.id));
const broken=[],hiddenTargets=[],disagreements=[],overflow=[];let routes=0;
for(const b of boards){const ss=walk(b);for(const s of ss){for(const i of [...(s.interactions||[])]){if(i.action.type!=='navigate-to')continue;routes++;const d=i.action.destination;if(!d||!ids.has(d.id))broken.push({board:b.name,shape:s.name});else if(d.hidden)hiddenTargets.push({board:b.name,shape:s.name,to:d.name});}
 if(s.hidden)continue;const x=s.x-b.x,y=s.y-b.y;if(s.type==='text'&&(x<-.5||y<-.5||x+s.width>b.width+1||y+s.height>b.height+1))overflow.push({board:b.name,shape:s.name,x,y,w:s.width,h:s.height});
 if(s.name.endsWith(' / label')){const other=ss.find(t=>t.name===s.name.slice(0,-8));if(other){const a=[...s.interactions].find(i=>i.action.type==='navigate-to')?.action.destination?.id,bb=[...other.interactions].find(i=>i.action.type==='navigate-to')?.action.destination?.id;if(a&&bb&&a!==bb)disagreements.push({board:b.name,shape:s.name});}}
 }}
return {page:penpot.currentPage.name,boards:boards.length,shapes:shapes.length,routes,broken,hiddenTargets,disagreements,overflow,uncompletedPlaceholder:boards.flatMap(b=>walk(b).filter(s=>s.type==='text'&&/Prototype scope|This navigation destination is shown|Live messaging, moderation/.test(s.characters)).map(s=>({board:b.name,text:s.characters}))),finalBoards:storage.desktopFinal?.newBoards||[]};
