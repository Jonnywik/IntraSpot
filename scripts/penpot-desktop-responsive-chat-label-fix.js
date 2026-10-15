const {walk}=storage.responsiveTools;let count=0;
for(const b of [...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden)){
 const ss=walk(b);for(const sender of ss.filter(s=>s.name.match(/^Final \/ sender [0-9]+$/))){const index=sender.name.match(/[0-9]+$/)[0],bubble=ss.find(s=>s.name==='Final / bubble '+index);if(bubble){sender.y=bubble.y+16;sender.bringToFront();count++;}}
}
return {senderLabelsInsideBubbles:count};
