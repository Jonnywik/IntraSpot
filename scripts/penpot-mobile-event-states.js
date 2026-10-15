const { C, rect, text, clean, tap } = storage.IS;
const info = (await penpotUtils.getPages()).find(p => p.name === 'Mobile • Light');
await penpot.openPage(info.id);
const root = penpot.currentPage.root;
const all = () => [...root.children].filter(s => s.type === 'board');
const pending = all().find(b => b.name.startsWith('M11'));
const states = [
  { prefix: 'M11', name: pending.name, x: pending.x, y: pending.y, label: 'Pending' },
  { prefix: 'M16', name: 'M16 • Member / My Events / Confirmed', x: 2820, y: 960, label: 'Confirmed' },
  { prefix: 'M17', name: 'M17 • Member / My Events / Waitlist', x: 3290, y: 960, label: 'Waitlist' },
  { prefix: 'M18', name: 'M18 • Member / My Events / Past', x: 3760, y: 960, label: 'Past' }
];
for (const state of states.slice(1)) {
  let board = all().find(b => b.name.startsWith(state.prefix));
  if (!board) { board = pending.clone(); board.name = state.name; board.x = state.x; board.y = state.y; }
  state.board = board;
}
states[0].board = pending;
const names = ['Pending','Confirmed','Waitlist','Past'];
for (const [index, state] of states.entries()) {
  const board = state.board;
  clean(board, ['My Events / Pending','My Events / Confirmed','My Events / Waitlist','My Events / Past','My Events / selected line','My Events final','View mode']);
  if (index > 0) clean(board, ['Pending','Registration state']);
  for (const [i, name] of names.entries()) {
    const x = [20,108,196,284][i];
    text(board, `My Events final / tab ${name}`, name, x, 199, 87, 32, 13, i === index ? '700' : '500', i === index ? C.navy : C.muted);
  }
  rect(board, 'My Events final / selected line', [20,108,196,284][index], 233, [72,82,70,40][index], 3, C.gold, 2);
  rect(board, 'View mode / shell', 269, 249, 101, 28, C.sand, 14);
  rect(board, 'View mode / list selected', 272, 252, 45, 22, C.white, 11);
  text(board, 'View mode / list', 'List', 276, 255, 38, 19, 11, '700', C.navy, false, 'center');
  text(board, 'View mode / calendar', 'Calendar', 320, 255, 47, 19, 10, '500', C.muted, false, 'center');
  if (index === 0) continue;
  const title = index === 1 ? "YOU'RE GOING" : index === 2 ? 'WAITING FOR A SPOT' : 'COMPLETED EVENTS';
  text(board, 'Registration state / section', title, 20, 253, 245, 19, 11, '700', C.blue);
  if (index === 1) {
    const data = [
      { y: 282, title: 'Community Makers Market', when: 'Sat, 19 Apr  ·  10:00 AM–4:00 PM', note: 'Your place is confirmed. Event chat is open.' },
      { y: 480, title: 'Riverside Photo Walk', when: 'Sun, 27 Apr  ·  7:30–9:30 AM', note: 'Your place is confirmed. See event details.' }
    ];
    data.forEach((d,i) => {
      rect(board, `Registration state / card ${i}`, 20, d.y, 350, 184, C.white, 18);
      rect(board, `Registration state / rail ${i}`, 20, d.y+17, 3, 150, C.green, 2);
      rect(board, `Registration state / badge ${i}`, 36, d.y+16, 100, 27, C.paleGreen, 14);
      text(board, `Registration state / badge label ${i}`, 'CONFIRMED', 47, d.y+20, 88, 20, 11, '700', C.green);
      text(board, `Registration state / title ${i}`, d.title, 36, d.y+50, 303, 36, 19, '700', C.ink, true);
      text(board, `Registration state / when ${i}`, d.when, 36, d.y+93, 306, 22, 12, '500', C.ink);
      text(board, `Registration state / note ${i}`, d.note, 36, d.y+119, 307, 38, 12, '400', C.muted);
      text(board, `Registration state / action ${i}`, i === 0 ? 'Open chat  →' : 'View event  →', 236, d.y+153, 117, 22, 13, '700', C.navy);
    });
  } else if (index === 2) {
    rect(board, 'Registration state / wait card', 20, 282, 350, 218, C.white, 18);
    for (const yy of [302,312,322,332,342,352,362,372,382,392,402,412,422,432,442,452,462,472]) rect(board, 'Registration state / dotted rail ' + yy, 20, yy, 2, 5, C.blue, 1);
    rect(board, 'Registration state / wait badge', 36, 300, 92, 27, C.paleBlue, 14);
    text(board, 'Registration state / wait badge label', 'WAITLIST', 49, 304, 76, 20, 11, '700', C.blue);
    text(board, 'Registration state / wait title', 'Open Studio Saturday', 36, 339, 306, 36, 20, '700', C.ink, true);
    text(board, 'Registration state / wait when', 'Sat, 26 Apr  ·  2:00–5:00 PM', 36, 382, 298, 22, 13, '500', C.ink);
    text(board, 'Registration state / wait position', 'You are #3 on the waitlist', 36, 412, 300, 24, 13, '600', C.navy);
    text(board, 'Registration state / wait note', 'We will let you know if a spot becomes available.', 36, 440, 302, 42, 12, '400', C.muted);
    text(board, 'Registration state / wait action', 'View event  →', 245, 471, 108, 23, 13, '700', C.navy);
    rect(board, 'Registration state / wait explainer', 20, 516, 350, 111, C.paleBlue, 18);
    text(board, 'Registration state / wait explainer title', 'How the waitlist works', 36, 529, 300, 28, 17, '700', C.ink, true);
    text(board, 'Registration state / wait explainer copy', 'A freed spot triggers a notification. Your place is not yet confirmed.', 36, 563, 307, 55, 13, '400', C.muted);
  } else {
    rect(board, 'Registration state / past card', 20, 282, 350, 206, C.white, 18);
    rect(board, 'Registration state / past rail', 20, 299, 3, 170, C.gray, 2);
    rect(board, 'Registration state / past badge', 36, 299, 66, 27, C.paleGray, 14);
    text(board, 'Registration state / past badge label', 'PAST', 50, 303, 48, 20, 11, '700', C.gray);
    text(board, 'Registration state / past title', 'Heritage at Dusk', 36, 339, 300, 36, 20, '700', C.ink, true);
    text(board, 'Registration state / past when', 'Sat, 5 Apr  ·  5:00–7:00 PM', 36, 382, 290, 22, 13, '500', C.ink);
    text(board, 'Registration state / past note', 'This event has ended. Its chat is archived and read-only.', 36, 411, 298, 47, 12, '400', C.muted);
    text(board, 'Registration state / past action', 'View event  →', 245, 457, 108, 23, 13, '700', C.navy);
    rect(board, 'Registration state / past callout', 20, 504, 350, 93, C.sand, 18);
    text(board, 'Registration state / past callout title', 'Your memories stay yours', 36, 517, 305, 27, 16, '700', C.ink, true);
    text(board, 'Registration state / past callout copy', 'Event chats close after 72 hours unless a report needs review.', 36, 550, 307, 43, 12, '400', C.muted);
  }
}
for (const state of states) {
  for (const [i, name] of names.entries()) {
    const tab = [...state.board.children].find(s => s.name === `My Events final / tab ${name}`);
    tap(tab, states[i].board);
  }
}
return states.map(s => ({ name: s.board.name, id: s.board.id, children: s.board.children.length }));
