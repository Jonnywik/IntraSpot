const info=(await penpotUtils.getPages()).find(p=>p.name==='Mobile • Light');
await penpot.openPage(info.id);
return [...penpot.currentPage.root.children].filter(b=>b.type==='board'&&/^M(02|03|04)/.test(b.name)).map(b=>({name:b.name,children:[...b.children].filter(s=>s.type==='text'||(s.type==='rectangle'&&s.y-b.y>180)).map(s=>({name:s.name,x:Math.round(s.x-b.x),y:Math.round(s.y-b.y),w:Math.round(s.width),h:Math.round(s.height),text:s.type==='text'?s.characters:undefined,links:s.interactions?.length||0})).filter(s=>s.y>105)}));
