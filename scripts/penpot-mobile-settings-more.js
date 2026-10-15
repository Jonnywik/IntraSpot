const { C, rect, text, ellipse, clean, tap }=storage.IS;
const info=(await penpotUtils.getPages()).find(p=>p.name==='Mobile • Light');
await penpot.openPage(info.id);
const root=penpot.currentPage.root;
const boards=()=>[...root.children].filter(s=>s.type==='board');
const settings=boards().find(b=>b.name.startsWith('M13'));
function shell(prefix,name,x,y,title,subtitle){
  let b=boards().find(b=>b.name.startsWith(prefix));
  if(!b){b=settings.clone();b.name=name;b.x=x;b.y=y;}
  clean(b,['Settings','Screen title','Screen subtitle','Settings detail']);
  text(b,'Settings detail / back','‹',20,120,30,42,30,'400',C.navy);
  text(b,'Settings detail / title',title,55,123,310,37,25,'700',C.ink,true);
  text(b,'Settings detail / subtitle',subtitle,55,163,305,42,12,'400',C.muted);
  tap([...b.children].find(s=>s.name==='Settings detail / back'),settings);
  return b;
}
const appearance=shell('M27','M27 • Settings / Appearance',940,3840,'Appearance','A warm day mode and a calmer night mode.');
text(appearance,'Settings detail / theme eyebrow','CHOOSE YOUR THEME',20,220,220,20,11,'700',C.blue);
rect(appearance,'Settings detail / light border',20,248,167,267,C.gold,18);
rect(appearance,'Settings detail / light card',22,250,163,263,C.canvas,16);
text(appearance,'Settings detail / light brand','IntraSpot',34,265,138,31,20,'700',C.red,true);
rect(appearance,'Settings detail / light sample card',34,308,139,129,C.white,13);
rect(appearance,'Settings detail / light image',43,319,121,57,C.sand,9);
text(appearance,'Settings detail / light image label','PLM · CULTURE',51,339,108,21,10,'700',C.blue);
text(appearance,'Settings detail / light sample title','Stories in the Walls',43,387,123,31,12,'700',C.ink,true);
rect(appearance,'Settings detail / light sample button',43,442,121,28,C.navy,9);
text(appearance,'Settings detail / light sample button label','View event',57,449,95,18,11,'600',C.white,false,'center');
text(appearance,'Settings detail / light name','Light',34,478,110,23,14,'700',C.ink);
text(appearance,'Settings detail / light check','✓',153,478,20,23,15,'700',C.navy);
rect(appearance,'Settings detail / dark border',203,248,167,267,C.line,18);
rect(appearance,'Settings detail / dark card',205,250,163,263,'#172535',16);
text(appearance,'Settings detail / dark brand','IntraSpot',217,265,138,31,20,'700',C.white,true);
rect(appearance,'Settings detail / dark sample card',217,308,139,129,'#23364A',13);
rect(appearance,'Settings detail / dark image',226,319,121,57,'#354960',9);
text(appearance,'Settings detail / dark image label','PLM · CULTURE',234,339,108,21,10,'700','#D5AD68');
text(appearance,'Settings detail / dark sample title','Stories in the Walls',226,387,123,31,12,'700',C.white,true);
rect(appearance,'Settings detail / dark sample button',226,442,121,28,'#315B99',9);
text(appearance,'Settings detail / dark sample button label','View event',240,449,95,18,11,'600',C.white,false,'center');
text(appearance,'Settings detail / dark name','Dark',217,478,110,23,14,'700',C.white);
rect(appearance,'Settings detail / theme note',20,539,350,115,C.paleBlue,18);
text(appearance,'Settings detail / theme note title','Same experience, two moods',36,555,300,28,18,'700',C.ink,true);
text(appearance,'Settings detail / theme note copy','Both themes keep the same structure, labels, and accessible controls.',36,592,306,48,13,'400',C.muted);

const language=shell('M28','M28 • Settings / Language',1410,3840,'Language','Choose the language you prefer.');
text(language,'Settings detail / language eyebrow','APP LANGUAGE',20,219,200,20,11,'700',C.blue);
rect(language,'Settings detail / English card',20,246,350,98,C.paleBlue,18);
ellipse(language,'Settings detail / English radio',36,279,24,C.navy);
ellipse(language,'Settings detail / English dot',43,286,10,C.white);
text(language,'Settings detail / English title','English',74,259,250,28,17,'700',C.ink);
text(language,'Settings detail / English copy','Current language',74,292,250,24,12,'400',C.muted);
rect(language,'Settings detail / Filipino card',20,357,350,98,C.white,18);
ellipse(language,'Settings detail / Filipino radio',36,390,24,C.line);
text(language,'Settings detail / Filipino title','Filipino',74,370,250,28,17,'700',C.ink);
text(language,'Settings detail / Filipino copy','Switch app labels and guidance',74,403,270,24,12,'400',C.muted);
rect(language,'Settings detail / language note',20,483,350,127,C.sand,18);
text(language,'Settings detail / language note title','Your choice travels with you',36,498,310,30,18,'700',C.ink,true);
text(language,'Settings detail / language note copy','Event titles and organizer-written descriptions stay in the language their authors used.',36,539,307,58,13,'400',C.muted);

const discovery=shell('M29','M29 • Settings / Discovery',1880,3840,'Discovery','Optional choices that shape your feed.');
text(discovery,'Settings detail / discovery eyebrow','PREFERRED AREA',20,219,200,20,11,'700',C.blue);
rect(discovery,'Settings detail / area card',20,246,350,144,C.white,18);
text(discovery,'Settings detail / area title','Where do you like to gather?',36,261,300,28,17,'700',C.ink,true);
rect(discovery,'Settings detail / area field',36,301,318,51,C.canvas,13);
text(discovery,'Settings detail / area prompt','No area selected  ·  Add manually',51,315,282,24,13,'400',C.muted);
text(discovery,'Settings detail / area hint','No live location is used.',36,359,300,20,11,'500',C.muted);
text(discovery,'Settings detail / availability eyebrow','AVAILABILITY',20,412,200,20,11,'700',C.blue);
rect(discovery,'Settings detail / availability card',20,439,350,217,C.white,18);
text(discovery,'Settings detail / availability title','When are you usually free?',36,455,300,28,17,'700',C.ink,true);
text(discovery,'Settings detail / availability note','Add or clear time windows at any time.',36,487,300,24,12,'400',C.muted);
const chips=[['Weekdays',36],['Weekends',150],['Evenings',264]];
for(const [name,x] of chips){rect(discovery,`Settings detail / chip ${name}`,x,526,name==='Weekends'?106:100,35,C.sand,18);text(discovery,`Settings detail / chip label ${name}`,name,x+9,535,name==='Weekends'?89:84,21,12,'600',C.navy,false,'center');}
rect(discovery,'Settings detail / availability action',36,582,318,51,C.navy,13);
text(discovery,'Settings detail / availability action label','Set availability',49,596,291,24,14,'700',C.white,false,'center');
for(const [name,y,b] of [['Appearance',225,appearance],['Language',301,language],['Preferred area',578,discovery],['Availability',646,discovery]]){
  const hit=rect(settings,`Settings final / tap ${name}`,20,y,350,name==='Availability'?70:76,C.white,0);hit.opacity=0;tap(hit,b);
}
return [{name:appearance.name,id:appearance.id},{name:language.name,id:language.id},{name:discovery.name,id:discovery.id}];
