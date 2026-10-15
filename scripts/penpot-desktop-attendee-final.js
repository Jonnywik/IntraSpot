const pages=await penpotUtils.getPages();
const mobile=pages.find(p=>p.name==='Mobile • Light');await penpot.openPage(mobile.id);
const member=[...penpot.currentPage.root.children].find(b=>b.name.startsWith('M10'));
const source=[...member.children].find(s=>s.name==='Event cover / heritage gathering');
const photoFill=JSON.parse(JSON.stringify(source.fills[0]));
const desktop=pages.find(p=>p.name.startsWith('Desktop'));await penpot.openPage(desktop.id);
const boards=[...penpot.currentPage.root.children].filter(s=>s.type==='board');
let copy=0,media=0;
for(const b of boards){
  for(const s of [...b.children]) if(s.type==='text'){
    let next=s.characters;
    next=next.replaceAll('Stories Within the Walls','Stories in the Walls')
      .replaceAll('PLM CULTURE CIRCLE','PLM CULTURE & ARTS')
      .replaceAll('PLM Culture Circle','PLM Culture & Arts')
      .replaceAll('Mon, October 19, 2026','Sat, 12 April')
      .replaceAll('October 19','12 April')
      .replaceAll('Oct 19','Apr 12');
    if(next!==s.characters){s.characters=next;copy++;}
  }
  const background=[...b.children].find(s=>s.name==='Background / image');
  if(background){background.fills=[photoFill];background.borderRadius=14;media++;}
}
for(const [prefix,x,y,w,h] of [['10 • Guest',404,454,632,218],['11 • Guest',928,220,484,220]]){
  const b=boards.find(s=>s.name.startsWith(prefix));
  for(const s of [...b.children]) if(s.name==='Final attendee / event photo') s.remove();
  const p=penpot.createRectangle();p.name='Final attendee / event photo';p.x=b.x+x;p.y=b.y+y;p.resize(w,h);p.borderRadius=12;p.fills=[photoFill];b.appendChild(p);media++;
}
return {copyChanges:copy,photoSurfaces:media};
