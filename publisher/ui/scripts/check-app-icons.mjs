// Verify the files browsers actually discover, including PNG payloads inside the legacy favicon.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

const UI = resolve(import.meta.dirname, '..');
const publicFile = url => {
  assert.match(url, /^\/[a-z0-9/.-]+$/);
  assert.ok(!url.includes('..'));
  return readFileSync(resolve(UI, `public${url}`));
};
const dimensions = bytes => {
  assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(bytes.subarray(12, 16).toString(), 'IHDR');
  assert.equal(bytes[25], 2, 'App icons must have opaque RGB backgrounds');
  return `${bytes.readUInt32BE(16)}x${bytes.readUInt32BE(20)}`;
};
const html = readFileSync(resolve(UI, 'index.html'), 'utf8');
const links = [...html.matchAll(/<link\b[^>]+>/g)].map(([tag]) =>
  Object.fromEntries([...tag.matchAll(/([a-z-]+)="([^"]*)"/g)].map(([, name, value]) => [name, value])));
const link = rel => {
  const found = links.find(item => item.rel === rel);
  assert.ok(found, `Missing ${rel} link`);
  return found;
};
const manifest = JSON.parse(publicFile(link('manifest').href));
assert.equal(manifest.id, '/');
assert.equal(manifest.scope, '/');
assert.equal(manifest.start_url, '/#/home');
assert.equal(manifest.display, 'standalone');
assert.equal(manifest.name, 'StudioZero');
for (const size of ['192x192', '512x512']) {
  assert.ok(manifest.icons.some(icon => icon.sizes === size && icon.purpose === 'any'));
}
assert.ok(manifest.icons.some(icon => icon.sizes === '512x512' && icon.purpose === 'maskable'));
for (const icon of manifest.icons) {
  assert.equal(icon.type, 'image/png');
  assert.equal(dimensions(publicFile(icon.src)), icon.sizes);
}
const apple = link('apple-touch-icon');
assert.equal(apple.sizes, '180x180');
assert.equal(dimensions(publicFile(apple.href)), apple.sizes);
for (const icon of links.filter(item => item.rel === 'icon' && item.type === 'image/png')) {
  assert.equal(dimensions(publicFile(icon.href)), icon.sizes);
}
assert.equal(dimensions(publicFile('/icons/studiozero-64.png')), '64x64');
const icoLink = links.find(item => item.rel === 'icon' && item.href.endsWith('.ico'));
assert.ok(icoLink, 'Missing ICO favicon');
const ico = publicFile(icoLink.href);
assert.equal(ico.readUInt16LE(0), 0);
assert.equal(ico.readUInt16LE(2), 1);
const sizes = [];
for (let i = 0; i < ico.readUInt16LE(4); i++) {
  const entry = 6 + i * 16;
  const size = `${ico[entry] || 256}x${ico[entry + 1] || 256}`;
  const start = ico.readUInt32LE(entry + 12);
  const end = start + ico.readUInt32LE(entry + 8);
  assert.ok(end <= ico.length);
  assert.equal(dimensions(ico.subarray(start, end)), size);
  sizes.push(size);
}
assert.deepEqual(sizes, ['16x16', '32x32', '48x48', '64x64', '256x256']);
assert.deepEqual(icoLink.sizes.split(' '), sizes);
assert.ok(!html.includes('data:,'), 'Empty placeholder favicon remains');
console.log('App manifest, Apple icon, PNG dimensions and all five favicon frames are valid.');
