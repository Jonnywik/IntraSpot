if(penpot.currentPage.id!=='2714a049-ae7d-81a2-8008-b3966a11b139')throw Error('Desktop page required');
const walk=s=>[s,...(s.children||[]).flatMap(walk)];
const hidden=s=>{for(let p=s;p;p=p.parent)if(p.hidden)return true;return false;};
const pairs=[],unmatched=[];
for(const b of penpot.currentPage.root.children.filter(b=>b.type==='board'&&!b.hidden)){
 const ss=walk(b),texts=ss.filter(s=>s.type==='text'&&!hidden(s));
 for(const face of ss.filter(s=>s.type==='rectangle'&&!hidden(s)&&s.height>=32&&s.height<=64&&s.width>=32&&s.width<=700)){
  if(/search|composer|input|field|filter chip|text area/i.test(face.name))continue;
  const actionable=face.interactions.some(i=>i.trigger==='click');const known=/^(Action \/|Appearance \/|Hover \/ appearance|Index \/)|button|disabled|Final hit \/|QA \/ Open index/i.test(face.name);
  if(!actionable&&!known)continue;
  const exact=texts.find(t=>t.name===face.name+' / label'||t.name===face.name+' label');
  const contained=texts.filter(t=>t.x>=face.x-1&&t.x+t.width<=face.x+face.width+8&&t.y>=face.y-1&&t.y+t.height<=face.y+face.height+8);
  const label=exact||(contained.length===1?contained[0]:contained.find(t=>/label/.test(t.name)));
  if(!label){unmatched.push({board:b.name,face:face.name,contained:contained.map(t=>t.name)});continue;}
  if(pairs.some(p=>p.label===label.id))continue;
  pairs.push({board:b.id,boardName:b.name,face:face.id,faceName:face.name,label:label.id,labelName:label.name,copy:label.characters,align:label.align,verticalAlign:label.verticalAlign,x:label.x,y:label.y,w:label.width,h:label.height,faceX:face.x,faceY:face.y,faceW:face.width,faceH:face.height,actions:label.interactions.map(i=>({trigger:i.trigger,type:i.action.type,d:i.action.destination?.id}))});
 }
}
storage.buttonCentering={pairs,unmatched};
return {page:penpot.currentPage.id,pairs,unmatched};
