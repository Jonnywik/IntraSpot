const info = (await penpotUtils.getPages()).find(p => p.name === 'Mobile • Light');
await penpot.openPage(info.id);
const boards = [...penpot.currentPage.root.children].filter(s => s.type === 'board');
const body = {
  Discover: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-9.5Z"/><path d="M9 21v-7h6v7"/>',
  'My Events': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',
  Chat: '<path d="M20 11.5a8 8 0 0 1-8 8H4l1.9-3.8A8 8 0 1 1 20 11.5Z"/><path d="M8.5 11.5h7"/>',
  Settings: '<path d="M4 6h7M15 6h5M4 12h2M10 12h10M4 18h9M17 18h3"/><circle cx="13" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="15" cy="18" r="2"/>'
};
const order = ['Discover', 'My Events', 'Chat', 'Settings'];
let replaced = 0;
for (const board of boards) {
  for (const shape of [...board.children]) if (shape.name.startsWith('Final nav icon /') || shape.name === 'Final status icons') shape.remove();
  for (const shape of [...board.children]) if (shape.name === 'Status indicators') shape.hidden = true;
  const status = penpot.createShapeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="60" height="18" viewBox="0 0 60 18"><g fill="#102A5C"><rect x="1" y="11" width="3" height="5" rx=".5"/><rect x="6" y="8" width="3" height="8" rx=".5"/><rect x="11" y="5" width="3" height="11" rx=".5"/><rect x="16" y="2" width="3" height="14" rx=".5"/></g><path d="M27 7c4-4 10-4 14 0M30 10c2.5-2.5 5.5-2.5 8 0M33.5 13h1" fill="none" stroke="#102A5C" stroke-width="1.6" stroke-linecap="round"/><rect x="46" y="4" width="11" height="10" rx="2" fill="none" stroke="#102A5C" stroke-width="1.5"/><rect x="48" y="6" width="7" height="6" rx=".7" fill="#102A5C"/><path d="M58 7v4" stroke="#102A5C" stroke-width="1.5" stroke-linecap="round"/></svg>');
  status.name = 'Final status icons'; status.x = board.x + 308; status.y = board.y + 11; board.appendChild(status);
  for (const [index, item] of order.entries()) {
    const old = [...board.children].find(s => s.name === `Navigation / ${item} / icon` || s.name === `Event details / nav icon ${item}`);
    if (!old) continue;
    old.hidden = true;
    const selected = board.name.includes('My Events') ? 'My Events' : board.name.includes(' / Chat') ? 'Chat' : board.name.includes(' / Settings') ? 'Settings' : 'Discover';
    const color = selected === item ? '#0E3473' : '#536481';
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${body[item]}</g></svg>`;
    const icon = penpot.createShapeFromSvg(svg);
    icon.name = `Final nav icon / ${item}`; icon.x = board.x + 42 + 95 * index; icon.y = board.y + 764;
    board.appendChild(icon); replaced++;
  }
}
return { boards: boards.length, icons: replaced };
