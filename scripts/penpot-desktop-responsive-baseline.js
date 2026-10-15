const walk=s=>[s,...[...(s.children||[])].flatMap(walk)];
const mobile=penpot.currentFile.pages.find(p=>p.id==='7966e618-213e-80ec-8008-b699123492b6');
storage.mobileResponsiveBaseline=walk(mobile.root).map(s=>({id:s.id,name:s.name,parent:s.parent?.id,x:s.x,y:s.y,w:s.width,h:s.height,text:s.characters,fills:s.fills,hidden:s.hidden,interactions:[...(s.interactions||[])].map(i=>({t:i.trigger,a:i.action.type,d:i.action.destination?.id}))}));
const version=await penpot.currentFile.saveVersion('Before desktop responsive and motion polish • 2026-10-11');
return {versionId:version.id,mobileShapes:storage.mobileResponsiveBaseline.length,desktopShapes:storage.responsiveBaseline?.shapes.length,mobileSnapshot:storage.mobileResponsiveBaseline};
