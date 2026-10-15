const walk=s=>[s,...[...(s.children||[])].flatMap(walk)];
const live=[...penpot.currentPage.root.children].filter(b=>b.type==='board'&&!b.hidden);
let grayText=0,focusSelection=0;
for(const b of live)for(const s of walk(b)){
 if(s.hidden||!Array.isArray(s.fills))continue;
 if(s.type==='text'&&s.fills.some(f=>f.fillColor?.toLowerCase()==='#68758a')){s.fills=s.fills.map(f=>f.fillColor?.toLowerCase()==='#68758a'?{...f,fillColor:'#536481'}:f);grayText++;}
 if(/focus|underline|selected|selection/i.test(s.name)){
  if(s.fills.some(f=>f.fillColor?.toLowerCase()==='#c9933a')){s.fills=s.fills.map(f=>f.fillColor?.toLowerCase()==='#c9933a'?{...f,fillColor:'#A97018'}:f);focusSelection++;}
  if(s.strokes?.some(f=>f.strokeColor?.toLowerCase()==='#c9933a')){s.strokes=s.strokes.map(f=>f.strokeColor?.toLowerCase()==='#c9933a'?{...f,strokeColor:'#A97018'}:f);focusSelection++;}
 }
}
return {grayText,focusSelection,decorativeGold:'Preserved #C9933A',functionalGold:'#A97018',scope:'Desktop light-mode functional states'};
