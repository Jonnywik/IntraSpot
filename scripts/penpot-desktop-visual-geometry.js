const info=(await penpotUtils.getPages()).find(p=>p.name.startsWith('Desktop'));await penpot.openPage(info.id);
const boards=[...penpot.currentPage.root.children].filter(s=>s.type==='board');
return boards.filter(b=>/^(10|11|12|13|14|15|16|49|49D)/.test(b.name)).map(b=>({board:b.name,items:[...b.children].filter(s=>/image|illustration|art|banner|media|hero|cover|graphic/i.test(s.name)).map(s=>({name:s.name,type:s.type,x:Math.round(s.x-b.x),y:Math.round(s.y-b.y),w:Math.round(s.width),h:Math.round(s.height)})).slice(0,15)}));
