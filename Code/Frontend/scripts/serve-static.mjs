import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve, extname, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
  '.css':'text/css; charset=utf-8','.json':'application/json','.jpg':'image/jpeg',
  '.png':'image/png','.svg':'image/svg+xml','.woff2':'font/woff2',
  '.txt':'text/plain; charset=utf-8'};
export function createStaticServer(root = resolve('out')) {
  root = resolve(root);
  return http.createServer(async (request, response) => {
  response.setHeader('Referrer-Policy', 'no-referrer');
  response.setHeader('X-Content-Type-Options', 'nosniff');
  if (!['GET','HEAD'].includes(request.method)) {response.writeHead(405).end(); return;}
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    const candidates = [pathname === '/' ? '/index.html' : extname(pathname) ? pathname : `${pathname.replace(/\/$/,'')}.html`];
    // Next flattens segment request keys, but this exporter emits nested files.
    // Segment names encode literal dots; only these separators become directories.
    const segment = pathname.match(/^(.*\/)(__next\.)([^/]+)\.txt$/);
    if (segment && segment[3].includes('.')) {
      const [first, ...rest] = segment[3].split('.');
      candidates.push(`${segment[1]}${segment[2]}${first}/${rest.join('/')}.txt`);
    }
    for (const [index, candidate] of candidates.entries()) {
      const file = resolve(root, `.${candidate}`);
      if (!file.startsWith(root + sep)) {response.writeHead(400).end(); return;}
      try {
        const content = await readFile(file);
        response.writeHead(200, {'Content-Type':mime[extname(file)] || 'application/octet-stream', 'Cache-Control':'no-store'});
        response.end(request.method === 'HEAD' ? undefined : content);
        return;
      } catch (error) {
        if (error.code !== 'ENOENT' || index === candidates.length - 1) throw error;
      }
    }
  } catch (error) {
    // No icon is configured in this local MVP; do not invent a new brand asset.
    if (pathname === '/favicon.ico' && error.code === 'ENOENT') {response.writeHead(204).end(); return;}
    response.writeHead(404, {'Content-Type':'text/html; charset=utf-8'});
    response.end(request.method === 'HEAD' ? undefined : await readFile(resolve(root, '404.html')).catch(() => 'Not found'));
  }
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  createStaticServer().listen(3000, '127.0.0.1', () => console.log('Local static frontend: http://127.0.0.1:3000'));
}
