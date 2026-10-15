const T=storage.responsiveTools,{walk}=T;
const targets=[...penpot.currentPage.root.children].filter(b=>b.getPluginData('viewport-source')&&!b.getPluginData('viewport-access-fixed'));const done=[];
for(const b of targets.slice(0,2)){
 const ss=walk(b),prefix=b.name.match(/Viewport \/ ([^ ]+)/)?.[1],card=ss.find(s=>s.name==='Responsive / Event card • 680 px');if(card)card.y=b.y+330;
 const full=b.clone();full.name='82 • Vertical access / '+prefix+' / '+b.width+' px';full.x=33000+(done.length%2)*2200;full.y=1000+[...penpot.currentPage.root.children].filter(s=>s.getPluginData('desktop-vertical-source')).length*1300;full.resize(b.width,Math.max(1100,b.height));full.clipContent=false;full.setPluginData('viewport-source','');full.setPluginData('desktop-vertical-source',b.id);
 const fs=walk(full);for(const s of fs.filter(s=>s.name.startsWith('QA / Full vertical content')))s.remove();
 const sheet=fs.find(s=>s.name==='Responsive / Right event sheet • 540 px');if(sheet){sheet.resize(540,1100);const body=walk(sheet).find(s=>s.name==='Responsive / Event sheet body • vertical content');body.clipContent=false;body.resize(540,928);const footer=walk(sheet).find(s=>s.name==='Responsive / Event sheet fixed action footer');footer.y=full.y+1000;walk(sheet).find(s=>s.name==='Panel / surface').resize(540,1100);}
 const messages=fs.find(s=>s.name==='QA / Message scroll viewport');if(messages)messages.clipContent=false;
 for(const s of ss.filter(s=>s.name.startsWith('QA / Full vertical content'))){for(const i of [...s.interactions])i.remove();s.addInteraction('click',{type:'navigate-to',destination:full});}
 full.setPluginData('viewport-access-fixed','companion');b.setPluginData('viewport-access-fixed',full.id);done.push({viewport:b.name,verticalCompanion:full.id});
}
return {done,remaining:targets.length-Math.min(2,targets.length),note:'Same-width vertical access companion; independent nested scroll is specified, not native'};
