import {execFileSync} from 'node:child_process';
const result=execFileSync('docker',['logs','--tail','140','penpot-penpot-mcp-1'],{encoding:'utf8',stdio:['ignore','pipe','pipe']});
const lines=result.split('\n').filter(l=>/connection established|Duplicate connection|connection closed|no heartbeat|suspended|frozen|Task .*completed|Task .*rejected|Sent task/i.test(l));
for(const line of lines)console.log(line.replace(/(userToken|token|authorization)([\s=:]+)[^\s,}]+/gi,'$1$2[redacted]').replace(/eyJ[A-Za-z0-9_.-]+/g,'[redacted]'));
