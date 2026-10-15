const old=penpot.currentPage.getShapeById('ec34fcb8-3872-805c-8008-b571ba739518');
const ids=['ec34fcb8-3872-805c-8008-b571b9b83af4','ec34fcb8-3872-805c-8008-b571b9e3a5af','ec34fcb8-3872-805c-8008-b571ba14beb4','ec34fcb8-3872-805c-8008-b571ba44c802'];
const names=['Default','Hover','Focus','Disabled'];
if(storage.finalReviewCaptions)return {alreadyAligned:true};
const token=penpot.history.undoBlockBegin(),created=[];
try {for(let i=0;i<ids.length;i++){const face=penpot.currentPage.getShapeById(ids[i]),s=i===0?old:penpot.createText(names[i]);if(i>0){const font=penpot.fonts.findByName('Inter Tight');font.applyToText(s,font.variants.find(v=>v.fontWeight==='400'&&v.fontStyle==='normal'));s.fontSize='12';s.lineHeight='1.25';s.fills=old.fills;old.parent.appendChild(s);}s.characters=names[i];s.name='Actions / state / '+names[i];s.growType='fixed';s.resize(face.width,22);s.x=face.x;s.y=face.y+face.height+8;s.align='center';s.verticalAlign='center';created.push({id:s.id,state:names[i]});}storage.finalReviewCaptions=created;}finally{penpot.history.undoBlockFinish(token);}
return {captions:created};
