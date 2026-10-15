if(!storage.desktopFinal)throw new Error('Desktop helper session missing.');
const {C,walk,by,route,replace,links,button}=storage.desktopFinal;
const root=penpot.currentPage.root;
function rect(b,name,x,y,w,h,color,r=0){const s=penpot.createRectangle();s.name=name;s.x=b.x+x;s.y=b.y+y;s.resize(w,h);s.fills=[{fillColor:color,fillOpacity:1}];s.borderRadius=r;b.appendChild(s);return s;}
function text(b,name,value,x,y,w,h,size=14,weight='400',color=C.ink,serif=false){const s=penpot.createText(value);s.name=name;s.x=b.x+x;s.y=b.y+y;s.growType='fixed';s.resize(w,h);s.fontFamily=serif?'Noto Serif Georgian':'Inter Tight';s.fontSize=String(size);s.fontWeight=weight;s.fills=[{fillColor:color,fillOpacity:1}];b.appendChild(s);return s;}
const undo=penpot.history.undoBlockBegin();
try{
 // Only recolor the status callout; preserve image fills behind the sheet.
 const photo=walk(by('11F')).find(s=>s.name==='Background / image');
 for(const p of ['16W','16C']){const image=walk(by(p)).find(s=>s.name==='Background / image');if(photo&&image)image.fills=[...photo.fills];}
 replace(by('00'),'Typography / micro','Noto Serif Georgian for titles · Inter Tight for interface and data');
 // Guests keep public search without inheriting a signed-in empty-state shell.
 let guestEmpty=by('10GE');if(!guestEmpty){guestEmpty=by('10E').clone();guestEmpty.name='10GE • Guest / Discover / Empty search';guestEmpty.x=15200;guestEmpty.y=5300;}
 for(const s of [...guestEmpty.children])if(/Discover \/ My Clubs|Filter \/ label/.test(s.name))s.remove();
 replace(guestEmpty,'Feed / subheading','Search public event and organization names. No sign-in is required to browse.');
 links(guestEmpty,'Final / reset search',by('10'));links(guestEmpty,'Final / search clear',by('10'));
 for(const s of walk(by('10GS')))if(s.name==='Final / sample empty entry')route(s,guestEmpty);
 for(const b of [...root.children].filter(b=>b.type==='board'&&!b.hidden&&/Guest/.test(b.name))){for(const s of walk(b)){if(/^Utility \//.test(s.name)||/^Final hit \/ Utility/.test(s.name))s.hidden=true;if(/^(Nav \/|Action \/ My Events nav|Final hit \/)/.test(s.name)&&/My Events|Chat|Settings/.test(s.name))route(s,by('12'));}
  for(const s of [...b.children])if(s.name==='Final / guest sign in'||s.name==='Final / guest sign in / label')s.remove();
  button(b,'Final / guest sign in','Sign in',1305,18,103,by('12'),true);
 }
 // The guest empty state was cloned from the member shell: route all utilities back to eligibility.
 for(const s of walk(guestEmpty))if(/Nav|nav|Final hit/.test(s.name))route(s,/Discover/.test(s.name)?by('10'):by('12'));
 // Reading from a search result retains the member event destination.
 for(const p of ['10S','10CS']){const s=walk(by(p)).find(s=>s.name==='Event card / social');route(s,by('11D'));}
 for(const p of ['60','61'])for(const s of [...by(p).children])if(s.name==='Final / nav selection')s.hidden=true;
 // A clear front door for review: these are prototype persona journeys, not production role switching.
 let guide=by('03');if(!guide){guide=penpot.createBoard();guide.name='03 • Desktop / Final prototype start';guide.x=3040;guide.y=0;guide.resize(1440,980);guide.fills=[{fillColor:C.canvas,fillOpacity:1}];root.appendChild(guide);}else for(const s of [...guide.children])s.remove();
 text(guide,'Start / brand','IntraSpot',64,43,440,65,44,'700',C.red,true);
 text(guide,'Start / eyebrow','DESKTOP PROTOTYPE · FINAL DESIGN PASS',64,127,1270,25,13,'700',C.blue);
 text(guide,'Start / title','One PLM community. Four journeys.',64,177,1280,65,39,'700',C.ink,true);
 text(guide,'Start / intro','Choose a sample journey to review the desktop experience. All accounts, decisions, and registrations are simulated.',64,259,1260,51,17,'400',C.muted);
 const journeys=[{x:64,y:344,title:'Public visitor',copy:'Browse published events and details. Search without signing in; registration requires simulated PLM eligibility.',dest:by('10'),action:'Browse public events'},
 {x:752,y:344,title:'PLM attendee',copy:'Discover events, use My Clubs, request a place or join the waitlist, and find the result in My Events.',dest:by('10M'),action:'Explore as an attendee'},
 {x:64,y:603,title:'Organization creator',copy:'Apply, draft while pending, review the event preview, and publish only after simulated admin approval.',dest:by('30'),action:'Open organizer journey'},
 {x:752,y:603,title:'Platform administrator',copy:'Review the organization’s accreditation offline, then record an outcome, deciding admin, and date/time.',dest:by('40'),action:'Open admin journey'}];
 for(const [i,j]of journeys.entries()){const r=rect(guide,'Start / card '+i,j.x,j.y,624,232,C.white,18);r.strokes=[{strokeColor:C.line,strokeWidth:1,strokeStyle:'solid',strokeAlignment:'center',strokeOpacity:1}];text(guide,'Start / card title '+i,j.title,j.x+28,j.y+24,560,39,25,'700',C.ink,true);text(guide,'Start / card copy '+i,j.copy,j.x+28,j.y+75,560,69,15,'400',C.muted);button(guide,'Start / action '+i,j.action,j.x+28,j.y+160,568,j.dest);}
 text(guide,'Start / gate','Review-ready visual prototype · Participant testing is still required before frontend implementation.',64,907,1250,28,14,'400',C.muted);
 const oldFlows=[...penpot.currentPage.flows];penpot.currentPage.setPluginData('desktop-final-flow-backup',JSON.stringify(oldFlows.map(f=>({name:f.name,boardId:f.startingBoard?.id}))));
 for(const f of oldFlows)if(/^Flow \d+$/.test(f.name))f.remove();
 for(const [name,board]of [['Desktop — Start here',guide],['Desktop — PLM attendee',by('10M')],['Desktop — Full event and waitlist',by('10F')],['Desktop — Event chat',by('52')]]){if(!penpot.currentPage.flows.some(f=>f.name===name))penpot.currentPage.createFlow(name,board);}
 penpot.currentPage.setPluginData('desktop-final-design-pass','2026-10-08 · desktop only · static simulated prototype');
 storage.desktopFinal.guide={id:guide.id,name:guide.name};
 return {guide:storage.desktopFinal.guide,guestEmpty:{id:guestEmpty.id,name:guestEmpty.name},flows:penpot.currentPage.flows.map(f=>f.name),automaticFlowBackup:true};
}finally{penpot.history.undoBlockFinish(undo);}
