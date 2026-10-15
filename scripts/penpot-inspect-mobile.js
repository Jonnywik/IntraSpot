const info = (await penpotUtils.getPages()).find(p => p.name === 'Mobile • Light');
await penpot.openPage(info.id);
const boards = [...penpot.currentPage.root.children].filter(s => s.type === 'board');
return boards.filter(b => /M1[0-5]/.test(b.name)).map(b => ({
  board: b.name,
  id: b.id,
  children: [...b.children].map(s => ({ id: s.id, name: s.name, type: s.type, x: Math.round(s.x-b.x), y: Math.round(s.y-b.y), w: Math.round(s.width), h: Math.round(s.height), text: s.type === 'text' ? s.characters : undefined })).filter(s => s.type === 'text' || /nav|tab|button|chip|hero|card/i.test(s.name)).slice(0, 55)
}));
