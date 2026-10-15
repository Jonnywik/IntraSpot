const T=storage.responsiveTools;if(!T)throw Error('Restore helpers first');const {C,rect,text,stroke,shadow,icon}=T;
function board(name,x,y,w,h,color=C.canvas){const b=penpot.createBoard();b.name=name;b.x=x;b.y=y;b.resize(w,h);b.fills=color?[{fillColor:color,fillOpacity:1}]:[];b.clipContent=false;b.setPluginData('desktop-qa','2026-10-11');return b;}
function strong(s,weight='600'){const f=penpot.fonts.findByName(s.fontFamily);f.applyToText(s,f.variants.find(v=>v.fontWeight===weight&&v.fontStyle==='normal'));return s;}
const existing=[...penpot.currentPage.root.children].find(b=>b.name==='80 • QA / Responsive & Motion Guide');if(existing)return {existing:existing.id};
const q=board('80 • QA / Responsive & Motion Guide',18000,0,1440,1060);
text(q,'QA / eyebrow','DESKTOP FINAL • RESPONSIVE & MOTION QA',40,32,1100,24,13,C.blue);
text(q,'QA / title','Comfortable space. Confident feedback.',40,76,1340,56,32,C.ink,true);
text(q,'QA / introduction','PLM identity retained. Desktop journeys refined; mobile and backend unchanged.',40,142,1330,32,16,C.muted);
const states=['Default','Hover','Pressed','Keyboard focus','Selected','Disabled','Loading','Success'];const comps={};
for(let i=0;i<states.length;i++){const state=states[i],x=40+(i%4)*344,y=196+Math.floor(i/4)*212;const tile=rect(q,'QA / '+state+' tile',x,y,320,188,C.white,16);tile.strokes=stroke();strong(text(q,'QA / '+state+' heading',state,x+20,y+16,280,26,16));
 const sample=board('Control / Primary / '+state,q.x+x+20,q.y+y+58,280,56,null);q.appendChild(sample);
 const face=rect(sample,'Appearance / '+state,4,4,272,state==='Pressed'?46:48,state==='Disabled'?C.paleGray:state==='Success'?C.green:state==='Hover'?'#16458A':C.navy,12);face.constraintsHorizontal='leftright';face.constraintsVertical='top';if(state==='Hover')face.shadows=shadow(1);if(state==='Pressed')face.y+=1;
 if(state==='Keyboard focus'){const ring=rect(sample,'Focus / gold ring',0,0,280,56,C.white,16);ring.fills=[];ring.strokes=stroke('#A97018',2);ring.sendToBack();ring.constraintsHorizontal='leftright';face.strokes=stroke(C.white,2);}
 if(state==='Selected'){face.strokes=stroke('#A97018',2);}
 const comp=penpot.library.local.createComponent([sample]);comp.name='Primary — '+state;comp.path='IntraSpot / Desktop Final';comps[state]=comp.id;
 const wording=state==='Loading'?'Loading…':state==='Success'?'Confirmed':state==='Selected'?'Selected':'View event';strong(text(q,'QA / '+state+' label',wording,x+28,y+74,256,26,15,state==='Disabled'?C.muted:C.white)).align='center';
 const copy={Default:'48 px control · 12 px corners',Hover:'2 px lift · depth · 140 ms',Pressed:'Slight compression · specified', 'Keyboard focus':'Distinct gold ring · specified',Selected:'Gold border + clear state',Disabled:'No lift, hover, or activation',Loading:'Labelled · stable control width',Success:'One brief check · 200 ms'}[state];text(q,'QA / '+state+' note',copy,x+20,y+134,280,44,14,C.muted);
}
rect(q,'QA / interaction notes',40,654,1360,164,C.sand,16);
strong(text(q,'QA / native heading','Native examples and handoff-only effects',64,674,1280,30,20));
text(q,'QA / native copy','Native: hover overlays, click destinations, dissolve/slide transitions, fixed scrolling elements, and simulated outcomes.\nSpecified: true keyboard-focus and mouse-down triggers, continuous cropped-image scaling, spring settling, and independent nested scroll.',64,720,1290,82,16,C.muted);
text(q,'QA / rules title','Motion rules',40,850,1300,38,24,C.ink,true);
text(q,'QA / rules','Normal: expressive but brief feedback. Reduced: instant color, border, and status changes; static decoration.\nHeritage movement is isolated in its own preview flow. Never loop a full application screen.\nHeuristic/structural checks are not participant testing or a completed live presentation review.',40,901,1300,112,16,C.muted);
penpot.currentPage.setPluginData('desktop-final-components',JSON.stringify(comps));
storage.responsiveTools.board=board;storage.responsiveTools.strong=strong;
return {guide:q.id,components:comps};
