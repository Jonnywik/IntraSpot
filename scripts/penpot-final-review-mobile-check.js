const walk=s=>[s,...[...(s.children||[])].flatMap(walk)];
const p=penpot.currentFile.pages.find(p=>p.id==='7966e618-213e-80ec-8008-b699123492b6');
return {mobileSnapshot:walk(p.root).map(s=>({id:s.id,name:s.name,parent:s.parent?.id,x:s.x,y:s.y,w:s.width,h:s.height,text:s.characters,fills:s.fills,hidden:s.hidden,interactions:s.interactions.map(i=>({t:i.trigger,a:i.action.type,d:i.action.destination?.id}))}))};
