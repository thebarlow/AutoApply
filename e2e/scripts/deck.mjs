#!/usr/bin/env node
/**
 * Build a single self-contained slide deck from the harness screenshots and open
 * it in one browser window. Cycle pages with ← / → (or the on-screen ‹ ›).
 *
 *   node scripts/deck.mjs            # all screenshots, in name order
 *   node scripts/deck.mjs landing    # only shots whose filename contains "landing"
 *
 * Images are base64-embedded, so the deck.html is portable and needs no server.
 * Tall full-page shots scroll inside their slide.
 */
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const shotsDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'screenshots');
const filter = process.argv[2]?.toLowerCase();

let files;
try {
  files = readdirSync(shotsDir)
    .filter((f) => f.toLowerCase().endsWith('.png'))
    .filter((f) => !filter || f.toLowerCase().includes(filter))
    .sort();
} catch {
  console.error(`No screenshots directory at ${shotsDir} — run the tests first.`);
  process.exit(1);
}

if (files.length === 0) {
  console.error(
    filter
      ? `No screenshot matches "${filter}" in ${shotsDir}.`
      : `No screenshots in ${shotsDir} — run the tests first.`,
  );
  process.exit(1);
}

const slides = files.map((f) => ({
  name: basename(f),
  data: `data:image/png;base64,${readFileSync(join(shotsDir, f)).toString('base64')}`,
}));

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>check-pages screenshots</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: #0d0d12; color: #e6e6ee;
    font: 14px/1.4 system-ui, sans-serif; }
  body { display: flex; flex-direction: column; }
  header { display: flex; align-items: center; gap: 12px; padding: 10px 16px;
    border-bottom: 1px solid #26263a; background: #14141c; }
  header .name { font-weight: 600; }
  header .count { color: #9a9ab5; margin-left: auto; }
  button { background: #24243a; color: #e6e6ee; border: 1px solid #3a3a55;
    border-radius: 6px; padding: 6px 12px; font-size: 16px; cursor: pointer; }
  button:hover { background: #303050; }
  main { flex: 1; overflow: auto; display: flex; justify-content: center;
    padding: 16px; }
  img { max-width: 100%; height: auto; align-self: flex-start;
    border: 1px solid #26263a; border-radius: 4px; }
  .hint { color: #6f6f8c; font-size: 12px; }
</style></head><body>
<header>
  <button id="prev" title="Previous (←)">‹</button>
  <button id="next" title="Next (→)">›</button>
  <span class="name" id="name"></span>
  <span class="hint">use ← / →</span>
  <span class="count" id="count"></span>
</header>
<main><img id="shot" alt=""></main>
<script>
  const slides = ${JSON.stringify(slides)};
  let i = 0;
  const img = document.getElementById('shot');
  const name = document.getElementById('name');
  const count = document.getElementById('count');
  function show() {
    img.src = slides[i].data;
    name.textContent = slides[i].name;
    count.textContent = (i + 1) + ' / ' + slides.length;
    document.querySelector('main').scrollTop = 0;
  }
  function go(d) { i = (i + d + slides.length) % slides.length; show(); }
  document.getElementById('prev').onclick = () => go(-1);
  document.getElementById('next').onclick = () => go(1);
  addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') go(-1);
    else if (e.key === 'ArrowRight') go(1);
  });
  show();
</script>
</body></html>`;

const out = join(shotsDir, 'deck.html');
writeFileSync(out, html);
console.log(`Deck: ${out} (${slides.length} slide${slides.length > 1 ? 's' : ''})`);

// Open in the default browser (one window).
const opener =
  process.platform === 'win32' ? ['cmd', ['/c', 'start', '', out]]
  : process.platform === 'darwin' ? ['open', [out]]
  : ['xdg-open', [out]];
spawn(opener[0], opener[1], { detached: true, stdio: 'ignore' }).unref();
