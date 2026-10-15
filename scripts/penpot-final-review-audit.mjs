import {readFileSync} from 'node:fs';
const input=JSON.parse(readFileSync(process.argv[2]||'penpot-final-review-live-before.json','utf8'));
const data=input.shapes?input:JSON.parse(input.content.find(c=>c.type==='text').text).result;
if(!data?.shapes)throw Error('Successful live snapshot required');
const all=data.shapes,by=new Map(all.map(s=>[s.id,s]));
const hidden=s=>s.hidden||(s.parent&&by.has(s.parent)?hidden(by.get(s.parent)):false);
function root(s){while(s.parent&&s.parent!=='00000000-0000-0000-0000-000000000000'&&by.has(s.parent))s=by.get(s.parent);return s;}
const roots=all.filter(s=>s.type==='board'&&s.parent==='00000000-0000-0000-0000-000000000000'&&!s.hidden);
const journeys=roots.filter(s=>! /^(00|01|02|03|8|9|Retired)/.test(s.name)),ids=new Set(journeys.map(s=>s.id));
const visible=all.filter(s=>!hidden(s));
const invalidGeometry=visible.filter(s=>ids.has(root(s).id)&&![s.x,s.y,s.width,s.height].every(Number.isFinite));
const horizontalOverflow=visible.filter(s=>ids.has(root(s).id)&&s.id!==root(s).id&&(s.x<root(s).x-.5||s.x+s.width>root(s).x+root(s).width+.5));
const hiddenTargets=[],missingTargets=[],applicationLoops=[],disabledInteractive=[];
for(const s of visible){const r=root(s);for(const i of s.interactions||[]){const d=i.action.destination;if(d&&!by.has(d))missingTargets.push({source:s.name,target:d});else if(d&&hidden(by.get(d)))hiddenTargets.push({source:s.name,target:by.get(d).name});if(i.trigger==='after-delay'&&ids.has(r.id))applicationLoops.push(s.name);if(/disabled/i.test(s.name)&&ids.has(r.id)&&['click','mouse-enter'].includes(i.trigger))disabledInteractive.push(s.name);}}
console.log(JSON.stringify({page:data.page,shapes:all.length,journeyBoards:journeys.length,invalidGeometry:invalidGeometry.map(s=>s.name),horizontalOverflow:horizontalOverflow.map(s=>({board:root(s).name,shape:s.name})),hiddenTargets,missingTargets,applicationLoops,disabledInteractive,presentationTesting:'Not performed: structural prototype check only'},null,2));
