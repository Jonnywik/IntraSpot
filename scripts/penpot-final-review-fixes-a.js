if(penpot.currentPage.id!=='2714a049-ae7d-81a2-8008-b3966a11b139'||!storage.finalReviewBackup)throw Error('Desktop review backup required');
const by=id=>penpot.currentPage.getShapeById(id),before=storage.finalReviewBaseline.shapes,map=new Map(before.map(s=>[s.id,s]));
function hidden(s){return s.hidden||(s.parent&&map.has(s.parent)?hidden(map.get(s.parent)):false);}
const edits=[],token=penpot.history.undoBlockBegin();
try {
 for(const p of before.filter(s=>s.type==='text'&&!hidden(s)&&s.characters==='Continue as sample student')){const s=by(p.id);s.characters='Continue as sample PLM attendee';edits.push({id:s.id,change:'Faculty-inclusive action copy'});}
 for(const p of before.filter(s=>s.type==='text'&&!hidden(s)&&s.name==='Final / archived status')){const s=by(p.id);s.fontSize='14';s.lineHeight='1.35';s.resize(s.width,24);edits.push({id:s.id,change:'Readable archived/read-only label'});}
 const divider=by('0790ece5-2133-80b3-8008-c56eaa0e949c'),heading=by('0790ece5-2133-80b3-8008-c56eaa0e949d'),board=by('0790ece5-2133-80b3-8008-c56eaa0e9469');
 divider.y=board.y+564;heading.y=board.y+580;edits.push({id:divider.id,change:'Compact sheet divider spacing'},{id:heading.id,change:'Heading clear of fixed footer'});
 const helper=by('0790ece5-2133-80b3-8008-c572ecacc5c9'),stress=by('0790ece5-2133-80b3-8008-c572ecac915e');helper.resize(helper.width,48);helper.y=stress.y+930;helper.lineHeight='1.5';edits.push({id:helper.id,change:'Two-line larger-text helper fits'});
 const hover=by('0790ece5-2133-80b3-8008-c5719d3e5e65');if(hover){hover.name='90 • Hover / Continue as sample PLM attendee / 10';const raw=hover.getPluginData('desktop-hover-key');if(raw){const key=JSON.parse(raw);key[0]='Continue as sample PLM attendee';hover.setPluginData('desktop-hover-key',JSON.stringify(key));}}
 storage.finalReviewEditsA=edits;
} finally {penpot.history.undoBlockFinish(token);}
return {edited:edits.length,edits,scope:'Desktop Penpot only; actions, mobile and backend unchanged'};
