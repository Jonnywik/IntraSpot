const { C, rect, text, ellipse, tap }=storage.IS;
const info=(await penpotUtils.getPages()).find(p=>p.name==='Mobile • Light');
await penpot.openPage(info.id);
const root=penpot.currentPage.root;
const boards=()=>[...root.children].filter(s=>s.type==='board');
const privacy=boards().find(b=>b.name.startsWith('M04'));
const title=[...privacy.children].find(s=>s.name==='Screen title');
title.y=privacy.y+113;title.resize(350,72);
const subtitle=[...privacy.children].find(s=>s.name==='Screen subtitle');subtitle.y=privacy.y+185;
const count=[...privacy.children].find(s=>s.name==='Setup count');count.y=privacy.y+219;
for(const shape of [...privacy.children]){
  const local=shape.y-privacy.y;
  if(local>=237&&local<650&&shape.name!=='Screen title'&&shape.name!=='Screen subtitle'&&shape.name!=='Setup count') shape.y+=25;
}
const start=boards().find(b=>b.name.startsWith('M03'));
function blank(prefix,name,x,y){
  let b=boards().find(b=>b.name.startsWith(prefix));
  if(!b){b=start.clone();b.name=name;b.x=x;b.y=y;}
  for(const s of [...b.children]) if(s.y-b.y>=119) s.remove();
  return b;
}
const choice=blank('M30','M30 • Guest / Simulated eligibility',0,4800);
text(choice,'Eligibility / eyebrow','SIMULATED SIGN-IN',20,122,250,20,11,'700',C.blue);
text(choice,'Eligibility / title','Choose a sample account',20,150,350,70,28,'700',C.ink,true);
text(choice,'Eligibility / intro','This prototype does not ask for your real PLM email.',20,224,350,50,13,'400',C.muted);
rect(choice,'Eligibility / eligible card',20,296,350,165,C.white,18);
ellipse(choice,'Eligibility / eligible icon',36,314,42,C.paleBlue);
text(choice,'Eligibility / eligible initials','PLM',42,328,30,17,11,'700',C.navy,false,'center');
text(choice,'Eligibility / eligible title','PLM student or faculty',91,314,260,30,19,'700',C.ink,true);
text(choice,'Eligibility / eligible copy','Sample Google account ending in .plm.edu.ph. Registration and social actions are available.',36,368,307,64,13,'400',C.muted);
text(choice,'Eligibility / eligible arrow','Continue  →',254,436,98,23,13,'700',C.navy);
rect(choice,'Eligibility / other card',20,477,350,165,C.white,18);
ellipse(choice,'Eligibility / other icon',36,495,42,C.sand);
text(choice,'Eligibility / other letter','G',48,506,19,20,14,'700',C.amber,false,'center');
text(choice,'Eligibility / other title','Other Google account',91,495,260,30,19,'700',C.ink,true);
text(choice,'Eligibility / other copy','Sample non-PLM account. You can browse public events, but cannot join or comment.',36,549,307,64,13,'400',C.muted);
text(choice,'Eligibility / other arrow','Continue  →',254,617,98,23,13,'700',C.navy);
text(choice,'Eligibility / reminder','No real sign-in occurs in this design prototype.',20,685,350,37,12,'400',C.muted,false,'center');

const blocked=blank('M31','M31 • Guest / PLM access needed',470,4800);
ellipse(blocked,'Blocked / icon background',143,176,104,C.paleAmber);
text(blocked,'Blocked / icon','!',182,199,31,52,37,'700',C.amber,false,'center');
text(blocked,'Blocked / title','PLM access needed',20,312,350,47,28,'700',C.ink,true,'center');
text(blocked,'Blocked / explanation','Joining events and taking part in discussions is for current PLM students and faculty.',35,378,320,72,14,'400',C.muted,false,'center');
rect(blocked,'Blocked / note',20,478,350,123,C.white,18);
text(blocked,'Blocked / note title','You can still explore',36,495,318,30,18,'700',C.ink,true);
text(blocked,'Blocked / note copy','Public event listings and details remain available without a PLM account.',36,535,306,56,13,'400',C.muted);
rect(blocked,'Blocked / browse',20,695,350,52,C.navy,14);
text(blocked,'Blocked / browse label','Browse public events',34,710,322,25,15,'700',C.white,false,'center');
const guest=boards().find(b=>b.name.startsWith('M00'));
tap([...choice.children].find(s=>s.name==='Eligibility / eligible card'),start);
tap([...choice.children].find(s=>s.name==='Eligibility / other card'),blocked);
tap([...blocked.children].find(s=>s.name==='Blocked / browse'),guest);
const handoff=boards().find(b=>b.name.startsWith('M02'));
const continueButton=[...handoff.children].find(s=>s.name==='Continue with PLM');
for(const interaction of [...continueButton.interactions]) continueButton.removeInteraction(interaction);
tap(continueButton,choice);
return [{name:privacy.name,children:privacy.children.length},{name:choice.name,id:choice.id},{name:blocked.name,id:blocked.id}];
