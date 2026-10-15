const { C, rect, text, clean, tap }=storage.IS;
const info=(await penpotUtils.getPages()).find(p=>p.name==='Mobile • Light');
await penpot.openPage(info.id);
const root=penpot.currentPage.root;
const boards=()=>[...root.children].filter(s=>s.type==='board');
const feeds=[boards().find(b=>b.name.startsWith('M00')),boards().find(b=>b.name.startsWith('M10'))];
for(const [index,b] of feeds.entries()){
  clean(b,['Feed final']);
  rect(b,'Feed final / featured badge',282,313,74,22,C.paleAmber,11);
  text(b,'Feed final / featured label','FEATURED',292,317,57,16,10,'700',C.amber,false,'center');
  if(index===1){
    const card=[...b.children].find(s=>s.name==='Event card');card.resize(350,446);
    rect(b,'Feed final / reaction rule',35,703,320,1,C.line);
    text(b,'Feed final / reactions','12 reactions  ·  4 comments',35,710,235,19,11,'500',C.muted);
    text(b,'Feed final / action menu','···',327,706,27,19,15,'500','#A9B4C6',false,'center');
  }
}
const sheets=[];
for(const [index,feed] of feeds.entries()){
  const prefix=index===0?'M32':'M33';
  let b=boards().find(s=>s.name.startsWith(prefix));
  if(!b){b=feed.clone();b.name=`${prefix} • ${index===0?'Guest':'Member'} / Sort and explore`;b.x=index*470;b.y=5760;}
  clean(b,['Sort final']);
  const veil=rect(b,'Sort final / veil',0,0,390,844,C.ink);veil.opacity=.32;
  rect(b,'Sort final / sheet',0,447,390,397,C.white,24);
  rect(b,'Sort final / grabber',174,458,42,4,C.line,2);
  text(b,'Sort final / title','Sort and explore',20,483,350,34,23,'700',C.ink,true);
  text(b,'Sort final / explanation','Choose what you want to see first.',20,518,350,24,13,'400',C.muted);
  const options=[['For You','Personalized to your interests',568],['Upcoming','Soonest events first',630],['Newest','Recently published first',692]];
  for(const [i,[label,note,y]] of options.entries()){
    rect(b,`Sort final / option ${i}`,20,y-9,350,57,i===0?C.paleBlue:C.white,13);
    text(b,`Sort final / option name ${i}`,label,36,y,215,23,15,i===0?'700':'600',C.ink);
    text(b,`Sort final / option note ${i}`,note,36,y+23,265,20,11,'400',C.muted);
    if(i===0) text(b,'Sort final / selected check','✓',329,y+10,26,24,17,'700',C.navy,false,'center');
  }
  rect(b,'Sort final / apply',20,769,350,54,C.navy,14);
  text(b,'Sort final / apply label','Show events',34,784,322,27,15,'700',C.white,false,'center');
  tap([...b.children].find(s=>s.name==='Sort final / apply'),feed);
  sheets.push(b);
  const sort=[...feed.children].find(s=>s.name==='Sort and filter / label');
  if(sort){for(const old of [...sort.interactions]) sort.removeInteraction(old);tap(sort,b);}
}
return sheets.map(b=>({name:b.name,id:b.id,children:b.children.length}));
