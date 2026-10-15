const {walk}=storage.responsiveTools;const q=[...penpot.currentPage.root.children].find(b=>b.name==='80 • QA / Responsive & Motion Guide');let moved=0;
for(const state of ['Default','Hover','Pressed','Keyboard focus','Selected','Disabled','Loading','Success']){
 const sample=penpot.library.local.components.find(c=>c.path==='IntraSpot / Desktop Final'&&c.name==='Primary — '+state)?.mainInstance(),label=walk(q).find(s=>s.name==='QA / '+state+' label');if(sample&&label&&label.parent.id!==sample.id){sample.appendChild(label);label.constraintsHorizontal='leftright';label.constraintsVertical='top';moved++;}
}
return {labelsIncludedInReusableComponent:moved};
