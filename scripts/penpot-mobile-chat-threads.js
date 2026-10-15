const { C, rect, text, ellipse, clean, tap } = storage.IS;
const info=(await penpotUtils.getPages()).find(p=>p.name==='Mobile • Light');
await penpot.openPage(info.id);
const root=penpot.currentPage.root;
const boards=()=>[...root.children].filter(s=>s.type==='board');
const inbox=boards().find(b=>b.name.startsWith('M12'));
const specs=[
  { prefix:'M23', name:'M23 • Member / Chat / Active thread', x:3290, y:2880, archived:false },
  { prefix:'M24', name:'M24 • Member / Chat / Archived thread', x:3760, y:2880, archived:true }
];
for(const s of specs){
  let b=boards().find(b=>b.name.startsWith(s.prefix));
  if(!b){ b=inbox.clone(); b.name=s.name; b.x=s.x; b.y=s.y; }
  s.board=b;
  clean(b,['Chat','Screen title','Screen subtitle','Thread final']);
  text(b,'Thread final / back','‹',20,119,32,42,30,'400',C.navy);
  text(b,'Thread final / title',s.archived?'Heritage at Dusk':'Stories in the Walls',55,123,312,37,23,'700',C.ink,true);
  text(b,'Thread final / subtitle',s.archived?'Event ended · history preserved briefly':'28 attendees · confirmed members only',55,163,305,22,12,'400',C.muted);
  rect(b,'Thread final / rule',20,194,350,1,C.line);
  if(!s.archived){
    rect(b,'Thread final / context',20,210,350,70,C.paleBlue,16);
    text(b,'Thread final / context label','EVENT REMINDER',36,219,172,18,10,'700',C.blue);
    text(b,'Thread final / context when','12 Apr · 9:00 AM · Intramuros',36,240,300,24,13,'600',C.ink);
    text(b,'Thread final / today','TODAY',170,291,50,19,10,'700',C.muted,false,'center');
    ellipse(b,'Thread final / avatar one',20,322,32,C.paleGreen);
    text(b,'Thread final / avatar one letters','ML',27,330,20,17,10,'700',C.green,false,'center');
    rect(b,'Thread final / message one',62,317,278,88,C.white,16);
    text(b,'Thread final / message one by','Mika · 9:34 AM',75,324,225,19,11,'700',C.navy);
    text(b,'Thread final / message one copy','See you at the main gate! Bring water for the walk.',75,346,248,49,13,'400',C.ink);
    text(b,'Thread final / subtle menu one','···',342,333,24,20,13,'500','#B9C1CE');
    rect(b,'Thread final / message self',93,426,277,75,C.paleBlue,16);
    text(b,'Thread final / self by','You · 9:38 AM',106,434,235,19,11,'700',C.navy);
    text(b,'Thread final / self copy','Looking forward to it. I will be there early.',106,456,245,38,13,'400',C.ink);
    ellipse(b,'Thread final / avatar two',20,522,32,C.sand);
    text(b,'Thread final / avatar two letters','CA',27,530,20,17,10,'700',C.amber,false,'center');
    rect(b,'Thread final / message two',62,517,278,95,C.white,16);
    text(b,'Thread final / message two by','PLM Culture & Arts · 9:40 AM',75,524,252,19,11,'700',C.navy);
    text(b,'Thread final / message two copy','We will start on time. The gathering point is beside the gate.',75,547,246,53,13,'400',C.ink);
    text(b,'Thread final / subtle menu two','···',342,536,24,20,13,'500','#B9C1CE');
    rect(b,'Thread final / composer',20,674,350,62,C.white,18);
    text(b,'Thread final / composer prompt','Message your event group…',36,693,263,25,13,'400',C.muted);
    ellipse(b,'Thread final / send',325,686,38,C.navy);
    text(b,'Thread final / send arrow','→',334,693,22,24,19,'600',C.white,false,'center');
  }else{
    rect(b,'Thread final / archived context',20,211,350,94,C.paleGray,16);
    text(b,'Thread final / archived eyebrow','ARCHIVED · READ ONLY',36,222,215,20,11,'700',C.gray);
    text(b,'Thread final / archived countdown','Deletes in 2 days, 14 hours',36,249,300,25,14,'700',C.ink);
    text(b,'Thread final / archived note','This chat closed 72 hours after the event ended.',36,275,308,22,11,'400',C.muted);
    text(b,'Thread final / last day','EVENT DAY',160,321,70,19,10,'700',C.muted,false,'center');
    ellipse(b,'Thread final / archived avatar',20,357,32,C.paleGray);
    text(b,'Thread final / archived avatar letters','HD',27,365,20,17,10,'700',C.gray,false,'center');
    rect(b,'Thread final / archived message one',62,352,278,95,C.white,16);
    text(b,'Thread final / archived by one','Organizer · 6:15 PM',75,359,228,19,11,'700',C.gray);
    text(b,'Thread final / archived copy one','Thank you for sharing the evening with us. Take care on your way home.',75,382,246,55,13,'400',C.muted);
    rect(b,'Thread final / archived message two',93,469,277,78,C.paleGray,16);
    text(b,'Thread final / archived by two','You · 6:22 PM',106,477,220,19,11,'700',C.gray);
    text(b,'Thread final / archived copy two','A beautiful night. Thanks, everyone!',106,500,242,40,13,'400',C.muted);
    rect(b,'Thread final / composer disabled',20,660,350,76,C.paleGray,18);
    text(b,'Thread final / composer disabled title','Conversation closed',36,670,300,24,14,'700',C.gray);
    text(b,'Thread final / composer disabled note','You can read messages until deletion.',36,695,300,25,12,'400',C.muted);
  }
  tap([...b.children].find(x=>x.name==='Thread final / back'),inbox);
}
const row=inbox.children.find(s=>s.name==='Chat / list');
if(row && !row.interactions.length) tap(row,specs[0].board);
const old=inbox.children.find(s=>s.name==='Chat / archived row');
if(old && !old.interactions.length) tap(old,specs[1].board);
return specs.map(s=>({name:s.board.name,id:s.board.id,children:s.board.children.length}));
