const walk=s=>[s,...[...(s.children||[])].flatMap(walk)];
const boards=[...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden);
return boards.filter(b=>/^(10M |11M |53 |34 |50 |10 |11 )/.test(b.name)).map(b=>({id:b.id,name:b.name,w:b.width,h:b.height,items:walk(b).slice(1).map(s=>({id:s.id,name:s.name,type:s.type,x:Math.round(s.x-b.x),y:Math.round(s.y-b.y),w:Math.round(s.width),h:Math.round(s.height),text:s.characters,size:s.fontSize,fixed:s.fixedWhenScrolling,to:[...(s.interactions||[])].map(i=>({trigger:i.trigger,type:i.action.type,d:i.action.destination?.id}))}))}));
