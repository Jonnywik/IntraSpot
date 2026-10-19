import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtemp, mkdir, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve, sep} from 'node:path';
import {createStaticServer} from '../Code/Frontend/scripts/serve-static.mjs';

test('static serving resolves Next segment prefetch without weakening route or file boundaries', async () => {
  const root = await mkdtemp(join(tmpdir(), 'intraspot-static-s13-'));
  const server = createStaticServer(root);
  try {
    await mkdir(join(root, 'events', '__next.events'), {recursive: true});
    await writeFile(join(root, 'events.html'), 'event page');
    await writeFile(join(root, '404.html'), 'not found');
    await writeFile(join(root, 'events', '__next.events', '__PAGE__.txt'), 'page segment');
    await writeFile(join(root, 'events', '__next._tree.txt'), 'tree segment');
    await new Promise(ready => server.listen(0, '127.0.0.1', ready));
    const base = `http://127.0.0.1:${server.address().port}`;
    for (const [path, expected] of [
      ['/events?eventId=newly-published', 'event page'],
      ['/events/__next.events.__PAGE__.txt?_rsc=fixture', 'page segment'],
      ['/events/__next.events/__PAGE__.txt', 'page segment'],
      ['/events/__next._tree.txt', 'tree segment'],
    ]) {
      const response = await fetch(base + path);
      assert.equal(response.status, 200, path);
      assert.equal(await response.text(), expected);
    }
    const head = await fetch(base + '/events/__next.events.__PAGE__.txt', {method: 'HEAD'});
    assert.equal(head.status, 200);
    assert.equal(await head.text(), '');
    assert.equal((await fetch(base + '/events', {method: 'POST'})).status, 405);
    assert.equal((await fetch(base + '/%2e%2e%5cprivate.txt')).status, 400);
    assert.equal((await fetch(base + '/missing.txt')).status, 404);
    assert.equal((await fetch(base + '/favicon.ico')).status, 204);
  } finally {
    await new Promise(done => server.close(done));
    assert.ok(resolve(root).startsWith(resolve(tmpdir()) + sep));
    assert.ok(root.split(sep).at(-1).startsWith('intraspot-static-s13-'));
    await rm(root, {recursive: true, force: true});
  }
});
