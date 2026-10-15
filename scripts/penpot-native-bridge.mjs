import {readFileSync,writeFileSync} from 'node:fs';
const config=readFileSync('C:/Users/mikae/.codex/config.toml','utf8');
const section=config.match(/\[mcp_servers\.penpot\]([\s\S]*?)(?=\n\[|$)/)?.[1];
const endpoint=section?.match(/url\s*=\s*"([^"]+)"/)?.[1];
if(!endpoint)throw new Error('Penpot connection is not configured');
let session;let serial=0;
async function call(method,params,notification=false){
 const headers={accept:'application/json, text/event-stream','content-type':'application/json'};
 if(session)headers['mcp-session-id']=session;
 const id=notification?undefined:++serial;
 const r=await fetch(endpoint,{method:'POST',headers,body:JSON.stringify({jsonrpc:'2.0',id,method,params}),signal:AbortSignal.timeout(90000)});
 session=r.headers.get('mcp-session-id')||session;
 if(!r.ok)throw new Error('Penpot HTTP '+r.status);
 if(notification||r.status===202){await r.body?.cancel();return null;}
 const body=await r.text();let response;
 if(r.headers.get('content-type')?.includes('text/event-stream')){
  for(const frame of body.replaceAll('\r','').split('\n\n')){const data=frame.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');if(!data)continue;const item=JSON.parse(data);if(item.id===id)response=item;}
 }else response=JSON.parse(body);
 if(!response)throw new Error('No Penpot response received');if(response.error)throw new Error(JSON.stringify(response.error));return response.result;
}
await call('initialize',{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'intraspot-final-design',version:'1'}});
await call('notifications/initialized',{},true);
const tool=process.argv[2]||'--list',input=process.argv[3];
const args=tool==='execute_code'?{code:readFileSync(input,'utf8')}:tool==='export_shape'?{shapeId:input,format:'png',mode:'shape'}:tool==='penpot_api_info'?{type:input,...(process.argv[4]?{member:process.argv[4]}:{})}:{};
const repetitions=tool==='execute_code'?Number(process.argv[4]||1):1;
const outputPath=process.env.PENPOT_OUTPUT||(tool==='export_shape'?process.argv[4]:null);
const resultOutput=process.env.PENPOT_RESULT_OUTPUT||(tool==='execute_code'?process.argv[5]:null);
if(!Number.isInteger(repetitions)||repetitions<1||repetitions>30)throw new Error('Repeat count must be 1–30');
for(let batch=0;batch<repetitions;batch++){
const result=tool==='--list'?await call('tools/list',{}):await call('tools/call',{name:tool,arguments:args});
if(resultOutput){writeFileSync(resultOutput,JSON.stringify(result,null,2));console.log('Saved result '+resultOutput);}
else if(tool==='export_shape'&&outputPath){const bitmap=result.content?.find(c=>c.type==='image');if(!bitmap)throw new Error(JSON.stringify(result));writeFileSync(outputPath,Buffer.from(bitmap.data,'base64'));console.log('Saved '+outputPath);}
else{const raw=result.content?.find(c=>c.type==='text')?.text;try{console.log(JSON.stringify(JSON.parse(raw)));}catch{console.log(JSON.stringify(result));}}
const message=result.content?.find(c=>c.type==='text')?.text||'';
if(result.isError||message.startsWith('Tool execution failed')){process.exitCode=1;break;}
try{if(JSON.parse(message)?.result?.remaining===0)break;}catch{}
}
