const page=penpot.currentPage;
if(page.id!=='2714a049-ae7d-81a2-8008-b3966a11b139')throw Error('Open the IntraSpot desktop page');
const walk=s=>[s,...[...(s.children||[])].flatMap(walk)];
const properties=['id','name','type','x','y','width','height','hidden','opacity','fills','strokes','shadows','borderRadius','characters','fontFamily','fontSize','fontWeight','lineHeight','align','verticalAlign','growType','fixedWhenScrolling','clipContent'];
const shapes=walk(page.root).map(s=>{const o={parent:s.parent?.id};for(const p of properties){try{if(s[p]!==undefined)o[p]=s[p];}catch{}}o.interactions=[...(s.interactions||[])].map(i=>({trigger:i.trigger,delay:i.delay,action:{...i.action,destination:i.action.destination?.id,relativeTo:i.action.relativeTo?.id}}));return JSON.parse(JSON.stringify(o));});
storage.finalReviewBaseline={page:page.id,shapes};
return {file:penpot.currentFile.id,page:page.id,pageName:page.name,shapes,boards:[...page.root.children].filter(s=>s.type==='board').map(s=>({id:s.id,name:s.name,x:s.x,y:s.y,width:s.width,height:s.height,hidden:s.hidden})),pages:penpot.currentFile.pages.map(p=>({id:p.id,name:p.name}))};
