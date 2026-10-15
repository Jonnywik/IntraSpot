const info=(await penpotUtils.getPages()).find(p=>p.name==='Mobile • Light');
await penpot.openPage(info.id);
return [...penpot.currentPage.root.children].filter(s=>s.type==='board' && /^M(11|16|17|18|19|20|21|22)/.test(s.name)).map(b=>({name:b.name,id:b.id,children:b.children.length,links:[...b.children].filter(s=>s.interactions?.length).map(s=>s.name).filter(n=>n.startsWith('Calendar final')||n.startsWith('View mode')||n.startsWith('My Events final'))}));
