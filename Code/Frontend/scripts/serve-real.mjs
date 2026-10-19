import {access} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createStaticServer} from './serve-static.mjs';

const root = resolve('out-real');
await access(resolve(root, 'index.html'));
createStaticServer(root).listen(3001, '127.0.0.1', () =>
  console.log('Isolated real-auth development frontend: http://127.0.0.1:3001'));
