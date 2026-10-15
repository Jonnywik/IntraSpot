const pages=await penpotUtils.getPages();
const mobile=pages.find(p=>p.name==='Mobile • Light');
await penpot.openPage(mobile.id);
const m=[...penpot.currentPage.root.children].find(b=>b.name.startsWith('M10'));
const image=[...m.children].filter(s=>s.type==='image'||(s.fills||[]).some(f=>f.fillImage)).map(s=>({name:s.name,type:s.type,id:s.id,x:s.x-m.x,y:s.y-m.y,w:s.width,h:s.height,fills:(s.fills||[]).map(f=>({fillImage:f.fillImage?Object.keys(f.fillImage):null,fillColor:f.fillColor}))}));
const desk=pages.find(p=>p.name.startsWith('Desktop'));
await penpot.openPage(desk.id);
const boards=[...penpot.currentPage.root.children].filter(s=>s.type==='board');
return { mobileImage:image, problemText:boards.flatMap(b=>[...b.children].filter(s=>s.type==='text'&&/upload|proof|document|evidence|double.check|accreditation/i.test(s.characters||'')).map(s=>({board:b.name,id:s.id,name:s.name,text:s.characters,links:s.interactions?.length||0}))).slice(0,100), nameVariants:boards.flatMap(b=>[...b.children].filter(s=>s.type==='text'&&/Stories (Within|in) the Walls|PLM Culture (Circle|& Arts)/i.test(s.characters||'')).map(s=>({board:b.name,text:s.characters}))).slice(0,80)};
