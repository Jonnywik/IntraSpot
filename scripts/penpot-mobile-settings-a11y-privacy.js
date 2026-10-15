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
  text(b,'Settings detail / subtitle',subtitle,55,163,305,39,12,'400',C.muted);
  tap([...b.children].find(s=>s.name==='Settings detail / back'),settings);
  return b;
}
const access=shell('M25','M25 • Settings / Accessibility',0,3840,'Accessibility','Make every interaction comfortable.');
text(access,'Settings detail / text label','TEXT SIZE',20,218,200,20,11,'700',C.blue);
rect(access,'Settings detail / text panel',20,244,350,127,C.white,18);
text(access,'Settings detail / text explanation','Choose what feels easiest to read.',36,258,300,22,13,'400',C.muted);
rect(access,'Settings detail / segment shell',36,292,318,59,C.sand,15);
rect(access,'Settings detail / segment selected',40,296,101,51,C.white,12);
text(access,'Settings detail / text default','Default',43,312,95,25,13,'700',C.navy,false,'center');
text(access,'Settings detail / text large','Large',145,312,95,25,13,'500',C.muted,false,'center');
text(access,'Settings detail / text largest','Extra large',246,312,101,25,12,'500',C.muted,false,'center');
text(access,'Settings detail / display label','DISPLAY & MOTION',20,394,220,20,11,'700',C.blue);
rect(access,'Settings detail / display panel',20,420,350,158,C.white,18);
rect(access,'Settings detail / display rule',36,498,318,1,C.line);
text(access,'Settings detail / contrast title','High contrast',36,433,225,25,16,'600',C.ink);
text(access,'Settings detail / contrast note','Sharper text and boundaries',36,461,230,21,12,'400',C.muted);
rect(access,'Settings detail / contrast track',306,438,48,28,C.paleGray,14);
ellipse(access,'Settings detail / contrast knob',309,441,22,C.white);
text(access,'Settings detail / motion title','Reduced motion',36,512,225,25,16,'600',C.ink);
text(access,'Settings detail / motion note','Calmer transitions throughout',36,540,230,21,12,'400',C.muted);
rect(access,'Settings detail / motion track',306,517,48,28,C.paleGray,14);
ellipse(access,'Settings detail / motion knob',309,520,22,C.white);
rect(access,'Settings detail / preview panel',20,599,350,120,C.paleBlue,18);
text(access,'Settings detail / preview eyebrow','LIVE PREVIEW',36,613,180,20,10,'700',C.blue);
text(access,'Settings detail / preview title','Stories in the Walls',36,638,300,31,19,'700',C.ink,true);
text(access,'Settings detail / preview copy','Clear labels, gentle movement, and room to breathe.',36,675,307,38,12,'400',C.muted);

const privacy=shell('M26','M26 • Settings / Privacy',470,3840,'Privacy','You choose who can see your profile.');
text(privacy,'Settings detail / privacy eyebrow','PROFILE VISIBILITY',20,217,215,20,11,'700',C.blue);
const options=[
  {y:244,title:'Only me',copy:'Your profile stays hidden by default.',selected:true},
  {y:344,title:'People at my events',copy:'Visible only where you opt in.',selected:false},
  {y:444,title:'IntraSpot members',copy:'Broader visibility, only if you choose it.',selected:false}
];
for(const [i,o] of options.entries()){
  rect(privacy,`Settings detail / privacy option ${i}`,20,o.y,350,88,o.selected?C.paleBlue:C.white,16);
  ellipse(privacy,`Settings detail / privacy radio ${i}`,36,o.y+29,23,o.selected?C.navy:C.line);
  if(o.selected) ellipse(privacy,`Settings detail / privacy radio center ${i}`,43,o.y+36,9,C.white);
  text(privacy,`Settings detail / privacy title ${i}`,o.title,73,o.y+15,270,27,16,'700',C.ink);
  text(privacy,`Settings detail / privacy copy ${i}`,o.copy,73,o.y+47,272,34,12,'400',C.muted);
}
rect(privacy,'Settings detail / privacy assurance',20,567,350,102,C.sand,18);
text(privacy,'Settings detail / privacy assurance title','Your PLM email stays private',36,581,304,27,17,'700',C.ink,true);
text(privacy,'Settings detail / privacy assurance copy','It verifies access but is never displayed on your public profile.',36,617,307,46,12,'400',C.muted);
text(privacy,'Settings detail / privacy saved','Saved automatically in this prototype',38,689,314,22,11,'500',C.muted,false,'center');

for(const [key,b] of [['Accessibility',access],['Privacy',privacy]]){
  const hit=rect(settings,`Settings final / tap ${key}`,20,key==='Accessibility'?377:453,350,76,C.white,0);
  hit.opacity=0;tap(hit,b);
}
return [{name:access.name,id:access.id},{name:privacy.name,id:privacy.id}];
