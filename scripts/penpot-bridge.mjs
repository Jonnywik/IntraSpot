import { readFileSync, writeFileSync } from 'node:fs';

const config = readFileSync('C:/Users/mikae/.codex/config.toml', 'utf8');
const section = config.match(/\[mcp_servers\.penpot\]([\s\S]*?)(?=\n\[|$)/)?.[1];
const source = section?.match(/url\s*=\s*"([^"]+)"/)?.[1];
if (!source) throw new Error('Penpot MCP URL is not configured');
const token = new URL(source).searchParams.get('userToken');
if (!token) throw new Error('Penpot MCP token is missing');
const stream = await fetch(`http://localhost:4401/sse?userToken=${encodeURIComponent(token)}`, { headers: { accept: 'text/event-stream' } });
if (!stream.ok) throw new Error(`Penpot stream failed: ${stream.status}`);
const reader = stream.body.getReader();
const pending = new Map();
let endpoint;
let buffer = '';
let serial = 0;
const ready = Promise.withResolvers();
const receive = (async () => {
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += new TextDecoder().decode(value);
    for (let end; (end = buffer.indexOf('\n\n')) >= 0;) {
      const frame = buffer.slice(0, end).replaceAll('\r', '');
      buffer = buffer.slice(end + 2);
      const event = frame.match(/^event:\s*(.*)$/m)?.[1];
      const data = [...frame.matchAll(/^data:\s*(.*)$/gm)].map(x => x[1]).join('\n');
      if (event === 'endpoint') { endpoint = new URL(data, 'http://localhost:4401').href; ready.resolve(); }
      if (event === 'message') {
        let message;
        try { message = JSON.parse(data); } catch { continue; }
        if (message.id != null && pending.has(message.id)) {
          const { resolve, reject } = pending.get(message.id);
          pending.delete(message.id);
          message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
        }
      }
    }
  }
  for (const { reject } of pending.values()) reject(new Error('Penpot stream closed'));
})();
await Promise.race([ready.promise, new Promise((_, reject) => setTimeout(() => reject(new Error('Penpot endpoint timeout')), 10000))]);
async function call(method, params) {
  const id = ++serial;
  const response = Promise.withResolvers();
  pending.set(id, response);
  const posted = await fetch(endpoint, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', id, method, params }) });
  if (!posted.ok) throw new Error(`Penpot request failed: ${posted.status}`);
  return Promise.race([response.promise, new Promise((_, reject) => setTimeout(() => reject(new Error(`Penpot ${method} timeout`)), 90000))]);
}
await call('initialize', { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'intraspot-design', version: '1' } });
await fetch(endpoint, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) });
const tool = process.argv[2] || 'execute_code';
const input = process.argv[3];
const args = tool === 'execute_code' ? { code: readFileSync(input, 'utf8') } : tool === '--list' ? null : tool === 'penpot_api_info' ? { type: input } : tool === 'export_shape' && /^[0-9a-f-]{36}$/.test(input) ? { shapeId: input, format: 'png', mode: 'shape' } : JSON.parse(readFileSync(input, 'utf8'));
const result = tool === '--list' ? await call('tools/list', {}) : await call('tools/call', { name: tool, arguments: args });
if (process.env.PENPOT_OUTPUT && tool === 'export_shape') {
  const bitmap = result.content?.find(item => item.type === 'image');
  if (!bitmap) throw new Error(JSON.stringify(result));
  writeFileSync(process.env.PENPOT_OUTPUT, Buffer.from(bitmap.data, 'base64'));
  process.stdout.write(`Saved ${process.env.PENPOT_OUTPUT}\n`);
} else process.stdout.write(JSON.stringify(result) + '\n');
process.exit(0);
