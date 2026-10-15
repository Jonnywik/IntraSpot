const info=(await penpotUtils.getPages()).find(p=>p.name==='Mobile • Light');await penpot.openPage(info.id);
const b=[...penpot.currentPage.root.children].find(b=>b.name.startsWith('M14'));
return [...b.children].filter(s=>s.y-b.y>=460&&s.y-b.y<752).map(s=>({name:s.name,y:Math.round(s.y-b.y),h:Math.round(s.height),text:s.type==='text'?s.characters:undefined,links:s.interactions?.length||0}));
