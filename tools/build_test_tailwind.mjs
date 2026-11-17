// 画面の配置テスト（tests/e2e_v129.py）用の CSS を作る。使い方:
//   npm install tailwindcss@4        （どこかに入れておく）
//   node tools/build_test_tailwind.mjs <node_modules/tailwindcss のパス> tests/fixtures/tailwind-local.css
// 本番は Tailwind の CDN を使うので、これはテスト専用（ネットワークなしで、実際の幅で重なりやはみ出しを測るため）。
import { compile } from 'tailwindcss/dist/lib.mjs';
import fs from 'fs'; import path from 'path';
const [twDir, out] = process.argv.slice(2);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const files = [];
(function walk(d) {
  for (const f of fs.readdirSync(d)) {
    const p = path.join(d, f), s = fs.statSync(p);
    if (s.isDirectory()) { if (!['.git', '__pycache__', 'tests', 'tools', 'ui_labels', 'phrasebook'].includes(f)) walk(p); }
    else if (/\.(html|js|py)$/.test(f)) files.push(p);
  }
})(root);
const cands = new Set();
for (const f of files) for (const m of fs.readFileSync(f, 'utf8').matchAll(/[A-Za-z0-9_\-:\/\.\[\]%#!&>()=,'"*]+/g)) cands.add(m[0].replace(/^['"]|['"]$/g, ''));
const tw = path.resolve(twDir) + '/';
const c = await compile('@import "tailwindcss";', {
  base: tw,
  loadStylesheet: async (id, base) => {
    const file = id === 'tailwindcss' ? tw + 'index.css' : id.startsWith('tailwindcss/') ? tw + id.slice(12) + (id.endsWith('.css') ? '' : '.css') : path.resolve(base, id);
    return { path: file, base: path.dirname(file), content: fs.readFileSync(file, 'utf8') };
  },
});
fs.writeFileSync(out, c.build([...cands]));
console.log('ok', out);
