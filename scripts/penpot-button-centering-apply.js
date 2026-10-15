if(penpot.currentPage.id!=='2714a049-ae7d-81a2-8008-b3966a11b139'||!storage.buttonCentering)throw Error('Inspect desktop labels first');
const work=storage.buttonCentering;work.cursor=work.cursor||0;
if(!work.backup){await penpot.currentFile.saveVersion('Before desktop button centering • 2026-10-11');work.backup=true;}
const batch=work.pairs.slice(work.cursor,work.cursor+96),token=penpot.history.undoBlockBegin();let centered=0;
try{for(const p of batch){const face=penpot.currentPage.getShapeById(p.face),label=penpot.currentPage.getShapeById(p.label);if(!face||!label)throw Error('Missing button pair '+p.faceName);const padding=face.width<=64?4:8;label.growType='fixed';label.resize(face.width-padding*2,face.height);label.x=face.x+padding;label.y=face.y;label.align='center';label.verticalAlign='center';work.cursor++;centered++;}}finally{penpot.history.undoBlockFinish(token);}
return {centered,total:work.cursor,remaining:work.pairs.length-work.cursor};
