import { readFileSync } from 'node:fs';
const config=readFileSync('C:/Users/mikae/.codex/config.toml','utf8');
const section=config.match(/\[mcp_servers\.penpot\]([\s\S]*?)(?=\n\[|$)/)?.[1];
const raw=section?.match(/url\s*=\s*"([^"]+)"/)?.[1];
if(!raw)throw new Error('No configured Penpot connection');
const url=new URL(raw);
console.log(JSON.stringify({origin:url.origin,path:url.pathname}));
try {const r=await fetch(url,{method:'POST',headers:{accept:'application/json, text/event-stream','content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'intraspot-final-design',version:'1'}}}),signal:AbortSignal.timeout(5000)});console.log(JSON.stringify({status:r.status,contentType:r.headers.get('content-type'),session:!!r.headers.get('mcp-session-id')}));const body=await r.text();let parsed;try{parsed=JSON.parse(body)}catch{};if(parsed)console.log(JSON.stringify({result:parsed.result,error:parsed.error}));}
catch(e){console.log(JSON.stringify({failure:e.name}));}
