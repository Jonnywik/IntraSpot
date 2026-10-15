import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve, extname, sep} from 'node:path';

const root = resolve('out');
const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
  '.css':'text/css; charset=utf-8','.json':'application/json','.jpg':'image/jpeg',
  '.png':'image/png','.svg':'image/svg+xml','.woff2':'font/woff2',
  '.txt':'text/plain; charset=utf-8'};
http.createServer(async (request, response) => {
  if (!['GET','HEAD'].includes(request.method)) {response.writeHead(405).end(); return;}
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    const file = resolve(root, `.${pathname === '/' ? '/index.html' : extname(pathname) ? pathname : `${pathname.replace(/\/$/,'')}.html`}`);
    if (!file.startsWith(root + sep)) {response.writeHead(400).end(); return;}
    const content = await readFile(file);
    response.writeHead(200, {'Content-Type':mime[extname(file)] || 'application/octet-stream', 'Cache-Control':'no-store'});
    response.end(request.method === 'HEAD' ? undefined : content);
  } catch {
    response.writeHead(404, {'Content-Type':'text/html; charset=utf-8'});
    response.end(await readFile(resolve(root, '404.html')).catch(() => 'Not found'));
  }
}).listen(3000, '127.0.0.1', () => console.log('Local static frontend: http://127.0.0.1:3000'));
