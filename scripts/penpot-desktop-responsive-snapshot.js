if(penpot.currentPage.id!=='2714a049-ae7d-81a2-8008-b3966a11b139')throw new Error('Desktop page required');
const walk=s=>[s,...[...(s.children||[])].flatMap(walk)];
const props=['id','name','type','x','y','width','height','hidden','blocked','opacity','borderRadius','borderRadiusTopLeft','borderRadiusTopRight','borderRadiusBottomLeft','borderRadiusBottomRight','fills','strokes','shadows','constraintsHorizontal','constraintsVertical','fixedWhenScrolling','clipContent','showInViewMode','characters','fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','align','growType'];
const serialize=s=>{const out={parent:s.parent?.id,index:s.parentIndex};for(const p of props){try{const v=s[p];if(v!==undefined)out[p]=v;}catch{}}out.interactions=[...(s.interactions||[])].map(i=>{const a=i.action;return {trigger:i.trigger,delay:i.delay,action:{...a,destination:a.destination?.id,relativeTo:a.relativeTo?.id}};});return JSON.parse(JSON.stringify(out));};
const snapshot={file:penpot.currentFile.id,page:penpot.currentPage.id,created:'2026-10-11',shapes:walk(penpot.currentPage.root).map(serialize)};
storage.responsiveBaseline=snapshot;
return snapshot;
