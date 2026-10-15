const {walk}=storage.responsiveTools;let badges=0;
for(const b of [...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden)){
 const ss=walk(b),bg=ss.find(s=>s.name==='Queue / badge bg'),label=ss.find(s=>s.name==='Queue / badge'),outline=ss.find(s=>s.name==='Queue / badge / outline');if(bg&&label){label.x=bg.x+40;label.y=bg.y+7;label.resize(bg.width-52,label.height);if(outline){outline.x=bg.x+14;outline.y=bg.y+9;}badges++;}
 if(b.getPluginData('desktop-stress'))for(const name of ['Event card / date','Event card / social']){const label=ss.find(s=>s.name===name),icon=ss.find(s=>s.name===name+' / outline');if(label&&icon){icon.x=label.x-26;icon.y=label.y+2.5;}}
}
return {badgeAnchorsCorrected:badges,stressMetadataIconsAligned:true};
