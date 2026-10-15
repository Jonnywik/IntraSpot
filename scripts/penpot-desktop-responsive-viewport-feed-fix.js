const {walk,by}=storage.responsiveTools;const src=by('10M'),ss=walk(src);const roots=[...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden&&(b.getPluginData('viewport-source')===src.id||/Vertical access \/ 10M/.test(b.name)));let n=0;
for(const b of roots){const center=(b.width-680)/2;for(const s of [...b.children].filter(s=>s.name.startsWith('Feed /')||s.name==='Final / full event entry')){const orig=ss.find(t=>t.name===s.name);if(orig)s.x=b.x+center+(orig.x-src.x-380);}n++;}
return {feedViewportAndVerticalExamplesFixed:n};
