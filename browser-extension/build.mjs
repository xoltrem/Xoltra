/**
 * build.mjs — esbuild pipeline for the Xoltra Companion Extension.
 *
 * Outputs an unpacked MV3 extension into dist/:
 *   dist/manifest.json
 *   dist/service-worker.js        (background)
 *   dist/content-capture.js       (injected on demand via chrome.scripting)
 *   dist/sidepanel.{js,html,css}
 *   dist/options.{js,html,css}
 *
 * No dev server: MV3 forbids remote code, so everything is bundled flat.
 * Run `npm run build` then "Load unpacked" -> dist/ in chrome://extensions.
 */
import { build, context } from 'esbuild';
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs';

const watch = process.argv.includes('--watch');

rmSync('dist', { recursive: true, force: true });
mkdirSync('dist', { recursive: true });

// Static assets copied verbatim.
cpSync('manifest.json', 'dist/manifest.json');
cpSync('src/sidepanel/sidepanel.html', 'dist/sidepanel.html');
cpSync('src/sidepanel/sidepanel.css', 'dist/sidepanel.css');
cpSync('src/options/options.html', 'dist/options.html');
if (existsSync('public')) cpSync('public', 'dist', { recursive: true });

/** @type {import('esbuild').BuildOptions} */
const common = {
  bundle: true,
  format: 'esm',
  target: 'chrome120',
  sourcemap: false,
  minify: true,
  logLevel: 'info',
  define: { 'process.env.NODE_ENV': '"production"' },
};

const entries = [
  { entryPoints: ['src/background/service-worker.ts'], outfile: 'dist/service-worker.js' },
  // Content script: injected with chrome.scripting, must be IIFE (no module scope).
  { entryPoints: ['src/content/capture.ts'], outfile: 'dist/content-capture.js', format: 'iife' },
  { entryPoints: ['src/sidepanel/main.tsx'], outfile: 'dist/sidepanel.js' },
  { entryPoints: ['src/options/main.tsx'], outfile: 'dist/options.js' },
];

if (watch) {
  const ctxs = await Promise.all(entries.map(e => context({ ...common, ...e })));
  await Promise.all(ctxs.map(c => c.watch()));
  console.log('[xoltra-ext] watching…');
} else {
  await Promise.all(entries.map(e => build({ ...common, ...e })));
  console.log('[xoltra-ext] built dist/');
}
