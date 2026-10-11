#!/usr/bin/env node
// render.mjs — the motion-video engine (zero dependencies: node 22+ (global WebSocket) / system Chrome / ffmpeg)
//
//   node render.mjs storyboard <project> [--aspect 9:16|all] [--brand brand.json] [--out dir]  (cut sheet cutsheet.html; advances the version if feedback/v<N>.json exists)
//   node render.mjs check      <project> [--frame 300]
//   node render.mjs approve    <project> --by "<person who gave the OK>" --note "<the OK statement>"
//   node render.mjs final      <project> [--aspect all|16:9,9:16] [--keep-frames]
//   node render.mjs stills     <project> (--times 1.2,3.4 | --from 3 --to 4) [--aspect 16:9]
//   node render.mjs probe      <file.mp4>
//
// Chrome does not start inside Claude Code's Bash sandbox. Run outside the sandbox (dangerouslyDisableSandbox).
// Output defaults to <project>/out; the working PNG sequence goes under os.tmpdir()/motion-video/.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import crypto from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { renderAudio, beatsInfo, audioWarnings, measureLoudness, spectrogram, bandLevels, BANDS, AAC } from './audio.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const SIZES = { '16:9': [1920, 1080], '9:16': [1080, 1920], '1:1': [1080, 1080], '4:5': [1080, 1350] };
const tag = (a) => a.replace(':', 'x');
const sha = (b) => crypto.createHash('sha256').update(b).digest('hex');

function die(msg, code = 1) {
  console.error(`motion-video: ${msg}`);
  process.exit(code);
}

function parseArgs(argv) {
  const [cmd, ...rest] = argv;
  const pos = [];
  const f = {};
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a.startsWith('--')) {
      const k = a.slice(2);
      if (i + 1 < rest.length && !rest[i + 1].startsWith('--')) f[k] = rest[++i];
      else f[k] = true;
    } else pos.push(a);
  }
  return { cmd, pos, f };
}

function run(bin, args) {
  const r = spawnSync(bin, args, { encoding: 'utf8', maxBuffer: 1 << 26 });
  if (r.status !== 0) throw new Error(`${bin} ${args.join(' ')}\n${r.stderr}`);
  return r.stdout;
}

// ── Drive Chrome directly over CDP ──────────────────────────────
function chromePath() {
  const cands = [
    process.env.MOTION_VIDEO_CHROME,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
  ].filter(Boolean);
  for (const c of cands) if (fs.existsSync(c)) return c;
  for (const n of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']) {
    const r = spawnSync('which', [n], { encoding: 'utf8' });
    if (r.status === 0) return r.stdout.trim();
  }
  die('Chrome / Chromium not found. Set MOTION_VIDEO_CHROME to the executable path');
}

async function launchChrome() {
  const ud = fs.mkdtempSync(path.join(os.tmpdir(), 'mv-chrome-'));
  const proc = spawn(chromePath(), [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--hide-scrollbars',
    '--force-color-profile=srgb', '--font-render-hinting=none', '--disable-lcd-text', '--mute-audio',
    '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-extensions',
    '--remote-debugging-port=0', `--user-data-dir=${ud}`, 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsUrl = await new Promise((res, rej) => {
    let buf = '';
    const to = setTimeout(() => rej(new Error(`Chrome did not start (if inside the Claude Code sandbox, run outside it)\n${buf.slice(-800)}`)), 20000);
    proc.stderr.on('data', (d) => {
      buf += d;
      const m = buf.match(/DevTools listening on (ws:\S+)/);
      if (m) { clearTimeout(to); res(m[1]); }
    });
    proc.on('exit', (c) => rej(new Error(`Chrome exited (code ${c})\n${buf.slice(-800)}`)));
  });
  const base = wsUrl.replace('ws://', 'http://').replace(/\/devtools.*/, '');
  const page = (await (await fetch(`${base}/json/list`)).json()).find((x) => x.type === 'page');
  const sock = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r, j) => { sock.onopen = r; sock.onerror = j; });
  let id = 0;
  const pend = new Map();
  sock.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) {
      const { res, rej } = pend.get(m.id);
      pend.delete(m.id);
      m.error ? rej(new Error(m.error.message)) : res(m.result);
    } else if (m.method === 'Runtime.exceptionThrown') {
      console.error('[page] ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    } else if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) {
      console.error(`[page ${m.params.type}] ` + m.params.args.map((a) => a.value ?? a.description).join(' '));
    }
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const i = ++id;
    pend.set(i, { res, rej });
    sock.send(JSON.stringify({ id: i, method, params }));
  });
  // Wait for Chrome to exit before deleting the profile (right after kill, Chrome may still be writing and the delete can fail)
  const close = async () => {
    try { sock.close(); } catch {}
    const exited = proc.exitCode != null ? Promise.resolve() : new Promise((r) => proc.once('exit', r));
    proc.kill('SIGKILL');
    await Promise.race([exited, new Promise((r) => setTimeout(r, 3000))]);
    try { fs.rmSync(ud, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }); } catch {}
  };
  return { send, close };
}

// ── Local http (serves assets from the same origin; with file:// the canvas is tainted and cannot be exported) ──
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.otf': 'font/otf' };
async function serve(roots) {
  const srv = http.createServer((req, res) => {
    const url = decodeURIComponent(req.url.split('?')[0]);
    const p = url === '/' ? '/runtime/harness.html' : url === '/harness.html' ? '/runtime/harness.html' : url;
    const pre = Object.keys(roots).find((k) => p.startsWith(k));
    if (!pre) { res.statusCode = 404; return res.end(); }
    const file = path.resolve(roots[pre], '.' + p.slice(pre.length - 1));
    if (!file.startsWith(path.resolve(roots[pre])) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.statusCode = 404; return res.end(); }
    res.setHeader('content-type', TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream');
    res.setHeader('cache-control', 'no-store');
    fs.createReadStream(file).pipe(res);
  }).listen(0, '127.0.0.1');
  await new Promise((r) => srv.once('listening', r));
  return srv;
}

// ── Project ─────────────────────────────────────────────────────
function listFiles(dir, skip) {
  const out = [];
  const walk = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(d, e.name);
      if (e.name.startsWith('.') || e.name === 'node_modules' || skip.some((s) => p === s)) continue;
      e.isDirectory() ? walk(p) : out.push(p);
    }
  };
  walk(dir);
  return out;
}

function resolveProject(pos, f) {
  if (!pos[0]) die('Specify the project folder');
  const proj = path.resolve(pos[0]);
  if (!fs.existsSync(path.join(proj, 'video.js'))) die(`${proj}/video.js not found`);
  const brand = f.brand ? path.resolve(f.brand) : fs.existsSync(path.join(proj, 'brand.json')) ? path.join(proj, 'brand.json') : null;
  const out = path.resolve(f.out || path.join(proj, 'out'));
  return { proj, brand, out };
}

// What approval covers = every file in the project (except out/ and approval.json) + an external brand.json and the files it references
function sourceHash({ proj, brand, out }) {
  const files = listFiles(proj, [out, path.join(proj, 'approval.json')]);
  const h = crypto.createHash('sha256');
  for (const p of files) h.update(path.relative(proj, p)).update('\0').update(fs.readFileSync(p)).update('\0');
  if (brand && !brand.startsWith(proj + path.sep)) {
    h.update('@brand\0').update(fs.readFileSync(brand));
    const b = JSON.parse(fs.readFileSync(brand, 'utf8'));
    for (const rel of [b.logo, ...Object.values(b.fonts || {}).map((x) => x.file)].filter(Boolean)) {
      const p = path.resolve(path.dirname(brand), rel);
      if (fs.existsSync(p)) h.update(rel).update(fs.readFileSync(p));
    }
  }
  return h.digest('hex');
}

function prepareClips(meta, proj, work) {
  const counts = {};
  for (const [k, c] of Object.entries(meta.clips || {})) {
    const src = path.resolve(proj, c.src);
    if (!fs.existsSync(src)) die(`Clip not found: ${src}`);
    if (!c.fps) die(`Specify meta.clips.${k}.fps (frames per second to extract)`);
    const dir = path.join(work, 'clips', k);
    const key = sha(Buffer.concat([fs.readFileSync(src), Buffer.from(`|${c.fps}|${c.maxWidth || ''}`)]));
    const marker = path.join(dir, '.key');
    if (!(fs.existsSync(marker) && fs.readFileSync(marker, 'utf8') === key)) {
      fs.rmSync(dir, { recursive: true, force: true });
      fs.mkdirSync(dir, { recursive: true });
      const vf = [`fps=${c.fps}`, c.maxWidth ? `scale='min(${c.maxWidth},iw)':-2` : null].filter(Boolean).join(',');
      run('ffmpeg', ['-v', 'error', '-i', src, '-vf', vf, '-start_number', '1', path.join(dir, '%05d.png')]);
      fs.writeFileSync(marker, key);
    }
    counts[k] = fs.readdirSync(dir).filter((x) => x.endsWith('.png')).length;
    if (!counts[k]) die(`Could not extract frames from clip ${k}`);
  }
  return counts;
}

async function openSession(P, f) {
  const hash = sourceHash(P);
  const work = path.resolve(f.work || path.join(os.tmpdir(), 'motion-video', `${path.basename(P.proj)}-${hash.slice(0, 10)}`));
  fs.mkdirSync(work, { recursive: true });
  fs.mkdirSync(path.join(work, 'clips'), { recursive: true });
  const srv = await serve({
    '/runtime/': path.join(HERE, 'runtime'),
    '/project/': P.proj,
    '/brand/': P.brand ? path.dirname(P.brand) : P.proj,
    '/clips/': path.join(work, 'clips'),
  });
  const cdp = await launchChrome();
  const ev = async (expr) => {
    const r = await cdp.send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  };
  const close = async () => { srv.close(); await cdp.close(); };
  try {
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Page.navigate', { url: `http://127.0.0.1:${srv.address().port}/harness.html` });
    for (let i = 0; !(await ev('window.__mvReady === true').catch(() => false)); i++) {
      if (i > 400) throw new Error('harness failed to load');
      await new Promise((r) => setTimeout(r, 50));
    }
    const meta = await ev('__mv.load()');
    const problems = metaErrors(meta);
    if (problems.length) throw new Error('Invalid meta in video.js:\n- ' + problems.join('\n- '));
    const clipCounts = prepareClips(meta, P.proj, work);
    const brandJson = P.brand ? JSON.parse(fs.readFileSync(P.brand, 'utf8')) : null;
    const init = await ev(`__mv.init(${JSON.stringify({ brandJson, clipCounts })})`);
    const N = Math.round(meta.duration * meta.fps);
    let curSize = null;
    const S = {
      meta, hash, work, N, fonts: init.fonts, brandJson, close,
      async size(asp, div = 1) {
        const [w, h] = SIZES[asp];
        const key = `${w / div}x${h / div}`;
        if (curSize !== key) { await ev(`__mv.resize(${Math.round(w / div)}, ${Math.round(h / div)})`); curSize = key; }
      },
      async frame(t, sub) {
        const url = await ev(`__mv.frame(${JSON.stringify(t)}, ${sub == null ? 'undefined' : sub})`);
        return Buffer.from(url.slice(url.indexOf(',') + 1), 'base64');
      },
      motionScan: () => ev(`__mv.motionScan(${N})`),
      pairDiff: (pairs) => ev(`__mv.pairDiff(${JSON.stringify(pairs)})`),
      manifest: () => ev('__mv.manifest()'),
    };
    return S;
  } catch (e) {
    await close();
    throw e;
  }
}

function metaErrors(m) {
  const e = [];
  if (!(m.duration > 0)) e.push('duration (seconds) must be a positive number');
  if (!(m.fps > 0)) e.push('fps must be a positive number');
  for (const a of m.aspects || []) if (!SIZES[a]) e.push(`unsupported aspect ${a} (${Object.keys(SIZES).join(' / ')})`);
  if (!(m.aspects || []).length) e.push('aspects needs at least one entry (e.g. ["9:16","1:1","16:9"])');
  if (!(m.scenes || []).length) e.push('scenes needs at least one entry');
  return e;
}

// Check the scene contract and timing (warnings; does not stop)
function sceneWarnings(m) {
  const w = [];
  const N = m.duration * m.fps;
  if (Math.abs(N - Math.round(N)) > 1e-6) w.push(`duration×fps is not an integer (${N}). Frame count is rounded to ${Math.round(N)}`);
  const sc = m.scenes;
  if (Math.abs(sc[0].start) > 1e-6) w.push(`The first scene does not start at 0 s (${sc[0].start})`);
  for (let i = 1; i < sc.length; i++) if (Math.abs(sc[i].start - sc[i - 1].end) > 1e-6) w.push(`Gap or overlap between ${sc[i - 1].id}→${sc[i].id} (${sc[i - 1].end}→${sc[i].start})`);
  if (Math.abs(sc[sc.length - 1].end - m.duration) > 1e-6) w.push(`The end of the last scene (${sc[sc.length - 1].end}) does not match the duration (${m.duration})`);
  const dup = sc.map((s) => s.id).filter((id, i, a) => a.indexOf(id) !== i);
  if (dup.length) w.push(`Duplicate scene ids (${[...new Set(dup)].join(', ')}). Cut sheet images and FB are looked up by id, so make them unique`);
  for (const s of sc) {
    const miss = ['message', 'screen', 'motion', 'sound', 'transition'].filter((k) => !s[k]);
    if (miss.length) w.push(`${s.id}: empty scene-contract fields (${miss.join(', ')})`);
    if (/^(cut|hard ?cut|カット|ハードカット)$/i.test(String(s.transition || '').trim())) w.push(`${s.id}: the transition is a hard cut. Turn something on screen into something in the next scene instead`);
  }
  return w;
}

// From the series of motion amounts, find stretches of 4+ seconds without a noticeable change
function quietWindows(diffs, fps, thr = 0.002, win = 4) {
  const out = [];
  let start = 0;
  for (let i = 1; i <= diffs.length; i++) {
    if (i === diffs.length || diffs[i] > thr) {
      if ((i - start) / fps >= win) out.push([+(start / fps).toFixed(2), +(i / fps).toFixed(2)]);
      start = i;
    }
  }
  return out;
}

function tile(pngs, outPath, cols, width) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mv-tile-'));
  pngs.forEach((p, i) => fs.copyFileSync(p, path.join(dir, `${String(i + 1).padStart(4, '0')}.png`)));
  const rows = Math.ceil(pngs.length / cols);
  run('ffmpeg', ['-y', '-v', 'error', '-framerate', '1', '-i', path.join(dir, '%04d.png'), '-vf', `scale=${width}:-2,tile=${cols}x${rows}:padding=6:margin=6:color=white`, '-frames:v', '1', '-update', '1', outPath]);
  fs.rmSync(dir, { recursive: true, force: true });
}

function sceneKeys(s) {
  return s.keys || [s.key ?? (s.start + s.end) / 2];
}

// Compare the same frame "drawn first" and "drawn after other frames". They differ if state carries over from previous frames
async function determinismCheck(S, asp, frameNo) {
  await S.size(asp);
  const { N, meta } = S;
  const F = Math.max(0, Math.min(frameNo ?? 300, N - 1));
  const cold = sha(await S.frame(F / meta.fps));
  for (const j of [N - 1, 0, Math.max(0, F - 1), Math.min(N - 1, F + 13)]) await S.frame(j / meta.fps);
  const warm = sha(await S.frame(F / meta.fps));
  const res = { frame: F, cold: cold.slice(0, 16), warm: warm.slice(0, 16), ok: cold === warm };
  if (meta.loop) {
    // If the change across the seam (last frame → first frame) is about the same as between neighboring frames on either side, position and velocity are continuous.
    // Wrapping with t % duration cannot fake this (if the motion is not actually periodic, the seam difference jumps)
    const fr = (i) => i / meta.fps;
    await S.size(asp, 4);
    const [before, seam, after] = await S.pairDiff([[fr(N - 2), fr(N - 1)], [fr(N - 1), fr(0)], [fr(0), fr(1)]]);
    await S.size(asp);
    const neighbor = Math.max(before, after);
    const ok = seam <= neighbor * 2 + 1e-4;
    res.loop = { seam: +seam.toFixed(6), neighbor: +neighbor.toFixed(6), ok };
    res.ok = res.ok && ok;
  }
  return res;
}

// ── storyboard ─────────────────────────────────────────────────
async function cmdStoryboard(P, f) {
  const S = await openSession(P, f);
  try {
    const { meta } = S;
    const aspects = f.aspect === 'all' ? meta.aspects : f.aspect ? f.aspect.split(',') : [meta.aspects[0]];
    const dir = path.join(P.out, 'storyboard');
    // Rebuild the latest version at the top level. Keep earlier versions (v<N>/)
    fs.mkdirSync(dir, { recursive: true });
    for (const e of fs.readdirSync(dir)) if (!VERSION_DIR.test(e)) fs.rmSync(path.join(dir, e), { recursive: true, force: true });
    const fb = loadFeedback(P.proj);
    const version = 1 + Math.max(0, ...Object.keys(fb).map(Number));
    const warnings = [...sceneWarnings(meta), ...audioWarnings(meta.audio, meta.duration, meta.fps), ...feedbackWarnings(fb[version - 1], version - 1, meta.scenes)];
    const beats = beatsInfo(meta.audio, meta.duration);
    fs.writeFileSync(path.join(dir, 'beats.json'), JSON.stringify(beats, null, 2));
    const sound = hasAudio(meta) ? audioPreview(S, P, dir, warnings) : null;
    const check = await determinismCheck(S, aspects[0], f.frame ? +f.frame : undefined);
    if (!check.ok) warnings.unshift(`Determinism check failed: ${JSON.stringify(check)} (render carries state over from previous frames)`);
    const per = {};
    for (const asp of aspects) {
      const ad = path.join(dir, tag(asp));
      fs.mkdirSync(ad, { recursive: true });
      await S.size(asp);
      const stills = [];
      for (const s of meta.scenes) {
        for (const t of sceneKeys(s)) {
          const p = path.join(ad, `scene-${s.id}-${t.toFixed(2)}s.png`);
          fs.writeFileSync(p, await S.frame(t));
          stills.push({ scene: s.id, t, path: p });
        }
      }
      // Cut sheet: per cut, the "first" frame and the "last" frame
      const cutDir = path.join(ad, 'cuts');
      fs.mkdirSync(cutDir, { recursive: true });
      const cuts = [];
      for (const s of meta.scenes) {
        const c = { id: s.id, start: s.start, end: Math.max(s.start, s.end - 1 / meta.fps), startPng: cutPng(cutDir, s.id, 'start'), endPng: cutPng(cutDir, s.id, 'end') };
        fs.writeFileSync(c.startPng, await S.frame(c.start));
        fs.writeFileSync(c.endPng, await S.frame(c.end));
        cuts.push(c);
      }
      // contact: one frame per beat (thinned to at most 48 frames when there are too many)
      let bt = beats.beats;
      const step = Math.ceil(bt.length / 48);
      if (step > 1) bt = bt.filter((_, i) => i % step === 0);
      const cdir = path.join(ad, 'beats');
      fs.mkdirSync(cdir, { recursive: true });
      const cpaths = [];
      for (const t of bt) {
        const p = path.join(cdir, `beat-${t.toFixed(3)}s.png`);
        fs.writeFileSync(p, await S.frame(t));
        cpaths.push(p);
      }
      tile(cpaths, path.join(ad, 'contact.png'), 6, 320);
      // strip: 12 frames around the fastest-moving frame
      await S.size(asp, 8);
      const diffs = await S.motionScan();
      await S.size(asp);
      let fast = 0;
      diffs.forEach((d, i) => { if (d > diffs[fast]) fast = i; });
      const s0 = Math.max(0, Math.min(fast - 6, S.N - 12));
      const spaths = [];
      for (let i = s0; i < Math.min(S.N, s0 + 12); i++) {
        const p = path.join(cdir, `strip-${i}.png`);
        fs.writeFileSync(p, await S.frame(i / meta.fps));
        spaths.push(p);
      }
      tile(spaths, path.join(ad, 'strip.png'), 6, 320);
      // phone: representative frames shrunk to a phone screen width (390px)
      tile(stills.map((x) => x.path), path.join(ad, 'phone.png'), Math.min(4, stills.length), 390);
      const quiet = quietWindows(diffs, meta.fps);
      for (const [a, b] of quiet) warnings.push(`${asp}: no noticeable change in ${a}–${b}s (add a new visual event every 2–4 seconds)`);
      // seam: for loops, line up the last frame, the exact end, and the first frame
      let seam = null;
      if (meta.loop) {
        const sp = [];
        for (const [nm, t] of [['last', (S.N - 1) / meta.fps], ['end', meta.duration], ['first', 0]]) {
          const p = path.join(cdir, `seam-${nm}.png`);
          fs.writeFileSync(p, await S.frame(t));
          sp.push(p);
        }
        seam = path.join(ad, 'seam.png');
        tile(sp, seam, 3, 480);
      }
      per[asp] = {
        stills,
        cuts,
        contact: path.join(ad, 'contact.png'),
        strip: path.join(ad, 'strip.png'), stripFrom: +(s0 / meta.fps).toFixed(3), fastestAt: +(fast / meta.fps).toFixed(3),
        phone: path.join(ad, 'phone.png'),
        seam,
        quiet,
      };
    }
    const manifest = await S.manifest();
    for (const [fam, ok] of Object.entries(manifest.fonts)) if (!ok) warnings.push(`Font "${fam}" is not on this machine (drawn with a fallback). Pass a font file in fonts.*.file of brand.json`);
    const compare = compareCuts(dir, version, fb[version - 1], per[aspects[0]].cuts, aspects[0], warnings);
    const sb = { source_hash: S.hash, version, title: meta.title, duration: meta.duration, fps: meta.fps, frames: S.N, aspects, check, warnings, beats: path.join(dir, 'beats.json'), sound, per, manifest, scenes: meta.scenes, feedback: fb[version - 1] || null, compare };
    fs.writeFileSync(path.join(dir, 'storyboard.json'), JSON.stringify(sb, null, 2));
    fs.writeFileSync(path.join(dir, 'storyboard.md'), storyboardMd(sb, dir, P));
    fs.writeFileSync(path.join(dir, 'cutsheet.html'), cutsheetHtml(sb, dir, P, beats, meta, S.brandJson));
    // Keep a copy of this version in v<N>/ (re-running the same version overwrites it)
    const snap = path.join(dir, `v${version}`);
    fs.rmSync(snap, { recursive: true, force: true });
    fs.mkdirSync(snap);
    for (const e of fs.readdirSync(dir)) if (!VERSION_DIR.test(e)) fs.cpSync(path.join(dir, e), path.join(snap, e), { recursive: true });
    // The copy's storyboard.json points to files inside the copy (the top level is overwritten by the next version)
    const q = (p) => JSON.stringify(p + path.sep).slice(1, -1);
    fs.writeFileSync(path.join(snap, 'storyboard.json'), JSON.stringify(sb, null, 2).split(q(dir)).join(q(snap)));
    console.log(JSON.stringify({ storyboard: path.join(dir, 'storyboard.md'), cutsheet: path.join(dir, 'cutsheet.html'), version, source_hash: S.hash, check: check.ok, warnings, compare, sound: sound && { preview: sound.preview, spectrogram: sound.spectrogram, lufs: sound.lufs, truePeakDb: sound.truePeakDb }, per: Object.fromEntries(Object.entries(per).map(([k, v]) => [k, { contact: v.contact, strip: v.strip, phone: v.phone, seam: v.seam, stills: v.stills.map((x) => x.path) }])) }, null, 2));
  } finally {
    await S.close();
  }
}

const hasAudio = (meta) => !!(meta.audio?.cues?.length || meta.audio?.music);

// At the storyboard stage, build the sound with the same steps as the final and output a preview WAV and a spectrogram
function audioPreview(S, P, dir, warnings) {
  const { meta } = S;
  const ad = path.join(dir, 'audio');
  fs.mkdirSync(ad, { recursive: true });
  const preview = path.join(ad, 'preview.wav');
  const r = renderAudio({ duration: S.N / meta.fps, audio: meta.audio, scenes: meta.scenes, outPath: preview, work: S.work, base: P.proj });
  const spec = spectrogram({ wav: preview, out: path.join(ad, 'spectrogram.png'), duration: S.N / meta.fps, scenes: meta.scenes, peaks: meta.audio.peaks || [] });
  let mid = null;
  if (r.bgm) {
    mid = path.join(ad, 'bgm.mid');
    fs.copyFileSync(r.bgm.mid, mid);
  }
  if (r.lufs != null && Math.abs(r.lufs - r.target) > 1) warnings.push(`Loudness ${r.lufs} LUFS is outside ${r.target} ±1`);
  const tp = r.aac?.truePeakDb ?? r.truePeakDb;
  if (tp != null && tp > -1) warnings.push(`True peak after AAC encoding ${tp} dBFS exceeds -1`);
  const bands = bandLevels(preview);
  const sound = { preview, spectrogram: spec, mid, ...r, bands, bgm: r.bgm && { ...r.bgm, stem: undefined, mid: undefined } };
  fs.writeFileSync(path.join(ad, 'audio.json'), JSON.stringify(sound, null, 2));
  return sound;
}

function fmtMotion(m) {
  if (!m || typeof m === 'string') return m || '';
  return ['enter:Enter', 'main:Main', 'secondary:Secondary', 'exit:Exit'].map((kv) => { const [k, l] = kv.split(':'); return m[k] ? `${l}: ${m[k]}` : null; }).filter(Boolean).join(' / ');
}
const cell = (s) => String(s ?? '').replace(/\|/g, '\\|').replace(/\n/g, ' ');

function storyboardMd(sb, dir, P) {
  const rel = (p) => path.relative(dir, p);
  const a0 = sb.aspects[0];
  const L = [];
  L.push(`# Storyboard: ${sb.title || path.basename(P.proj)}`, '');
  L.push(`- Version v${sb.version} / cut sheet: [cutsheet.html](cutsheet.html) (earlier versions stay in v<N>/)`);
  L.push(`- Duration ${sb.duration}s / ${sb.fps}fps (${sb.frames} frames) / ${sb.aspects.join(', ')} / source_hash \`${sb.source_hash.slice(0, 12)}\``);
  L.push(`- Determinism check (frame ${sb.check.frame} drawn twice and compared): ${sb.check.ok ? 'OK' : '**NG**'}${sb.check.loop ? ` / loop seam: ${sb.check.loop.ok ? 'OK' : '**NG**'} (seam diff ${sb.check.loop.seam} / neighbor diff ${sb.check.loop.neighbor})` : ''}`);
  L.push('');
  if (sb.warnings.length) {
    L.push('## Warnings', '');
    for (const w of sb.warnings) L.push(`- ${w}`);
    L.push('');
  }
  L.push('## Scene table', '');
  L.push('| # | Start-end | Message | Screen | Motion | Narration | Sound | Transition | Representative frame |');
  L.push('|---|---|---|---|---|---|---|---|---|');
  for (const s of sb.scenes) {
    const st = sb.per[a0].stills.filter((x) => x.scene === s.id).map((x) => `[${x.t.toFixed(2)}s](${rel(x.path)})`).join(' ');
    L.push(`| ${cell(s.id)} | ${s.start.toFixed(2)}–${s.end.toFixed(2)}s | ${cell(s.message)} | ${cell(s.screen)} | ${cell(fmtMotion(s.motion))} | ${cell(s.narration)} | ${cell(s.sound)} | ${cell(s.transition)} | ${st} |`);
  }
  L.push('', '## Pre-render evidence', '');
  for (const [asp, v] of Object.entries(sb.per)) {
    L.push(`### ${asp}`, '');
    L.push(`- contact (one frame per beat): [contact.png](${rel(v.contact)})`);
    L.push(`- strip (12 consecutive frames around the fastest motion at ${v.fastestAt}s, from ${v.stripFrom}s): [strip.png](${rel(v.strip)})`);
    L.push(`- phone (representative frames shrunk to a 390px phone width): [phone.png](${rel(v.phone)})`);
    if (v.seam) L.push(`- seam (last frame / exact end / first frame): [seam.png](${rel(v.seam)})`);
    L.push('');
  }
  L.push(`- Beats: [beats.json](${rel(sb.beats)})`, '');
  if (sb.sound) {
    const a = sb.sound;
    L.push('## Sound', '');
    L.push(`- Preview (mixed with the same steps as the final): [preview.wav](${rel(a.preview)})${a.mid ? ` / BGM MIDI: [bgm.mid](${rel(a.mid)})` : ''}`);
    L.push(`- Spectrogram (vertical = log frequency axis, white lines = scene boundaries, green lines = peaks): [spectrogram.png](${rel(a.spectrogram)})`);
    L.push(`- Loudness ${a.lufs ?? '-'} LUFS (target ${a.target} ±1) / true peak ${a.truePeakDb ?? '-'} dBFS (${a.aac?.truePeakDb ?? '-'} dBFS after AAC encoding) / loudness range ${a.lra ?? '-'} LU`);
    L.push(`- RMS per band (dBFS; the bottom row of the spectrogram blurs on the log axis, so judge muddiness here): ${Object.entries(a.bands).map(([k, v]) => `${k} (${BANDS[k][0]}–${BANDS[k][1] || '∞'}Hz) ${v ?? '-'}`).join(' / ')}`);
    if (a.bgm) L.push(`- BGM: ${a.bgm.style} / ${a.bgm.progression.join(' → ')} / ${a.bgm.bars} bars, ${a.bgm.notes} notes / seed ${a.bgm.seed} / soundfont ${path.basename(a.bgm.soundfont)} (fluidsynth ${a.bgm.fluidsynth}) / reverb ${a.bgm.reverb} (IR: ${a.bgm.ir})`);
    L.push('');
  }
  L.push('## Next steps', '');
  L.push('1. Finish the self-review (9 items, 1–10) and fix the worst 3 before showing a human');
  L.push(`2. Show the cut sheet [cutsheet.html](cutsheet.html); if there is FB, have it written to \`feedback/v${sb.version}.json\` (write the responses and run storyboard to get v${sb.version + 1})`);
  L.push('3. **Only after a human OK**: `node render.mjs approve <project> --by "<name>" --note "<the OK statement>"`');
  L.push('4. `node render.mjs final <project>` (refused if the sources changed after approval)');
  return L.join('\n') + '\n';
}

// ── Cut sheet and FB round trips ─────────────────────────────────
// The human writes feedback on version N in feedback/v<N>.json; the agent writes its responses in response in the same file.
// The next storyboard becomes v<N+1> (version = latest version with FB + 1; 1 if there is no FB)
const VERSION_DIR = /^v\d+$/;
// Characters not allowed in file names (including Japanese IDs) become _, and ~ plus a hash of the original ID is appended to avoid collisions.
// IDs that need no replacement cannot contain ~, so they never collide with names of replaced IDs
const cutPng = (dir, id, which) => {
  const safe = String(id).replace(/[^\w.-]/g, '_');
  return path.join(dir, `${safe === String(id) ? safe : `${safe}~${sha(String(id)).slice(0, 8)}`}-${which}.png`);
};

function loadFeedback(proj) {
  const dir = path.join(proj, 'feedback');
  const out = {};
  if (!fs.existsSync(dir)) return out;
  const items = (x) => (Array.isArray(x) ? x : x == null ? [] : [x])
    .map((v) => (typeof v === 'string' ? { fb: v, response: '' } : { fb: String(v.fb ?? ''), response: String(v.response ?? '') }))
    .filter((v) => v.fb.trim());
  for (const name of fs.readdirSync(dir)) {
    const m = /^v(\d+)\.json$/.exec(name);
    if (!m) continue;
    let j;
    try { j = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8')); } catch (e) { throw new Error(`feedback/${name} is not valid JSON: ${e.message}`); }
    out[+m[1]] = {
      file: `feedback/${name}`,
      summary: j.summary || '',
      overall: items(j.overall),
      cuts: Object.fromEntries(Object.entries(j.cuts || {}).map(([k, v]) => [k, items(v)]).filter(([, v]) => v.length)),
    };
  }
  return out;
}

function feedbackWarnings(fb, v, scenes) {
  if (!fb) return [];
  const w = [];
  const ids = new Set(scenes.map((s) => s.id));
  for (const id of Object.keys(fb.cuts)) if (!ids.has(id)) w.push(`${fb.file}: cut ${id} is not in the current scene table (if you renamed the ID, update the FB too)`);
  const open = [...fb.overall.map((x) => ['overall', x]), ...Object.entries(fb.cuts).flatMap(([id, xs]) => xs.map((x) => [id, x]))].filter(([, x]) => !x.response.trim());
  for (const [id, x] of open) w.push(`v${v} feedback has no response (response in ${fb.file}): ${id} "${x.fb.slice(0, 40)}"`);
  return w;
}

// For cuts with FB, line up the "first / last" frames of the previous and current versions (top row = previous, bottom row = current)
function compareCuts(dir, version, fb, cuts, asp, warnings) {
  if (!fb || !Object.keys(fb.cuts).length) return [];
  const prev = path.join(dir, `v${version - 1}`, tag(asp), 'cuts');
  const cd = path.join(dir, 'compare');
  const out = [];
  for (const c of cuts.filter((x) => fb.cuts[x.id])) {
    const before = [cutPng(prev, c.id, 'start'), cutPng(prev, c.id, 'end')];
    if (!before.every((p) => fs.existsSync(p))) {
      warnings.push(`${c.id}: no frames from the previous version (v${version - 1}/${tag(asp)}), so the comparison image cannot be made`);
      continue;
    }
    fs.mkdirSync(cd, { recursive: true });
    const p = cutPng(cd, c.id, `v${version - 1}-v${version}`);
    tile([...before, c.startPng, c.endPng], p, 2, 480);
    out.push({ cut: c.id, path: p });
  }
  return out;
}

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const br = (s) => esc(s).replace(/\n/g, '<br>');
const clock = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;
const num = (x) => String(+x.toFixed(2));

// Seconds → bar and beat (1-based). Off the beat grid, output the beat count as a decimal (within half a frame counts as on the beat)
const beats = (n) => `${num(n)} beat${Math.abs(n) === 1 ? '' : 's'}`;
function beatPos(t, B, fps) {
  const b = ((t - B.offset) * B.bpm) / 60;
  const on = Math.abs(b - Math.round(b)) <= (0.5 / fps) * (B.bpm / 60);
  const n = on ? Math.round(b) : b;
  if (n < 0) return `${beats(n)} (before the ${num(B.offset)}s offset)`;
  return on ? `bar ${Math.floor(n / B.beatsPerBar) + 1} beat ${(n % B.beatsPerBar) + 1} (${beats(n)})` : beats(n);
}

function cutsheetHtml(sb, dir, P, B, meta, brand) {
  const rel = (p) => path.relative(dir, p).split(path.sep).join('/');
  const a0 = sb.aspects[0];
  const cuts = sb.per[a0].cuts;
  const others = sb.aspects.slice(1);
  const prevFb = sb.feedback;
  const v = sb.version;
  const spb = 60 / B.bpm;
  const barSec = spb * B.beatsPerBar;
  const bars = Math.ceil((meta.duration - B.offset) / barSec - 1e-9);
  const assets = Object.keys(meta.assets || {}).length + Object.keys(meta.clips || {}).length;
  const [w, h] = SIZES[a0];
  const PAL = ['#DCE6F0', '#F3E3D3', '#E2EEDD', '#EEE0EC', '#F4EDCF', '#DDEBEA'];
  const sceneAt = (t) => meta.scenes.findIndex((s) => t >= s.start - 1e-9 && t < s.end - 1e-9);
  const verify = (x) => (Array.isArray(x) ? x : x ? String(x).split('\n') : []).map((l) => {
    const k = { '●': 'ok', '▲': 'risk', '◆': 'next', '✓': 'done', '○': 'todo' }[String(l).trim()[0]] || '';
    return `<div class="vf ${k}">${esc(l)}</div>`;
  }).join('');
  const L = [];
  L.push(`<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">`);
  L.push(`<title>Cut sheet v${v}: ${esc(sb.title || path.basename(P.proj))}</title>`);
  L.push(`<style>
:root{--ink:#1d1f22;--mute:#666b72;--line:#d9dce0;--paper:#fff;--bg:#f5f6f7;--fb:#fff4b8;--fbline:#e8d675}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.6 -apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:2200px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:13px;letter-spacing:.12em;color:var(--mute);margin:0 0 4px}h2{font-size:22px;margin:0 0 12px}h3{font-size:16px;margin:32px 0 8px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 16px}.chips span{background:var(--paper);border:1px solid var(--line);border-radius:99px;padding:2px 10px;font-size:12px}
.summary{background:var(--paper);border-left:4px solid var(--ink);padding:8px 12px;margin:0 0 16px;max-width:960px}
dl.info{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;background:var(--paper);border:1px solid var(--line);padding:12px 16px;max-width:960px;margin:0}
dl.info dt{color:var(--mute)}dl.info dd{margin:0}.sw{display:inline-block;width:14px;height:14px;border:1px solid var(--line);vertical-align:-2px;margin-right:4px}
.guide{color:var(--mute);font-size:12px;max-width:960px}
.tl{background:var(--paper);border:1px solid var(--line);padding:8px;overflow-x:auto}
.tl .row{position:relative;height:18px;min-width:640px}.tl .bar,.tl .pre{position:absolute;top:0;height:18px;border-right:1px solid var(--paper);font-size:10px;padding:2px 3px;white-space:nowrap;overflow:hidden}.tl .pre{background:repeating-linear-gradient(45deg,#eee 0 4px,#f8f8f8 4px 8px);color:var(--mute)}
.tl .cuts{position:relative;height:22px;min-width:640px;margin-top:2px}.tl .cuts a{position:absolute;top:0;height:20px;border-left:2px solid var(--ink);padding-left:3px;font-size:11px;color:var(--ink);text-decoration:none;white-space:nowrap;overflow:hidden}
.wrap{overflow-x:auto;background:var(--paper);border:1px solid var(--line)}
table{border-collapse:collapse;width:100%}th,td{border:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}
th{background:#eceef0;font-size:12px;white-space:nowrap;position:sticky;top:0}
table.cut td{min-width:120px}table.cut td.img{min-width:0;width:248px}table.cut td.no{min-width:0;white-space:nowrap;font-weight:700}
table.cut img{width:240px;display:block;border:1px solid var(--line)}table.cut td.other img{width:120px}
td.fb,th.fb{background:var(--fb);border-color:var(--fbline);min-width:220px}td.fb textarea{width:100%;min-height:96px;border:1px solid var(--fbline);background:#fffbe0;font:inherit;padding:4px}
.vf{font-size:12px}.vf.ok{color:#1a7f37}.vf.risk{color:#b45309}.vf.next{color:#1d4ed8}.vf.done{color:#555}.vf.todo{color:#888}
.sm{font-size:12px;color:var(--mute)}table.resp img{width:360px;display:block}
.warn{background:#fff1f0;border:1px solid #f3c1bd;padding:8px 12px;max-width:960px}.warn li{font-size:12px}
.overall textarea{width:100%;max-width:960px;min-height:80px;background:var(--fb);border:1px solid var(--fbline);font:inherit;padding:6px}
button{font:inherit;padding:6px 14px;border:1px solid var(--ink);background:var(--ink);color:#fff;border-radius:4px;cursor:pointer}
</style></head><body><main>`);
  const d = new Date();  // local date to match the viewer's calendar (toISOString is UTC, which gives the previous day between 0 and 9 a.m. JST)
  L.push(`<h1>CUT SHEET v${v} · ${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} · PROPOSAL BY CLAUDE</h1>`);
  L.push(`<h2>${esc(sb.title || path.basename(P.proj))}</h2>`);
  L.push(`<p class="guide">1 row = 1 cut. Pictures are the first and last frames; motion is described in words.</p>`);
  if (prevFb?.summary) L.push(`<p class="summary">${br(prevFb.summary)}</p>`);
  L.push(`<div class="chips"><span>${num(B.bpm)} BPM</span><span>${num(meta.duration / barSec)} bars = ${num(meta.duration)} s</span><span>${cuts.length} cuts</span><span>${w}×${h}·${sb.fps}fps</span><span>${assets} assets</span><span>source ${sb.source_hash.slice(0, 12)}</span></div>`);
  if (sb.warnings.length) L.push(`<div class="warn"><b>${sb.warnings.length} warning(s)</b><ul>${sb.warnings.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>`);
  // Project info
  const colors = brand?.colors ? Object.entries(brand.colors).map(([k, c]) => `<span class="sw" style="background:${esc(c)}"></span>${esc(k)} ${esc(c)}`).join('　') : '—';
  const fonts = brand?.fonts ? Object.entries(brand.fonts).map(([k, x]) => `${esc(k)}: ${esc(x.family || x.file || '')}`).join(' / ') : '—';
  L.push('<h3>Project info</h3><dl class="info">');
  for (const [k, val] of [
    ['Project name', esc(sb.title || path.basename(P.proj))],
    ['Total duration', `${num(meta.duration)} s (${sb.frames} frames)`],
    ['Tempo / BPM', `${num(B.bpm)} BPM, ${B.beatsPerBar} beats per bar${B.offset ? `, offset ${B.offset}s` : ''}`],
    ['Aspect', sb.aspects.map((a) => `${a} (${SIZES[a].join('×')})`).join(' / ') + ` · ${sb.fps}fps`],
    ['Deliverables', `final.mp4 / poster.png / contact.png (${(meta.aspects || []).join(' · ')})`],
    ['Reference', br(meta.reference || '—')],
    ['Colors', colors],
    ['Fonts', fonts],
  ]) L.push(`<dt>${k}</dt><dd>${val}</dd>`);
  L.push('</dl>');
  // Timeline strip: 1 cell = 1 bar, scenes as color bands, cut numbers below. Bars and cuts share the same 0 s–duration axis
  const pct = (t) => +((Math.min(t, meta.duration) / meta.duration) * 100).toFixed(4);
  L.push('<h3>Timeline</h3><div class="tl"><div class="row">');
  if (B.offset > 0) L.push(`<div class="pre" style="left:0%;width:${pct(B.offset)}%">offset</div>`);
  for (let i = 0; i < bars; i++) {
    const t0 = B.offset + i * barSec;
    const k = sceneAt(t0);
    L.push(`<div class="bar" style="left:${pct(t0)}%;width:${+(pct(t0 + barSec) - pct(t0)).toFixed(4)}%;background:${k < 0 ? '#eee' : PAL[k % PAL.length]}">${i + 1}${k >= 0 ? ` ${esc(meta.scenes[k].id)}` : ''}</div>`);
  }
  L.push('</div><div class="cuts">');
  cuts.forEach((c, i) => {
    const s = meta.scenes[i];
    L.push(`<a href="#cut-${esc(c.id)}" style="left:${pct(s.start)}%;width:${+(pct(s.end) - pct(s.start)).toFixed(4)}%">${String(i + 1).padStart(2, '0')} ${esc(c.id)}</a>`);
  });
  L.push('</div></div>');
  // Responses to the previous version's FB
  if (prevFb) {
    const rows = [...prevFb.overall.map((x) => ['overall', x, null]), ...Object.entries(prevFb.cuts).flatMap(([id, xs]) => xs.map((x) => [id, x, id]))];
    L.push(`<h3>Responses to v${v - 1} FB</h3><div class="wrap"><table class="resp"><tr><th>Target</th><th>FB</th><th>Response in v${v}</th><th>Cut</th></tr>`);
    for (const [target, x, id] of rows) {
      const cmp = id && sb.compare.find((c) => c.cut === id);
      const cell = cmp ? `<a href="${esc(rel(cmp.path))}"><img src="${esc(rel(cmp.path))}" alt="v${v - 1} vs v${v}"></a><div class="sm">top v${v - 1} / bottom v${v} (first, last)</div>` : id ? `<a href="#cut-${esc(id)}">${esc(id)}</a>` : '—';
      L.push(`<tr><td>${esc(target)}</td><td>${br(x.fb)}</td><td>${x.response.trim() ? br(x.response) : '<b style="color:#b42318">(blank)</b>'}</td><td>${cell}</td></tr>`);
    }
    L.push(`</table></div><p class="sm">Original FB: ${esc(prevFb.file)} (previous version: <a href="v${v - 1}/cutsheet.html">v${v - 1}/cutsheet.html</a>)</p>`);
  }
  // Cut sheet
  L.push('<h3>Cut sheet</h3><div class="wrap"><table class="cut"><tr>');
  const head = ['No.', 'Start (s · beat)', 'Length', 'First frame', 'Last frame', ...(others.length ? ['Other aspects (first)'] : []), 'Picture', 'Motion', 'Transition to next', 'Text', 'Sound', 'Verify'];
  L.push(head.map((x) => `<th>${x}</th>`).join('') + '<th class="fb">FB</th></tr>');
  cuts.forEach((c, i) => {
    const s = meta.scenes[i];
    const len = s.end - s.start;
    const other = others.map((a) => { const oc = sb.per[a].cuts[i]; return `<div class="sm">${a}</div><img src="${esc(rel(oc.startPng))}" alt="${a} first">`; }).join('');
    L.push(`<tr id="cut-${esc(c.id)}">`
      + `<td class="no">${String(i + 1).padStart(2, '0')}<div class="sm">${esc(c.id)}</div></td>`
      + `<td>${clock(s.start)}–${clock(s.end)}<div class="sm">${beatPos(s.start, B, sb.fps)}</div></td>`
      + `<td>${num(len)}s<div class="sm">${beats(len / spb)}</div></td>`
      + `<td class="img"><img src="${esc(rel(c.startPng))}" alt="first ${num(c.start)}s"><div class="sm">${num(c.start)}s</div></td>`
      + `<td class="img"><img src="${esc(rel(c.endPng))}" alt="last ${num(c.end)}s"><div class="sm">${num(c.end)}s</div></td>`
      + (others.length ? `<td class="other">${other}</td>` : '')
      + `<td>${s.message ? `<b>${br(s.message)}</b><br>` : ''}${br(s.screen)}</td>`
      + `<td>${br(fmtMotion(s.motion))}</td>`
      + `<td>${br(s.transition)}</td>`
      + `<td>${br(s.text ?? s.narration)}</td>`
      + `<td>${br(s.sound)}</td>`
      + `<td>${verify(s.verify)}</td>`
      + `<td class="fb"><textarea data-cut="${esc(c.id)}" placeholder="FB on this cut"></textarea></td></tr>`);
  });
  L.push('</table></div>');
  L.push(`<h3>Overall FB</h3><div class="overall"><textarea id="overall" placeholder="FB not tied to a cut"></textarea></div>`);
  L.push(`<p><button id="save">Save FB (v${v}.json)</button></p>`);
  L.push(`<h3>How to give feedback</h3><ul class="guide">
<li>Write in the yellow FB column at the right end of each row. Write overall FB in the box below the table.</li>
<li>When done, click "Save FB" to save <code>v${v}.json</code> and put it at <code>feedback/v${v}.json</code> in the project (to write it by hand: <code>{"cuts":{"${esc(cuts[0]?.id ?? 's1')}":"…"},"overall":"…"}</code>).</li>
<li>The agent writes its responses in <code>response</code> in the same file, and they appear at the top of the next version's (v${v + 1}) cut sheet as "Responses to v${v} FB".</li>
<li>The Verify column is the agent's notes: ● done ▲ risk / unresolved ◆ assets / next steps ✓ confirmed.</li>
</ul>`);
  L.push(`<script>
document.getElementById('save').onclick = () => {
  const cuts = {};
  document.querySelectorAll('textarea[data-cut]').forEach((t) => { if (t.value.trim()) cuts[t.dataset.cut] = { fb: t.value.trim(), response: '' }; });
  const data = { cuts };
  const o = document.getElementById('overall').value.trim();
  if (o) data.overall = { fb: o, response: '' };
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\\n'], { type: 'application/json' }));
  a.download = 'v${v}.json';
  a.click();
};
</script></main></body></html>`);
  return L.join('\n') + '\n';
}

// ── approve ───────────────────────────────────────────────────
function cmdApprove(P, f) {
  if (!f.by || f.by === true) die('Specify --by "<person who gave the OK>"');
  const sbp = path.join(P.out, 'storyboard', 'storyboard.json');
  if (!fs.existsSync(sbp)) die('No storyboard yet. Run storyboard first, show it to a human and get an OK', 3);
  const sb = JSON.parse(fs.readFileSync(sbp, 'utf8'));
  const hash = sourceHash(P);
  if (sb.source_hash !== hash) die('The sources changed after the storyboard was made. Rebuild the storyboard and show it again', 3);
  const ap = { approved_by: f.by, note: f.note === true ? '' : f.note || '', approved_at: new Date().toISOString(), source_hash: hash, storyboard: sbp };
  fs.writeFileSync(path.join(P.proj, 'approval.json'), JSON.stringify(ap, null, 2) + '\n');
  console.log(JSON.stringify({ approval: path.join(P.proj, 'approval.json'), source_hash: hash }, null, 2));
}

function requireApproval(P) {
  const ap = path.join(P.proj, 'approval.json');
  if (!fs.existsSync(ap)) die('No approval. Show the storyboard to a human, get an OK, then approve (final render only after approval)', 3);
  const a = JSON.parse(fs.readFileSync(ap, 'utf8'));
  const hash = sourceHash(P);
  if (a.source_hash !== hash) die('The sources changed after approval. Rebuild the storyboard and get the OK again', 3);
  return a;
}

// ── final ──────────────────────────────────────────────────────
async function cmdFinal(P, f) {
  const approval = requireApproval(P);
  const S = await openSession(P, f);
  try {
    const { meta, N } = S;
    const aspects = !f.aspect || f.aspect === 'all' ? meta.aspects : f.aspect.split(',');
    const check = await determinismCheck(S, aspects[0]);
    if (!check.ok) throw new Error(`Not rendering because the determinism check failed: ${JSON.stringify(check)}`);
    const deliver = path.join(P.out, 'deliver');
    fs.mkdirSync(deliver, { recursive: true });
    const beats = beatsInfo(meta.audio, meta.duration);
    let audio = null;
    const wav = path.join(S.work, 'audio.wav');
    if (hasAudio(meta)) audio = renderAudio({ duration: N / meta.fps, audio: meta.audio, scenes: meta.scenes, outPath: wav, work: S.work, base: P.proj });
    if (audio?.bgm) audio.bgm = { ...audio.bgm, stem: undefined, mid: undefined };
    const results = {};
    for (const asp of aspects) {
      const fd = path.join(S.work, `frames-${tag(asp)}`);
      fs.rmSync(fd, { recursive: true, force: true });
      fs.mkdirSync(fd, { recursive: true });
      await S.size(asp);
      const t0 = Date.now();
      for (let i = 0; i < N; i++) fs.writeFileSync(path.join(fd, `${String(i).padStart(6, '0')}.png`), await S.frame(i / meta.fps));
      const renderSec = (Date.now() - t0) / 1000;
      const od = path.join(deliver, tag(asp));
      fs.mkdirSync(od, { recursive: true });
      const mp4 = path.join(od, 'final.mp4');
      const args = ['-y', '-v', 'error', '-framerate', String(meta.fps), '-i', path.join(fd, '%06d.png')];
      if (audio) args.push('-i', wav);
      args.push('-map', '0:v');
      if (audio) args.push('-map', '1:a');
      args.push('-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p',
        '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-r', String(meta.fps));
      if (audio) args.push(...AAC);
      args.push('-map_metadata', '-1', '-fflags', '+bitexact', '-flags:v', '+bitexact', '-flags:a', '+bitexact', '-movflags', '+faststart', mp4);
      run('ffmpeg', args);
      const frameAt = (t) => path.join(fd, `${String(Math.max(0, Math.min(N - 1, Math.round(t * meta.fps)))).padStart(6, '0')}.png`);
      const posterT = meta.poster ?? sceneKeys(meta.scenes[meta.scenes.length - 1])[0];
      fs.copyFileSync(frameAt(posterT), path.join(od, 'poster.png'));
      let bt = beats.beats;
      const step = Math.ceil(bt.length / 48);
      if (step > 1) bt = bt.filter((_, i) => i % step === 0);
      tile(bt.map(frameAt), path.join(od, 'contact.png'), 6, 320);
      if (!f['keep-frames']) fs.rmSync(fd, { recursive: true, force: true });
      const loud = audio ? measureLoudness(mp4) : null;
      results[asp] = { mp4, poster: path.join(od, 'poster.png'), contact: path.join(od, 'contact.png'), renderSec, probe: probe(mp4), loudness: loud && { lufs: loud.lufs, lra: loud.lra, truePeakDb: loud.truePeakDb, samplePeakDb: loud.samplePeakDb } };
    }
    // All sources and the README
    const src = path.join(deliver, 'source');
    fs.rmSync(src, { recursive: true, force: true });
    for (const p of listFiles(P.proj, [P.out])) {
      const d = path.join(src, path.relative(P.proj, p));
      fs.mkdirSync(path.dirname(d), { recursive: true });
      fs.copyFileSync(p, d);
    }
    if (P.brand && !P.brand.startsWith(P.proj + path.sep)) fs.copyFileSync(P.brand, path.join(src, 'brand.json'));
    fs.writeFileSync(path.join(src, 'beats.json'), JSON.stringify(beats, null, 2));
    const manifest = { source_hash: S.hash, approval, check, audio, fonts: S.fonts, used: await S.manifest(), results };
    fs.writeFileSync(path.join(deliver, 'manifest.json'), JSON.stringify(manifest, null, 2));
    fs.writeFileSync(path.join(deliver, 'README.md'), readme(meta, manifest, deliver));
    console.log(JSON.stringify({ deliver, results, audio, used: manifest.used }, null, 2));
  } finally {
    await S.close();
  }
}

function readme(meta, m, deliver) {
  const L = [`# ${meta.title || 'motion-video'}`, ''];
  L.push(`- Duration ${meta.duration}s / ${meta.fps}fps / H.264 yuv420p CRF16 / motion blur with ${meta.subframes ?? 4} subframes`);
  L.push(`- Approval: ${m.approval.approved_by} (${m.approval.approved_at}) "${m.approval.note}"`);
  L.push(`- source_hash: \`${m.source_hash}\``);
  if (m.audio) L.push(`- Sound (mixed WAV): ${m.audio.lufs ?? '-'} LUFS / true peak ${m.audio.truePeakDb ?? '-'} dBFS${m.audio.bgm ? ` / BGM ${m.audio.bgm.style} (${m.audio.bgm.progression.join(' → ')}, seed ${m.audio.bgm.seed}, ${path.basename(m.audio.bgm.soundfont)})` : ' / sound effects only'}`);
  L.push('', '| Aspect | Video | Poster | Contact | Resolution | Frames | Loudness (mp4) | sha256 |', '|---|---|---|---|---|---|---|---|');
  for (const [asp, r] of Object.entries(m.results)) {
    const rel = (p) => path.relative(deliver, p);
    const ld = r.loudness ? `${r.loudness.lufs} LUFS / TP ${r.loudness.truePeakDb} dBFS` : '-';
    L.push(`| ${asp} | [final.mp4](${rel(r.mp4)}) | [poster.png](${rel(r.poster)}) | [contact.png](${rel(r.contact)}) | ${r.probe.width}x${r.probe.height} | ${r.probe.nb_frames} | ${ld} | \`${r.probe.sha256.slice(0, 16)}\` |`);
  }
  L.push('', 'Re-render: `node ' + path.join(HERE, 'render.mjs') + ' final source/` (source/ contains approval.json)');
  return L.join('\n') + '\n';
}

// ── stills (redraw only the given seconds) ───────────────────────
async function cmdStills(P, f) {
  const S = await openSession(P, f);
  try {
    const { meta } = S;
    const asp = f.aspect || meta.aspects[0];
    await S.size(asp);
    let times;
    if (f.times) times = String(f.times).split(',').map(Number);
    else if (f.from != null) {
      const a = Math.round(+f.from * meta.fps);
      const b = Math.round(+(f.to ?? f.from) * meta.fps);
      times = [];
      for (let i = a; i <= b; i++) times.push(i / meta.fps);
    } else die('Specify --times or --from/--to');
    const dir = path.join(P.out, 'stills', tag(asp));
    fs.mkdirSync(dir, { recursive: true });
    const paths = [];
    for (const t of times) {
      const p = path.join(dir, `t-${t.toFixed(3)}s.png`);
      fs.writeFileSync(p, await S.frame(t));
      paths.push(p);
    }
    if (paths.length > 1) tile(paths, path.join(dir, 'sheet.png'), Math.min(6, paths.length), 320);
    console.log(JSON.stringify({ stills: paths, sheet: paths.length > 1 ? path.join(dir, 'sheet.png') : null }, null, 2));
  } finally {
    await S.close();
  }
}

// ── check / probe ──────────────────────────────────────────────
async function cmdCheck(P, f) {
  const S = await openSession(P, f);
  try {
    const r = await determinismCheck(S, f.aspect || S.meta.aspects[0], f.frame ? +f.frame : undefined);
    console.log(JSON.stringify(r, null, 2));
    if (!r.ok) process.exitCode = 1;
  } finally {
    await S.close();
  }
}

export function probe(file) {
  const j = JSON.parse(run('ffprobe', ['-v', 'error', '-show_entries', 'stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,pix_fmt,duration:format=duration', '-of', 'json', file]));
  const v = j.streams.find((s) => s.codec_type === 'video');
  const a = j.streams.find((s) => s.codec_type === 'audio');
  const [n, d] = v.r_frame_rate.split('/').map(Number);
  return {
    width: v.width, height: v.height, fps: n / d, nb_frames: +v.nb_frames, video_duration: +v.duration,
    format_duration: +j.format.duration, codec: v.codec_name, pix_fmt: v.pix_fmt, audio: a ? a.codec_name : null,
    sha256: sha(fs.readFileSync(file)),
  };
}

async function main() {
  const { cmd, pos, f } = parseArgs(process.argv.slice(2));
  if (cmd === 'probe') return console.log(JSON.stringify(probe(path.resolve(pos[0])), null, 2));
  const cmds = { storyboard: cmdStoryboard, check: cmdCheck, approve: cmdApprove, final: cmdFinal, stills: cmdStills };
  if (!cmds[cmd]) die('Usage: render.mjs <storyboard|check|approve|final|stills|probe> <project> [options] (details in SKILL.md)');
  await cmds[cmd](resolveProject(pos, f), f);
}

main().catch((e) => die(e.stack || e.message));
