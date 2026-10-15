const {by,walk}=storage.desktopFinal;
const b=by('10M'),card=walk(b).find(s=>s.name==='Responsive / Event card • 680 px');
for(const s of [...b.children].filter(s=>s.name.startsWith('Action / Register from feed')||s.name.startsWith('Action / Open event details'))){const x=s.x,y=s.y-40;card.appendChild(s);s.x=x;s.y=y;s.constraintsHorizontal='right';s.constraintsVertical='top';}
walk(b).find(s=>s.name==='Responsive / Discovery controls • flexible row').flex.dir='row-reverse';
const chat=by('53'),subtitle=walk(chat).find(s=>s.name==='Final / active subtitle'),list=walk(chat).find(s=>s.name==='Responsive / Conversation list • fixed width');const x=subtitle.x,y=subtitle.y;list.appendChild(subtitle);subtitle.x=x;subtitle.y=y;subtitle.bringToFront();
return {fixed:true,actions:walk(card).filter(s=>s.name.startsWith('Action')).map(s=>({name:s.name,y:s.y-b.y})),searchX:walk(b).find(s=>s.name==='Responsive / Search control').x-b.x};
