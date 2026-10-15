import {readFileSync,writeFileSync} from 'node:fs';
const unwrap=p=>{const raw=JSON.parse(readFileSync(p,'utf8'));const content=raw.content?.find(c=>c.type==='text')?.text;return content?JSON.parse(content).result:raw.result||raw;};
const before=unwrap('penpot-mobile-unchanged-baseline-2026-10-11.json');
const report=unwrap('penpot-desktop-responsive-final-evidence-2026-10-11.json');
const prior=new Map(before.mobileSnapshot.map(s=>[s.id,s]));
const changes=report.mobileSnapshot.filter(s=>JSON.stringify(s)!==JSON.stringify(prior.get(s.id))).map(s=>s.id);
const now=new Set(report.mobileSnapshot.map(s=>s.id));const removed=[...prior.keys()].filter(id=>!now.has(id));
report.mobileComparison={before:prior.size,after:now.size,changed:changes.length,removed:removed.length,unchanged:!changes.length&&!removed.length};delete report.mobileSnapshot;
try{report.savedReview=unwrap('docs/design/desktop-responsive-final-version.json');}catch{}
writeFileSync('docs/design/Desktop responsive and motion evidence.json',JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));
