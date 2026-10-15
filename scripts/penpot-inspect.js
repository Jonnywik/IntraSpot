const pages = await penpotUtils.getPages();
const result = [];
for (const info of pages) {
  await penpot.openPage(info.id);
  const shapes = [...penpot.currentPage.root.children];
  result.push({ page: info.name, id: info.id, boards: shapes.filter(s => s.type === 'board').map(s => ({ id: s.id, name: s.name, x: s.x, y: s.y, w: s.width, h: s.height, children: [...s.children].length })) });
}
return result;
