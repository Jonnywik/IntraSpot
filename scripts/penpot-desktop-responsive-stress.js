const {walk,by,replace}=storage.responsiveTools;
if([...penpot.currentPage.root.children].some(b=>b.getPluginData('desktop-stress'))){return {existing:true};}
const b=by('10M').clone();b.name='83 • QA / Long Filipino titles & larger text';b.x=33000;b.y=28200;b.resize(1440,1200);b.clipContent=false;b.setPluginData('desktop-stress','2026-10-11');
const card=walk(b).find(s=>s.name==='Responsive / Event card • 680 px');card.resize(680,682);const ss=walk(card);const title=replace(b,'Event card / title','Pagdiriwang ng Sining at Kultura: Mga Kuwentong Nag-uugnay sa Pamantasan');title.fontSize='32';title.resize(620,132);title.lineHeight='1.35';
for(const s of ss){if(s.name==='Event card / title')continue;if(s.name==='Event card / shell')s.resize(680,682);else if(s.y-b.y>=443)s.y+=132;if(s.type==='text'&&!/featured|initials/.test(s.name)){s.fontSize=String(Math.max(16,Number(s.fontSize)));if(s.name.endsWith('/ label'))s.fontSize='16';}}
replace(b,'Feed / heading','Tuklasin ang mga pagtitipon sa PLM');replace(b,'Feed / subheading','Halimbawa ng mas mahabang teksto at mas malaking laki ng letra.');
const note=walk(b).find(s=>s.name==='Feed / public note');note.y=b.y+1140;const entry=walk(b).find(s=>s.name==='Final / full event entry');if(entry)entry.y=b.y+1080;
return {stressBoard:b.id,note:'Text wrapping test only; product copy and current preferences are unchanged'};
