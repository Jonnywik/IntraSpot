const T=storage.responsiveTools,{walk,C,rect,text,stroke,shadow}=T;
const ids=new Set(storage.responsiveBaseline.shapes.filter(s=>s.type==='board'&&s.parent==='00000000-0000-0000-0000-000000000000'&&!s.hidden&&!/^(00|01|02|03) /.test(s.name)).map(s=>s.id));
const roots=[...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden&&(ids.has(b.id)||b.getPluginData('desktop-sheet-source')));
const cache=new Map([...penpot.currentPage.root.children].filter(b=>b.type==='board'&&b.getPluginData('desktop-hover-key')).map(b=>[b.getPluginData('desktop-hover-key'),b]));
let created=0,wired=0,skipped=0;
const pairs=roots.flatMap(b=>walk(b).filter(s=>s.type==='rectangle'&&!s.hidden&&s.height>=40&&s.height<=64&&s.width>=70&&s.width<800&&!s.getPluginData('desktop-hover-wired')&&s.interactions.some(i=>i.trigger==='click'&&['navigate-to','open-overlay'].includes(i.action.type))).map(s=>({b,s})));
for(const {b,s} of pairs.slice(0,36)){
 if(/disabled|send disabled|search hit/i.test(s.name)){s.setPluginData('desktop-hover-wired','skipped');skipped++;continue;}
 const ss=walk(b),nav=s.name.toLowerCase().startsWith('final hit /');
 const label=ss.find(t=>t.type==='text'&&t.name===s.name+' / label')||ss.find(t=>t.type==='text'&&!t.hidden&&t.x>=s.x-1&&t.x+t.width<=s.x+s.width+8&&t.y>=s.y&&t.y+t.height<=s.y+s.height+5);
 if(!label){s.setPluginData('desktop-hover-wired','no label');skipped++;continue;}
 const click=s.interactions.find(i=>i.trigger==='click'&&['navigate-to','open-overlay'].includes(i.action.type)).action;
 const fill=s.fills?.[0]?.fillColor?.toLowerCase(),primary=fill===C.navy.toLowerCase(),duration=nav?180:140,reduced=/^(50B|51) /.test(b.name);
 const key=JSON.stringify([label.characters,Math.round(s.width),Math.round(s.height),click.type,click.destination.id,primary,nav,reduced]);let o=cache.get(key);
 if(!o){o=penpot.createBoard();o.name='90 • Hover / '+label.characters+' / '+cache.size;o.x=18000+(cache.size%10)*360;o.y=14000+Math.floor(cache.size/10)*104;o.resize(s.width+8,s.height+8);o.fills=[];o.clipContent=false;o.showInViewMode=false;o.setPluginData('desktop-hover-key',key);
 const y=nav||reduced?4:2,face=rect(o,'Hover / appearance',4,y,s.width,s.height,primary?'#0B2A5F':C.paleBlue,12);face.strokes=stroke(primary?'#0B2A5F':C.blue,1);if(!nav&&!reduced)face.shadows=shadow(1);
 const t=text(o,'Hover / label',label.characters,label.x-s.x+4,label.y-s.y+y,label.width,label.height,Number(label.fontSize),primary?C.white:C.navy);const font=penpot.fonts.findByName('Inter Tight');font.applyToText(t,font.variants.find(v=>v.fontWeight===label.fontWeight&&v.fontStyle==='normal'));t.align=label.align;
 face.addInteraction('click',click);t.addInteraction('click',click);o.addInteraction('mouse-leave',{type:'close-overlay',destination:o,...(reduced?{}:{animation:{type:'dissolve',duration,easing:'ease-out'}})});cache.set(key,o);created++;}
 s.addInteraction('mouse-enter',{type:'open-overlay',destination:o,relativeTo:s,position:'center',closeWhenClickOutside:true,addBackgroundOverlay:false,...(reduced?{}:{animation:{type:'dissolve',duration,easing:'ease-out'}})});
 s.setPluginData('desktop-hover-wired',o.id);wired++;
}
return {created,wired,skipped,remaining:pairs.length-Math.min(pairs.length,36),totalHoverBoards:cache.size};
