const info=(await penpotUtils.getPages()).find(p=>p.name.startsWith('Desktop'));
await penpot.openPage(info.id);
const board=[...penpot.currentPage.root.children].find(b=>b.name.startsWith('10 • Guest'));
const changed=[];
for(const s of [...board.children]) if(s.type==='text'){
  const next=s.characters.replaceAll('Stories Within the Walls','Stories in the Walls').replaceAll('PLM Culture Circle','PLM Culture & Arts');
  if(next!==s.characters){s.characters=next;changed.push({name:s.name,text:s.characters});}
}
return changed;
