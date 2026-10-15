const {C,walk,by,replace,icon,stroke,shadow}=storage.responsiveTools;
let cards=0,large=0,icons=0;
const ids=new Set(storage.responsiveBaseline.shapes.filter(s=>s.type==='board'&&s.parent==='00000000-0000-0000-0000-000000000000'&&!s.hidden&&!/^(00|01|02|03) /.test(s.name)).map(s=>s.id));
const boards=[...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden&&ids.has(b.id)&&!b.getPluginData('responsive-finish-v1')).slice(0,8);
for(const b of boards){if(b.getPluginData('responsive-finish-v1'))continue;
 const ss=walk(b),card=ss.find(s=>s.name==='Responsive / Event card • 680 px');if(card){card.y=b.y+330;const entry=ss.find(s=>s.name==='Final / full event entry');if(entry)entry.y=b.y+892;const note=ss.find(s=>s.name==='Feed / public note');if(note)note.y=b.y+936;b.resize(b.width,1000);cards++;}
 if(/^(50T|51) /.test(b.name)){const before=new Map(storage.responsiveBaseline.shapes.map(s=>[s.id,s]));for(const s of ss.filter(s=>s.type==='text'&&s.y-b.y>=82)){const old=before.get(s.id);if(old){s.fontSize=old.fontSize;s.lineHeight=old.lineHeight;large++;}}}
 for(const s of ss.filter(s=>s.type==='text'&&!s.hidden)){
  const m=s.characters.match(/^([◷⌖♡☆✓×])\s+/);if(!m)continue;const kind={'◷':'clock','⌖':'pin','♡':'heart','☆':'star','✓':'check','×':'cross'}[m[1]],x=s.x-b.x,y=s.y-b.y,w=s.width,h=s.height,n=s.name,inside=s.parent,color=s.fills?.[0]?.fillColor||C.navy;
  const next=replace(b,n,s.characters.slice(m[0].length));if(!next)continue;const size=Math.min(18,h);next.x+=size+8;next.resize(Math.max(40,w-size-8),h);const i=icon(b,n+' / outline',kind,x,y+Math.max(0,(h-size)/2),size,color);inside.appendChild(i);for(const action of [...next.interactions])i.addInteraction(action.trigger,action.action);icons++;
 }
 for(const s of ss.filter(s=>s.type==='rectangle'&&s.height===48&&s.interactions.some(i=>i.trigger==='click'))){if(s.fills?.some(f=>f.fillColor?.toLowerCase()===C.navy.toLowerCase()))s.shadows=shadow();const label=walk(b).find(t=>t.name===s.name+' / label');if(label&&!label.interactions.length){const a=s.interactions.find(i=>i.trigger==='click');label.addInteraction(a.trigger,a.action);}}
 b.setPluginData('responsive-finish-v1','2026-10-11');
}
return {cards,largeTextRestored:large,outlineIcons:icons};
