const { C, rect, text, ellipse, clean, tap }=storage.IS;
const info=(await penpotUtils.getPages()).find(p=>p.name==='Mobile • Light');
await penpot.openPage(info.id);
const root=penpot.currentPage.root;
const boards=()=>[...root.children].filter(s=>s.type==='board');
const base=boards().find(b=>b.name.startsWith('M13'));
function shell(prefix,name,x,y,title,subtitle){
  let b=boards().find(b=>b.name.startsWith(prefix));
  if(!b){b=base.clone();b.name=name;b.x=x;b.y=y;}
  clean(b,['Settings','Screen title','Screen subtitle','Utility final']);
  for(const s of [...b.children]) if(s.name.includes('selected line')) s.hidden=true;
  text(b,'Utility final / back','‹',20,119,30,42,30,'400',C.navy);
  text(b,'Utility final / title',title,55,123,310,37,25,'700',C.ink,true);
  text(b,'Utility final / subtitle',subtitle,55,163,310,37,12,'400',C.muted);
  tap([...b.children].find(s=>s.name==='Utility final / back'),boards().find(b=>b.name.startsWith('M10')));
  return b;
}
const profile=shell('M34','M34 • Member / Profile',2350,4800,'Your profile','A little about the person behind the plans.');
rect(profile,'Utility final / profile card',20,221,350,220,C.white,18);
ellipse(profile,'Utility final / profile avatar',36,239,68,C.paleBlue);
text(profile,'Utility final / profile initials','AR',49,261,42,28,20,'700',C.navy,false,'center');
text(profile,'Utility final / profile name','Ari Reyes',119,244,226,36,23,'700',C.ink,true);
text(profile,'Utility final / profile role','PLM member · sample profile',119,284,226,23,12,'500',C.muted);
rect(profile,'Utility final / profile badge',36,330,131,26,C.paleGreen,13);
text(profile,'Utility final / profile badge label','PLM ACCESS ACTIVE',48,335,112,18,10,'700',C.green);
text(profile,'Utility final / profile privacy','Visible only to you by default',36,377,300,24,13,'500',C.muted);
text(profile,'Utility final / profile edit','Edit profile  →',250,409,105,23,13,'700',C.navy);
text(profile,'Utility final / interest eyebrow','YOUR INTERESTS',20,465,200,20,11,'700',C.blue);
rect(profile,'Utility final / interest panel',20,491,350,105,C.white,18);
rect(profile,'Utility final / interest chip one',36,510,128,34,C.paleBlue,17);
text(profile,'Utility final / interest chip one label','Arts & culture',48,519,104,20,12,'600',C.navy,false,'center');
rect(profile,'Utility final / interest chip two',174,510,118,34,C.sand,17);
text(profile,'Utility final / interest chip two label','History walks',184,519,98,20,12,'600',C.navy,false,'center');
text(profile,'Utility final / interest note','Personalized suggestions use these choices.',36,558,305,25,12,'400',C.muted);
rect(profile,'Utility final / privacy panel',20,619,350,94,C.paleBlue,18);
text(profile,'Utility final / privacy title','Privacy is in your hands',36,633,310,27,17,'700',C.ink,true);
text(profile,'Utility final / privacy copy','Choose per-event or broader visibility in Settings.',36,671,305,38,12,'400',C.muted);

const notices=shell('M35','M35 • Member / Notifications',2820,4800,'Notifications','Updates about events that matter to you.');
text(notices,'Utility final / notices today','TODAY',20,215,150,19,11,'700',C.blue);
rect(notices,'Utility final / notices panel',20,242,350,339,C.white,18);
for(const y of [354,466]) rect(notices,'Utility final / notices divider '+y,36,y,318,1,C.line);
const rows=[
  {y:253,color:C.paleGreen,initial:'✓',title:'You are confirmed',copy:'Community Makers Market is in My Events.',time:'9:18 AM'},
  {y:365,color:C.paleAmber,initial:'·',title:'Request sent',copy:'Stories in the Walls is awaiting review.',time:'Yesterday'},
  {y:477,color:C.paleBlue,initial:'i',title:'A spot may open',copy:'Your waitlist position is now #3.',time:'Monday'}
];
rows.forEach((r,i)=>{
  ellipse(notices,`Utility final / notice icon ${i}`,36,r.y+11,37,r.color);
  text(notices,`Utility final / notice glyph ${i}`,r.initial,46,r.y+19,17,18,13,'700',C.navy,false,'center');
  text(notices,`Utility final / notice title ${i}`,r.title,88,r.y+6,245,26,17,'700',C.ink,true);
  text(notices,`Utility final / notice copy ${i}`,r.copy,88,r.y+38,247,38,12,'400',C.muted);
  text(notices,`Utility final / notice time ${i}`,r.time,88,r.y+80,247,18,10,'500',C.muted);
});
rect(notices,'Utility final / notices note',20,600,350,113,C.sand,18);
text(notices,'Utility final / notices note title','No hidden surprises',36,615,300,28,17,'700',C.ink,true);
text(notices,'Utility final / notices note copy','Registration, waitlist, and chat-expiry changes appear here. This screen uses sample updates.',36,652,307,54,12,'400',C.muted);

const memberMain=['M10','M11','M12','M13','M16','M17','M18'];
for(const prefix of memberMain){
  const b=boards().find(b=>b.name.startsWith(prefix));if(!b)continue;
  clean(b,['Utility final']);
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4" fill="none" stroke="#0E3473" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const bell=penpot.createShapeFromSvg(svg);bell.name='Utility final / bell';bell.x=b.x+288;bell.y=b.y+60;b.appendChild(bell);
  ellipse(b,'Utility final / avatar',331,54,34,C.paleBlue);
  text(b,'Utility final / avatar label','AR',338,64,20,17,10,'700',C.navy,false,'center');
  const bellTap=rect(b,'Utility final / bell tap',277,49,44,44,C.white);bellTap.opacity=0;tap(bellTap,notices);
  const avatarTap=rect(b,'Utility final / avatar tap',325,49,44,44,C.white);avatarTap.opacity=0;tap(avatarTap,profile);
}
const guest=boards().find(b=>b.name.startsWith('M00'));
clean(guest,['Utility final']);
rect(guest,'Utility final / guest sign in',287,53,82,34,C.paleBlue,17);
text(guest,'Utility final / guest sign in label','Sign in',298,62,60,20,12,'700',C.navy,false,'center');
tap([...guest.children].find(s=>s.name==='Utility final / guest sign in'),boards().find(b=>b.name.startsWith('M30')));
return [{name:profile.name,id:profile.id},{name:notices.name,id:notices.id}];
