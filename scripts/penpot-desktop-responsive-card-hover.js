const T=storage.responsiveTools,{walk,shadow,groupBoard}=T;
const originals=new Set(storage.responsiveBaseline.shapes.filter(s=>s.type==='board'&&s.parent==='00000000-0000-0000-0000-000000000000'&&!s.hidden).map(s=>s.id));
const candidates=[...penpot.currentPage.root.children].filter(b=>originals.has(b.id)).map(b=>({b,card:walk(b).find(s=>s.name==='Responsive / Event card • 680 px')})).filter(p=>p.card&&!p.card.getPluginData('desktop-card-hover'));
const done=[];
for(const {b,card} of candidates.slice(0,2)){
 const ss=walk(card),open=ss.find(s=>s.name==='Action / Open event details')?.interactions.find(i=>i.trigger==='click')?.action;
 if(!open){card.setPluginData('desktop-card-hover','no activation');continue;}
 const o=card.clone();penpot.currentPage.root.appendChild(o);o.name='91 • Card hover / '+b.name;o.x=26000+(done.length%2)*760;o.y=17000+[...penpot.currentPage.root.children].filter(s=>s.getPluginData('desktop-card-source')).length*650;o.showInViewMode=false;o.clipContent=false;o.setPluginData('desktop-card-source',card.id);
 const os=walk(o),shell=os.find(s=>s.name==='Event card / shell');shell.y-=4;shell.shadows=shadow(1);
 const photo=os.find(s=>s.name==='Final attendee / event photo');if(photo){const x=photo.x-o.x,y=photo.y-o.y,w=photo.width,h=photo.height;const crop=groupBoard(o,'Hover / Preserved image crop',[photo],x,y,w,h);crop.clipContent=true;crop.borderRadius=12;photo.resize(w*1.025,h*1.025);photo.x=crop.x-w*.0125;photo.y=crop.y-h*.0125;crop.addInteraction('click',open);}
 for(const s of [shell,os.find(s=>s.name==='Event card / title')].filter(Boolean))s.addInteraction('click',open);
 o.addInteraction('mouse-leave',{type:'close-overlay',destination:o,animation:{type:'dissolve',duration:220,easing:'ease-out'}});
 for(const s of [ss.find(s=>s.name==='Event card / shell'),ss.find(s=>s.name==='Event card / title'),ss.find(s=>s.name==='Final attendee / event photo')].filter(Boolean)){
  if(!s.interactions.some(i=>i.trigger==='click'))s.addInteraction('click',open);
 }
 card.addInteraction('mouse-enter',{type:'open-overlay',destination:o,relativeTo:card,position:'center',addBackgroundOverlay:false,closeWhenClickOutside:true,animation:{type:'dissolve',duration:220,easing:'ease-out'}});
 card.setPluginData('desktop-card-hover',o.id);done.push({source:b.name,overlay:o.id});
}
return {done,remaining:candidates.length-Math.min(2,candidates.length),nativeEffect:'Dissolve between two localized appearances; continuous transform remains specified'};
