import { readdir, readFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';

const root = resolve(process.argv[2] || 'public');
async function inspect(folder) {
  for (const entry of await readdir(folder, {withFileTypes: true})) {
    const target = join(folder, entry.name);
    if (entry.isDirectory()) { await inspect(target); continue; }
    if (/local-accounts|private\.pem|accounts\.json|\.env/i.test(entry.name)) {
      throw new Error('Refusing to export a local credential/configuration file.');
    }
    if (/\.(json|js|html|txt|pem|map)$/i.test(entry.name)) {
      const text = await readFile(target, 'utf8');
      if (/eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/.test(text)
          || text.includes('-----BEGIN PRIVATE KEY-----')) {
        throw new Error('Refusing to export signed credentials or signing keys.');
      }
    }
  }
}
await inspect(root);
console.log('Public/static asset credential guard passed.');
