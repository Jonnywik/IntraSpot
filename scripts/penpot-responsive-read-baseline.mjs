import {readFileSync} from 'node:fs';
const raw=JSON.parse(readFileSync('penpot-desktop-before-responsive-2026-10-11.json','utf8'));
const data=JSON.parse(raw.content.find(x=>x.type==='text').text).result;
if(!data?.shapes)throw Error('Snapshot missing shapes');
const shapes=data.shapes;const parent=new Map(shapes.map(s=>[s.id,s.parent]));
for(const b of shapes.filter(s=>s.type==='board'&&s.parent===shapes[0].id&&!s.hidden)){
 const code=b.name.split(' •')[0];if(!process.argv.slice(2).includes(code))continue;
 const inside=s=>{let id=s.parent;while(id){if(id===b.id)return true;id=parent.get(id);}return false;};
 console.log(JSON.stringify({id:b.id,name:b.name,w:b.width,h:b.height,items:shapes.filter(inside).filter(s=>!(s.hidden||s.name.startsWith('Event art /'))).map(s=>({name:s.name,x:s.x-b.x,y:s.y-b.y,w:s.width,h:s.height,text:s.characters,size:s.fontSize}))}));
}
