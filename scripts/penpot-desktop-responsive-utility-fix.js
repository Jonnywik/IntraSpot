const {walk,by}=storage.responsiveTools;let profiles=0,filters=0,reduced=0;
const ids=new Set(storage.responsiveBaseline.shapes.filter(s=>s.type==='board'&&s.parent==='00000000-0000-0000-0000-000000000000'&&!s.hidden&&!/^(00|01|02|03) /.test(s.name)).map(s=>s.id));
for(const b of [...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden&&ids.has(b.id))){
 const ss=walk(b);for(const s of ss.filter(s=>!s.hidden&&['Utility / avatar','Utility / avatar initials','Utility / profile'].includes(s.name))){if(/Guest/.test(b.name))continue;if(!s.interactions.some(i=>i.trigger==='click')){s.addInteraction('click',{type:'navigate-to',destination:by('60')});profiles++;}}
 const label=ss.find(s=>s.name==='Filter / label'),face=ss.find(s=>s.name==='Discover / My Clubs');if(label&&face&&!face.interactions.some(i=>i.trigger==='click')){const i=label.interactions.find(i=>i.trigger==='click');if(i){face.addInteraction('click',i.action);filters++;}}
 if(/^(50B|51) /.test(b.name))for(const s of ss)for(const i of [...s.interactions]){if(!i.action.animation)continue;const a={...i.action};delete a.animation;const trigger=i.trigger;i.remove();s.addInteraction(trigger,a);reduced++;}
}
return {profileUtilitiesLinked:profiles,wholeMyClubsControlsLinked:filters,reducedTransitionsRemoved:reduced};
