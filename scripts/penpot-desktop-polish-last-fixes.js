if(!storage.desktopFinal)throw new Error('Restore desktop helpers first.');
const {C,walk,by,route,replace,links}=storage.desktopFinal;
const undo=penpot.history.undoBlockBegin();
function clone(p,name,base,x,y){let b=by(p);if(!b){b=base.clone();b.name=p+' • '+name;b.x=x;b.y=y;}return b;}
function unlink(s){for(const i of [...s.interactions])i.remove();}
try{
 const pending=clone('11R','Member / Event details / Pending',by('11M'),12160,5300);
 replace(pending,'Panel / subtitle','Pending · Your request is awaiting organizer confirmation.');
 replace(pending,'Action / Register / label','View pending request');links(pending,'Action / Register',by('200'));links(pending,'Action / Close panel',by('200'));
 const past=clone('11P','Member / Event details / Past',by('11M'),13680,5300);
 for(const name of ['Panel / title','Background / preview title'])replace(past,name,'Community Heritage Talk');
 replace(past,'Panel / subtitle','Past · This event has ended.');
 replace(past,'Details / date','Sat, 12 Sep 2026 · 2:00–4:00 PM');
 replace(past,'Details / cost','Free · In person · Registration closed');
 replace(past,'Details / description','A community conversation about our campus and its heritage. This event is retained in your history; registration is closed.');
 replace(past,'Details / comments','Event conversation · historical sample');
 replace(past,'Final / seat counts','Event ended · No places available');
 replace(past,'Action / Register / label','Event ended');
 for(const s of walk(past))if(s.name==='Action / Register'||s.name==='Action / Register / label'){unlink(s);if(s.type==='rectangle')s.fills=[{fillColor:'#DDE2E9',fillOpacity:1}];else s.fills=[{fillColor:C.muted,fillOpacity:1}];}
 const comments=walk(past).find(s=>s.name==='Details / comments');if(comments)unlink(comments);
 links(past,'Action / Close panel',by('203'));
 const destinations=[['200',pending],['201',by('11C')],['202',by('11W')],['203',past],['210',pending],['211',by('11C')],['212',by('11W')],['213',past]];
 const photo=walk(by('11F')).find(s=>s.name==='Background / image');
 for(const [p,d]of destinations){const b=by(p);links(b,'Action / Open event',d);links(b,'Action / Open calendar event',d);links(b,'Action / Discover more',by('10M'));
  for(const s of walk(b))if(s.name==='My Events / image'||s.name==='Calendar / mini art')s.fills=[...photo.fills];
  for(const s of walk(b))if(s.name==='My Events / image stone'||s.name==='My Events / image label')s.hidden=true;
 }
 replace(by('203'),'My Events / event date','Sat, Sep 12, 2026 · 2:00–4:00 PM');
 const large=clone('50T','Settings / Larger text only',by('50'),13680,10600);
 replace(large,'Settings / text size value','A    A   A+');
 replace(large,'Settings / motion explanation','Larger text selected · Contrast, motion, and language are unchanged.');
 for(const s of walk(large))if(s.type==='text'&&/^Settings \//.test(s.name)&&!/(kicker|title|heading|value|state|explanation|subtitle)/.test(s.name)){s.fontSize='18';}
 const language=clone('50L','Settings / Filipino language only',by('50'),15200,10600);
 const translated={'Settings / title':'Gawing iyo ang IntraSpot','Settings / subtitle':'Piliin ang mas komportableng pagbasa at paggamit.','Settings / heading':'Display at wika','Settings / Text size':'Laki ng teksto','Settings / Text size desc':'Baguhin ang laki ng teksto sa IntraSpot.','Settings / High contrast':'Mas mataas na contrast','Settings / High contrast desc':'Gawing mas malinaw ang teksto at mga hangganan.','Settings / Reduced motion':'Bawas galaw','Settings / Reduced motion desc':'Bawasan ang animation at mga epekto ng galaw.','Settings / Language':'Wika','Settings / Language desc':'Piliin ang iyong gustong wika.','Settings / language value':'Filipino  ▾','Settings / motion explanation':'Halimbawang wika: Filipino. Hindi nagbago ang ibang preference.'};
 for(const [n,v]of Object.entries(translated))replace(language,n,v);
 const all=[...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden&&/^5[01][ABTL]? • Settings/.test(b.name));
 for(const b of all){const isLarge=b===large,isLanguage=b===language;
  for(const n of ['Action / Text size','Settings / text size value'])links(b,n,isLarge?by('50'):large);
  for(const n of ['Action / Language','Settings / language value'])links(b,n,isLanguage?by('50'):language);
 }
 // Accessible preview is explicitly a combination, not the result of changing one control.
 replace(by('51'),'Settings / subtitle','Combined accessibility preview · larger text, high contrast, reduced motion, and Filipino.');
 penpot.currentPage.setPluginData('desktop-final-design-pass','2026-10-08 · Desktop only · Static simulated prototype · Final state and route corrections saved');
 return {added:[pending,past,large,language].map(b=>({id:b.id,name:b.name})),calendarAndListDestinations:destinations.map(([p,d])=>({from:p,to:d.name})),mobileUntouched:true};
}finally{penpot.history.undoBlockFinish(undo);}
