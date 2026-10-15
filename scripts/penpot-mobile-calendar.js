const { C, rect, text, ellipse, clean, tap } = storage.IS;
const info = (await penpotUtils.getPages()).find(p => p.name === 'Mobile • Light');
await penpot.openPage(info.id);
const root = penpot.currentPage.root;
const boards = () => [...root.children].filter(s => s.type === 'board');
const base = boards().find(b => b.name.startsWith('M11'));
const names = ['Pending','Confirmed','Waitlist','Past'];
const targets = [
  { prefix: 'M19', state: 'Pending', day: 12, title: 'Stories in the Walls', note: 'Organizer review in progress', color: C.amber, bg: C.paleAmber },
  { prefix: 'M20', state: 'Confirmed', day: 19, title: 'Community Makers Market', note: 'Your place is confirmed', color: C.green, bg: C.paleGreen },
  { prefix: 'M21', state: 'Waitlist', day: 26, title: 'Open Studio Saturday', note: 'You are #3 on the waitlist', color: C.blue, bg: C.paleBlue },
  { prefix: 'M22', state: 'Past', day: 5, title: 'Heritage at Dusk', note: 'Event ended · chat archived', color: C.gray, bg: C.paleGray }
];
const listPrefixes = ['M11','M16','M17','M18'];
for (const [index,t] of targets.entries()) {
  let board = boards().find(b => b.name.startsWith(t.prefix));
  if (!board) { board = base.clone(); board.name = `${t.prefix} • Member / Calendar / ${t.state}`; board.x = 2820 + index*470; board.y = 1920; }
  t.board = board;
  clean(board, ['Pending','Registration state','My Events final','View mode','Calendar final']);
  for (const [i,name] of names.entries()) text(board, `Calendar final / tab ${name}`, name, [20,108,196,284][i], 199, 87, 32, 13, i === index ? '700' : '500', i === index ? C.navy : C.muted);
  rect(board, 'Calendar final / selected line', [20,108,196,284][index], 233, [72,82,70,40][index], 3, C.gold, 2);
  rect(board, 'Calendar final / view shell', 269, 249, 101, 28, C.sand, 14);
  rect(board, 'Calendar final / view selected', 318, 252, 49, 22, C.white, 11);
  text(board, 'Calendar final / list toggle', 'List', 276, 255, 38, 19, 11, '500', C.muted, false, 'center');
  text(board, 'Calendar final / calendar toggle', 'Calendar', 320, 255, 47, 19, 10, '700', C.navy, false, 'center');
  text(board, 'Calendar final / month', 'April', 20, 287, 150, 34, 23, '700', C.ink, true);
  text(board, 'Calendar final / sample', 'SAMPLE DATES', 258, 296, 112, 20, 10, '700', C.muted, false, 'right');
  rect(board, 'Calendar final / grid panel', 20, 329, 350, 278, C.white, 18);
  for (const [col,week] of ['M','T','W','T','F','S','S'].entries()) text(board, `Calendar final / weekday ${col}`, week, 28+50*col, 341, 33, 19, 10, '700', C.muted, false, 'center');
  for (let day=1;day<=30;day++) {
    const slot = day; const col = slot%7; const row = Math.floor(slot/7);
    const x = 28+50*col, y = 369+48*row;
    if (day === t.day) ellipse(board, `Calendar final / selected date ${day}`, x+3, y-3, 29, t.bg);
    text(board, `Calendar final / date ${day}`, String(day), x, y, 35, 24, 13, day === t.day ? '700' : '500', day === t.day ? C.navy : C.ink, false, 'center');
    const markerY = y+27;
    if (day === 12) rect(board, `Calendar final / pending marker ${day}`, x+10, markerY, 15, 2, C.gold, 1);
    if (day === 19) ellipse(board, `Calendar final / confirmed marker ${day}`, x+16, markerY-1, 4, C.green);
    if (day === 26) for (let k=0;k<3;k++) rect(board, `Calendar final / waitlist marker ${day} ${k}`, x+7+7*k, markerY, 4, 2, C.blue, 1);
    if (day === 5) ellipse(board, `Calendar final / past marker ${day}`, x+16, markerY-1, 4, C.gray);
  }
  rect(board, 'Calendar final / event panel', 20, 619, 350, 115, C.white, 18);
  rect(board, 'Calendar final / event accent', 20, 635, 3, 84, t.color, 2);
  text(board, 'Calendar final / event day', `${t.day} APR  ·  ${t.state.toUpperCase()}`, 36, 633, 290, 20, 10, '700', t.color);
  text(board, 'Calendar final / event title', t.title, 36, 660, 307, 31, 17, '700', C.ink, true);
  text(board, 'Calendar final / event note', t.note, 36, 695, 307, 24, 12, '400', C.muted);
}
for (const [index,t] of targets.entries()) {
  for (const [i,name] of names.entries()) tap([...t.board.children].find(s => s.name === `Calendar final / tab ${name}`), targets[i].board);
  tap([...t.board.children].find(s => s.name === 'Calendar final / list toggle'), boards().find(b => b.name.startsWith(listPrefixes[index])));
  const list = boards().find(b => b.name.startsWith(listPrefixes[index]));
  const calendarButton = [...list.children].find(s => s.name === 'View mode / calendar');
  if (calendarButton) tap(calendarButton, t.board);
}
return targets.map(t => ({ name: t.board.name, id: t.board.id, children: t.board.children.length }));
