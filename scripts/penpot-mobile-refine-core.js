const { C, rect, text, ellipse, clean, tap } = storage.IS;
const info = (await penpotUtils.getPages()).find(p => p.name === 'Mobile • Light');
await penpot.openPage(info.id);
const boards = [...penpot.currentPage.root.children].filter(s => s.type === 'board');
const find = prefix => boards.find(b => b.name.startsWith(prefix));

const events = find('M11');
clean(events, ['My Events / card', 'Pending status', 'My Events / event title', 'My Events / date', 'My Events / detail', 'My Events / view']);
clean(events, ['Pending']);
text(events, 'Pending / section label', 'AWAITING CONFIRMATION', 20, 253, 250, 19, 11, '700', C.blue);
rect(events, 'Pending / first card', 20, 282, 350, 184, C.white, 18);
rect(events, 'Pending / first rail', 20, 299, 3, 150, C.gold, 2);
rect(events, 'Pending / first badge', 36, 298, 88, 27, C.paleAmber, 14);
text(events, 'Pending / first badge label', 'PENDING', 48, 302, 75, 20, 11, '700', C.amber);
text(events, 'Pending / first title', 'Stories in the Walls', 36, 332, 290, 34, 20, '700', C.ink, true);
text(events, 'Pending / first schedule', 'Sat, 12 Apr  ·  9:00–11:00 AM', 36, 375, 298, 22, 13, '500', C.ink);
text(events, 'Pending / first note', 'The organizer will review your request.', 36, 403, 300, 27, 13, '400', C.muted);
text(events, 'Pending / first action', 'View event  →', 247, 436, 106, 24, 13, '700', C.navy);
rect(events, 'Pending / second card', 20, 480, 350, 178, C.white, 18);
rect(events, 'Pending / second rail', 20, 498, 3, 143, C.gold, 2);
rect(events, 'Pending / second badge', 36, 496, 88, 27, C.paleAmber, 14);
text(events, 'Pending / second badge label', 'PENDING', 48, 500, 75, 20, 11, '700', C.amber);
text(events, 'Pending / second title', 'City Sketch Exchange', 36, 532, 305, 34, 20, '700', C.ink, true);
text(events, 'Pending / second schedule', 'Fri, 18 Apr  ·  3:00–5:00 PM', 36, 574, 300, 22, 13, '500', C.ink);
text(events, 'Pending / second note', 'You will be notified when a spot is confirmed.', 36, 602, 300, 38, 13, '400', C.muted);
text(events, 'Pending / second action', 'View event  →', 247, 630, 106, 24, 13, '700', C.navy);
tap(events.children.find(s => s.name === 'Pending / first action'), find('M14'));

const chat = find('M12');
clean(chat, ['Chat card', 'Chat icon', 'Chat name', 'Chat preview']);
clean(chat, ['Chat']);
text(chat, 'Chat / section active', 'YOUR EVENT CONVERSATIONS', 20, 204, 270, 20, 11, '700', C.blue);
rect(chat, 'Chat / list', 20, 235, 350, 302, C.white, 18);
for (const y of [335, 436]) rect(chat, 'Chat / divider ' + y, 88, y, 263, 1, C.line);
const rows = [
  { y: 245, initials: 'SW', title: 'Stories in the Walls', preview: 'Mika: See you at the main gate!', time: 'Now', color: C.paleBlue },
  { y: 346, initials: 'CE', title: 'City Sketch Exchange', preview: 'Lia: Bring your favorite sketchbook.', time: '2h', color: C.sand },
  { y: 447, initials: 'CM', title: 'Community Makers', preview: 'Organizer: Details are in the event.', time: 'Tue', color: C.paleGreen }
];
rows.forEach((row, index) => {
  ellipse(chat, `Chat / avatar ${index}`, 36, row.y+10, 42, row.color);
  text(chat, `Chat / initials ${index}`, row.initials, 45, row.y+20, 26, 21, 11, '700', C.navy, false, 'center');
  text(chat, `Chat / title ${index}`, row.title, 91, row.y+5, 225, 28, 17, '700', C.ink, true);
  text(chat, `Chat / time ${index}`, row.time, 317, row.y+11, 34, 20, 11, '500', C.muted, false, 'right');
  text(chat, `Chat / preview ${index}`, row.preview, 91, row.y+38, 255, 39, 12, '400', C.muted);
});
text(chat, 'Chat / section archived', 'RECENTLY ENDED', 20, 563, 250, 20, 11, '700', C.blue);
rect(chat, 'Chat / archived row', 20, 590, 350, 125, C.white, 18);
ellipse(chat, 'Chat / archived avatar', 36, 608, 42, C.paleGray);
text(chat, 'Chat / archived initials', 'HD', 45, 619, 26, 21, 11, '700', C.gray, false, 'center');
text(chat, 'Chat / archived title', 'Heritage at Dusk', 91, 604, 235, 29, 17, '700', C.ink, true);
rect(chat, 'Chat / archived status', 91, 638, 119, 22, C.paleGray, 11);
text(chat, 'Chat / archived status label', 'ARCHIVED · READ ONLY', 100, 642, 110, 18, 10, '700', C.gray);
text(chat, 'Chat / archived countdown', 'Deletes in 2 days, 14 hours', 91, 670, 245, 23, 12, '500', C.muted);
text(chat, 'Chat / archived arrow', '→', 329, 642, 25, 25, 18, '500', C.gray);

const settings = find('M13');
clean(settings, ['Settings / Appearance', 'Settings / Language', 'Settings / Accessibility', 'Settings / Privacy']);
clean(settings, ['Settings']);
text(settings, 'Settings / section preferences', 'PREFERENCES', 20, 198, 180, 20, 11, '700', C.blue);
rect(settings, 'Settings / preference panel', 20, 225, 350, 306, C.white, 18);
for (const y of [301,377,453]) rect(settings, 'Settings / rule ' + y, 36, y, 318, 1, C.line);
const pref = [
  { y: 237, name: 'Appearance', note: 'Light is selected', value: 'Light' },
  { y: 313, name: 'Language', note: 'English is selected', value: 'English' },
  { y: 389, name: 'Accessibility', note: 'Text size, contrast & motion', value: 'Edit' },
  { y: 465, name: 'Privacy', note: 'Profile hidden by default', value: 'Edit' }
];
pref.forEach((row, index) => {
  text(settings, `Settings / row ${index} title`, row.name, 36, row.y, 220, 25, 16, '600', C.ink);
  text(settings, `Settings / row ${index} note`, row.note, 36, row.y+27, 240, 22, 12, '400', C.muted);
  text(settings, `Settings / row ${index} value`, row.value + '  ›', 276, row.y+12, 78, 25, 13, '600', C.navy, false, 'right');
});
text(settings, 'Settings / section discovery', 'DISCOVERY', 20, 552, 180, 20, 11, '700', C.blue);
rect(settings, 'Settings / discovery panel', 20, 578, 350, 138, C.white, 18);
rect(settings, 'Settings / discovery divider', 36, 646, 318, 1, C.line);
text(settings, 'Settings / area title', 'Preferred area', 36, 590, 220, 25, 16, '600', C.ink);
text(settings, 'Settings / area note', 'Optional · change or clear anytime', 36, 616, 240, 20, 12, '400', C.muted);
text(settings, 'Settings / area action', 'Set  ›', 298, 601, 56, 23, 13, '600', C.navy, false, 'right');
text(settings, 'Settings / availability title', 'Availability', 36, 656, 220, 25, 16, '600', C.ink);
text(settings, 'Settings / availability note', 'Optional time windows', 36, 682, 240, 20, 12, '400', C.muted);
text(settings, 'Settings / availability action', 'Set  ›', 298, 667, 56, 23, 13, '600', C.navy, false, 'right');
return { refined: [events.name, chat.name, settings.name], shapes: [events, chat, settings].map(b => [b.name, b.children.length]) };
