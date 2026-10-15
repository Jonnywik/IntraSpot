await penpot.openPage('2714a049-ae7d-81a2-8008-b3966a11b139');
const boards=[...penpot.currentPage.root.children].filter(s=>s.type==='board');
const walk=s=>[s,...[...(s.children||[])].flatMap(walk)];
storage.desktopPolish={boards:boards.map(b=>({id:b.id,name:b.name})),walk};
storage.desktopPolish.audit=boards.map(b=>({id:b.id,name:b.name,x:b.x,y:b.y,w:b.width,h:b.height,hidden:b.hidden,
  text:walk(b).filter(s=>s.type==='text').map(s=>({id:s.id,name:s.name,text:s.characters,x:Math.round(s.x-b.x),y:Math.round(s.y-b.y),w:Math.round(s.width),h:Math.round(s.height),size:s.fontSize})),
  routes:walk(b).flatMap(s=>[...(s.interactions||[])].map(i=>({name:s.name,to:i.action?.destination?.id||null}))) }));
return storage.desktopPolish.audit.map(b=>({id:b.id,name:b.name,hidden:b.hidden,texts:b.text.length,routes:b.routes.length,flags:b.text.filter(t=>/scope|placeholder|not yet|prototype only|coming soon/i.test(t.text)).map(t=>t.text)}));
