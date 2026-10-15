const {walk,groupBoard}=storage.responsiveTools;const roots=[...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden&&!b.getPluginData('operational-fit-v2')&&(/ • Admin \//.test(b.name)||/Viewport \/ 40|Vertical access \/ 40/.test(b.name)||walk(b).some(s=>s.name==='Responsive / Operational main • flexible content')));const done=[];
for(const b of roots.slice(0,6)){
 const gutter=Math.max(24,(b.width-1200)/2),left=Math.max(264,gutter+168),width=Math.min(1032,b.width-gutter-left);let ss=walk(b),main=ss.find(s=>s.name==='Responsive / Operational main • flexible content');
 const side=ss.find(s=>s.name==='Admin / side');if(side){side.x=b.x;side.y=b.y+72;side.resize(240,b.height-72);side.constraintsVertical='topbottom';for(const s of ss.filter(s=>s!==side&&s.x-b.x<274&&/^Admin \/|^Action \/ Admin/.test(s.name))){if(s.type==='rectangle')s.resize(208,s.height);if(s.type==='text')s.resize(Math.min(s.width,240-(s.x-b.x)-20),Math.max(s.height,24));if(s.name==='Admin / role'){s.y=b.y+b.height-66;s.fixedWhenScrolling=true;}}}
 if(!main){const items=[...b.children].filter(s=>s.x-b.x>=300&&s.y-b.y>=90&&!s.name.startsWith('QA /'));if(items.length)main=groupBoard(b,'Responsive / Operational main • flexible content',items,330,96,1034,Math.max(780,b.height-120));}
 if(main){const oldWidth=main.width,delta=width-oldWidth;main.x=b.x+left;main.resize(width,main.height);main.constraintsHorizontal='leftright';
  for(const s of main.children){let local=s.x-main.x;if(local>=600&&local+s.width>oldWidth-70){s.x+=delta;local=s.x-main.x;}
   const max=width-local-(local>0?24:0);if(s.width>max&&max>=80){const interactive=s.interactions.some(i=>i.trigger==='click');s.resize(max,s.height);if(interactive){for(const i of [...s.interactions])if(i.trigger==='mouse-enter')i.remove();s.setPluginData('desktop-hover-wired','');}if(s.type==='text'&&Number(s.fontSize)<=16)s.resize(max,Math.max(s.height,48));}
   if(s.name==='Admin / subtitle')s.resize(width,48);
  }
 }
 b.setPluginData('operational-fit-v2','2026-10-11');done.push(b.name);
}
return {done,remaining:roots.length-Math.min(6,roots.length)};
