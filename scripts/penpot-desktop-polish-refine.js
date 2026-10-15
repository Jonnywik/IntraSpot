if(!storage.desktopFinal)throw new Error('Reload the desktop helper batch before refinement.');
const {C,walk,by,route,replace,links,button}=storage.desktopFinal;
const all=()=>[...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden);
function rect(b,name,x,y,w,h,color,radius=0){const s=penpot.createRectangle();s.name=name;s.x=b.x+x;s.y=b.y+y;s.resize(w,h);s.fills=[{fillColor:color,fillOpacity:1}];s.borderRadius=radius;b.appendChild(s);return s;}
function text(b,name,value,x,y,w,h,size=14,weight='400',color=C.ink,serif=false){const s=penpot.createText(value);s.name=name;s.x=b.x+x;s.y=b.y+y;s.growType='fixed';s.resize(w,h);s.fontFamily=serif?'Noto Serif Georgian':'Inter Tight';s.fontSize=String(size);s.fontWeight=String(weight);s.fills=[{fillColor:color,fillOpacity:1}];b.appendChild(s);return s;}
const feed=by('10M'),club=by('10C'),guest=by('10'),detail=by('11M');
// Give every persistent-navigation item a distinct, comfortable hit target.
let targets=0;for(const b of all().filter(b=>!/^0[012] /.test(b.name))){const ss=walk(b);for(const s of [...b.children])if(s.name.startsWith('Final hit /'))s.remove();
 const selected=/My Events/.test(b.name)?'My Events':/^(52|53|54) /.test(b.name)?'Chat':/^5[01][AB]? /.test(b.name)?'Settings':/^(10|11|12|13|14|15|16|49)/.test(b.name)?'Discover':null;
 for(const s of ss.filter(s=>s.type==='text'&&(/^(Action \/ Nav |Nav \/)/.test(s.name)||s.name==='Action / My Events nav'))){const key=['Discover','My Events','Chat','Settings'].find(k=>s.characters===k);if(!key)continue;const widths={Discover:100,'My Events':116,Chat:64,Settings:95};s.resize(widths[key],s.height);s.fontWeight=key===selected?'700':'500';s.fills=[{fillColor:key===selected?C.navy:C.blue,fillOpacity:1}];const d=[...s.interactions].find(i=>i.action.type==='navigate-to')?.action.destination;if(d){const hit=rect(b,'Final hit / '+key,s.x-b.x-7,19,widths[key]+14,44,C.white,10);hit.opacity=0;route(hit,d);targets++;}}
 for(const name of ['Utility / notifications','Utility / profile','Utility / avatar initials']){const s=ss.find(s=>s.name===name);if(!s)continue;const d=[...s.interactions].find(i=>i.action.type==='navigate-to')?.action.destination;if(d){const hit=rect(b,'Final hit / '+name,s.x-b.x-4,19,Math.max(44,s.width+8),44,C.white,10);hit.opacity=0;route(hit,d);targets++;}}
 for(const s of ss)if(s.type==='rectangle'&&/^Final \/.*(panel|context|composer)$/.test(s.name))s.strokes=[{strokeColor:C.line,strokeWidth:1,strokeStyle:'solid',strokeAlignment:'center',strokeOpacity:1}];
}
// Keep status meaning consistent with the established green/blue/amber system.
const wait=by('16W'),confirmed=by('16C');
for(const [b,bg,fg] of [[wait,C.paleBlue,C.blue],[confirmed,C.paleGreen,C.green]]){for(const s of walk(b)){if(s.type==='rectangle'&&s.y-b.y>240&&s.y-b.y<275&&s.width>400)s.fills=[{fillColor:bg,fillOpacity:1}];if(s.name==='Result / status')s.fills=[{fillColor:fg,fillOpacity:1}];}}
for(const s of [...wait.children])if(s.name.startsWith('Final / waitlist dot'))s.remove();for(let y=268;y<329;y+=7)rect(wait,'Final / waitlist dot '+y,933,y,2,2,C.blue,1);
replace(by('60'),'Final / privacy note','Your persona stays hidden unless you opt in. Profile images are optional; when supplied, they may be seen by confirmed attendees of the same event.');
replace(by('53'),'Final / eyebrow','PLM COMMUNITY  /  EVENT CHAT');replace(by('54'),'Final / eyebrow','PLM COMMUNITY  /  ARCHIVED EVENT CHAT');by('53').name='53 • Member / Chat / Active thread';by('54').name='54 • Member / Chat / Archived thread';
const noticeRow=walk(by('61')).find(s=>s.name==='Final / notice row 0');route(noticeRow,confirmed);
replace(by('16'),'Action / View in My Events / label','View My Events');
replace(feed,'Feed / subheading','For you: matches your interest in arts & culture.');
// Present sample search and composed-club search as explicit prototype states.
function searchState(prefix,name,base,x,y,clubOn=false,empty=false){let b=by(prefix);if(!b){b=base.clone();b.name=prefix+' • '+name;b.x=x;b.y=y;}
 replace(b,'Feed / eyebrow',clubOn?'DISCOVER • MY CLUBS • SEARCH':'DISCOVER • SEARCH');replace(b,'Feed / heading',empty?'No matching events':'Search results');replace(b,'Feed / subheading',empty?'Try another event or organization name.':clubOn?'1 event from your active clubs matching “Culture”.':'1 public event matching “Culture”.');replace(b,'Search / placeholder',empty?'Astronomy':'Culture');
 for(const s of [...b.children])if(s.name==='Final / search clear'||s.name==='Final / empty message'||s.name==='Final / empty title'||s.name==='Final / sample empty entry'||s.name==='Final / full event entry')s.remove();
 const clear=text(b,'Final / search clear','Clear',722,298,61,25,14,'600',C.blue);route(clear,base);
 replace(b,'Feed / public note','Sample search matches event and organization names — no venue search.');
 if(empty){for(const s of [...b.children])if(/^(Event card|Action \/ Register from feed|Action \/ Open event details|Final attendee)/.test(s.name))s.remove();rect(b,'Final / empty panel',380,360,680,350,C.white,18);text(b,'Final / empty title','A fresh search might help',412,445,596,41,27,'700',C.ink,true);text(b,'Final / empty message','Search an event title or the publishing organization. You can also clear your filters to see more events.',412,507,596,65,16,'400',C.muted);button(b,'Final / reset search','Clear search',412,605,190,base,true);}
 return b;
}
const result=searchState('10S','Member / Discover / Search',feed,10640,4220);
const clubResult=searchState('10CS','Member / Discover / My Clubs and Search',club,12160,4220,true);
const guestResult=searchState('10GS','Guest / Discover / Search',guest,13680,4220);
const empty=searchState('10E','Member / Discover / Empty search',feed,15200,4220,false,true);
for(const [b,d] of [[feed,result],[club,clubResult],[guest,guestResult]])for(const s of walk(b))if(/^Search \/ (field|surface|background|placeholder|icon)$/.test(s.name))route(s,d);
// Existing search-surface names can vary, so put one transparent target over the field.
for(const [b,d] of [[feed,result],[club,clubResult],[guest,guestResult]]){for(const s of [...b.children])if(s.name==='Final / search hit')s.remove();const hit=rect(b,'Final / search hit',380,278,420,64,C.white,14);hit.opacity=0;route(hit,d);}
for(const b of [result,clubResult,guestResult]){const r=text(b,'Final / sample empty entry','Preview a search with no matches →',380,910,590,27,14,'600',C.blue);route(r,empty);const note=walk(b).find(s=>s.name==='Feed / public note');if(note)note.y=b.y+948;b.resize(1440,990);}
for(const s of walk(result))if(/Discover \/ My Clubs|Filter \/ label/.test(s.name))route(s,clubResult);
for(const s of walk(clubResult))if(/Discover \/ My Clubs active|Filter \/ label/.test(s.name))route(s,result);
// Comment-reading destination: use the same desktop sheet, with no new moderation rules.
let comments=by('11D');if(!comments){comments=detail.clone();comments.name='11D • Member / Event comments';comments.x=10640;comments.y=5300;}
for(const s of [...comments.children])if(s.x-comments.x>=900&&s.y-comments.y>=78)s.remove();
text(comments,'Final / comments title','Event conversation',928,91,462,52,30,'700',C.ink,true);text(comments,'Final / comments subtitle','Stories in the Walls · sample comments',928,161,462,34,14,'400',C.muted);
rect(comments,'Final / reaction panel',928,221,484,64,C.paleBlue,14);text(comments,'Final / reaction count','24 interested · interest is not attendance',948,242,440,26,14,'600',C.navy);
[['Mika Santos','Looking forward to learning more about our campus.'],['PLM Culture & Arts','Bring water and comfortable shoes for the walk.']].forEach(([name,copy],i)=>{const y=323+i*161;rect(comments,'Final / comment '+i,928,y,484,133,C.canvas,14);text(comments,'Final / comment sender '+i,name,948,y+17,382,24,14,'600',C.navy);text(comments,'Final / comment text '+i,copy,948,y+57,397,57,15,'400',C.ink);text(comments,'Final / comment options '+i,'···',1361,y+18,31,28,17,'500',C.muted);});
rect(comments,'Final / comment composer',928,679,484,90,C.canvas,14);text(comments,'Final / comment composer copy','Sample comment field — no message is submitted.',948,706,440,43,14,'400',C.muted);
button(comments,'Final / comments return','Back to event details',928,822,484,detail);links(comments,'Action / Close panel',detail);
for(const b of [feed,club,detail]){const s=walk(b).find(s=>s.name=== (b===detail?'Details / comments':'Event card / social'));route(s,comments);}
storage.desktopFinal.addedStates=[result,clubResult,guestResult,empty,comments].map(b=>({id:b.id,name:b.name}));
return {navigationHitTargets:targets,newStates:storage.desktopFinal.addedStates,waitlist:'Blue with fine dotted rail',profileCopy:'Aligned with canonical privacy rules'};
