#!/usr/bin/env node
// render.mjs — motion-video の実行本体（依存ゼロ: node 22+（グローバル WebSocket）/ system Chrome / ffmpeg）
//
//   node render.mjs storyboard <project> [--aspect 9:16|all] [--brand brand.json] [--out dir]  （カット表 cutsheet.html。feedback/v<N>.json があれば版を進める）
//   node render.mjs check      <project> [--frame 300]
//   node render.mjs approve    <project> --by "<OK を出した人>" --note "<OK の発言>"
//   node render.mjs final      <project> [--aspect all|16:9,9:16] [--keep-frames]
//   node render.mjs stills     <project> (--times 1.2,3.4 | --from 3 --to 4) [--aspect 16:9]
//   node render.mjs probe      <file.mp4>
//
// Chrome は Claude Code の Bash sandbox 内では起動しない。sandbox 外（dangerouslyDisableSandbox）で実行する。
// 出力の既定は <project>/out、作業用の連番 PNG は os.tmpdir()/motion-video/ 配下。
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

// ── Chrome を CDP で直接操作する ────────────────────────────────
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
  die('Chrome / Chromium が見つからない。MOTION_VIDEO_CHROME に実行ファイルのパスを入れる');
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
    const to = setTimeout(() => rej(new Error(`Chrome が起動しない（Claude Code の sandbox 内なら sandbox 外で実行する）\n${buf.slice(-800)}`)), 20000);
    proc.stderr.on('data', (d) => {
      buf += d;
      const m = buf.match(/DevTools listening on (ws:\S+)/);
      if (m) { clearTimeout(to); res(m[1]); }
    });
    proc.on('exit', (c) => rej(new Error(`Chrome が終了した (code ${c})\n${buf.slice(-800)}`)));
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
  // Chrome の終了を待ってからプロファイルを消す（kill 直後は Chrome がまだ書いていて消せないことがある）
  const close = async () => {
    try { sock.close(); } catch {}
    const exited = proc.exitCode != null ? Promise.resolve() : new Promise((r) => proc.once('exit', r));
    proc.kill('SIGKILL');
    await Promise.race([exited, new Promise((r) => setTimeout(r, 3000))]);
    try { fs.rmSync(ud, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }); } catch {}
  };
  return { send, close };
}

// ── ローカル http（素材を同一 origin で配る。file:// だと canvas が汚染されて書き出せない） ──
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

// ── プロジェクト ───────────────────────────────────────────────
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
  if (!pos[0]) die('プロジェクトのフォルダを指定する');
  const proj = path.resolve(pos[0]);
  if (!fs.existsSync(path.join(proj, 'video.js'))) die(`${proj}/video.js が無い`);
  const brand = f.brand ? path.resolve(f.brand) : fs.existsSync(path.join(proj, 'brand.json')) ? path.join(proj, 'brand.json') : null;
  const out = path.resolve(f.out || path.join(proj, 'out'));
  return { proj, brand, out };
}

// 承認の対象＝プロジェクト内の全ファイル（out/ と approval.json を除く）＋外部の brand.json とそこから参照するファイル
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
    if (!fs.existsSync(src)) die(`クリップが無い: ${src}`);
    if (!c.fps) die(`meta.clips.${k}.fps を指定する（ばらすコマ数/秒）`);
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
    if (!counts[k]) die(`クリップ ${k} からコマが取れない`);
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
      if (i > 400) throw new Error('harness が読み込めない');
      await new Promise((r) => setTimeout(r, 50));
    }
    const meta = await ev('__mv.load()');
    const problems = metaErrors(meta);
    if (problems.length) throw new Error('video.js の meta が不正:\n- ' + problems.join('\n- '));
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
  if (!(m.duration > 0)) e.push('duration（秒）を正の数で');
  if (!(m.fps > 0)) e.push('fps を正の数で');
  for (const a of m.aspects || []) if (!SIZES[a]) e.push(`未対応の aspect ${a}（${Object.keys(SIZES).join(' / ')}）`);
  if (!(m.aspects || []).length) e.push('aspects を1つ以上（例 ["9:16","1:1","16:9"]）');
  if (!(m.scenes || []).length) e.push('scenes を1つ以上');
  return e;
}

// シーン契約・時間割の点検（警告。止めはしない）
function sceneWarnings(m) {
  const w = [];
  const N = m.duration * m.fps;
  if (Math.abs(N - Math.round(N)) > 1e-6) w.push(`duration×fps が整数でない（${N}）。コマ数は ${Math.round(N)} に丸める`);
  const sc = m.scenes;
  if (Math.abs(sc[0].start) > 1e-6) w.push(`最初のシーンが 0 秒から始まっていない（${sc[0].start}）`);
  for (let i = 1; i < sc.length; i++) if (Math.abs(sc[i].start - sc[i - 1].end) > 1e-6) w.push(`${sc[i - 1].id}→${sc[i].id} の間に隙間か重なり（${sc[i - 1].end}→${sc[i].start}）`);
  if (Math.abs(sc[sc.length - 1].end - m.duration) > 1e-6) w.push(`最後のシーンの終わり（${sc[sc.length - 1].end}）が尺（${m.duration}）と合わない`);
  const dup = sc.map((s) => s.id).filter((id, i, a) => a.indexOf(id) !== i);
  if (dup.length) w.push(`シーンの id が重複している（${[...new Set(dup)].join(', ')}）。カット表の画像と FB は id で引くので一意にする`);
  for (const s of sc) {
    const miss = ['message', 'screen', 'motion', 'sound', 'transition'].filter((k) => !s[k]);
    if (miss.length) w.push(`${s.id}: シーン契約の欄が空（${miss.join(', ')}）`);
    if (/^(cut|hard ?cut|カット|ハードカット)$/i.test(String(s.transition || '').trim())) w.push(`${s.id}: トランジションがハードカット。画面上の物を次のシーンの物に変える形にする`);
  }
  return w;
}

// 動きの量の列から「4秒以上、目立つ変化が無い区間」を探す
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

// 同じコマを「最初に描いた時」と「他のコマを描いた後」で比べる。前フレームの状態を持ち越していれば割れる
async function determinismCheck(S, asp, frameNo) {
  await S.size(asp);
  const { N, meta } = S;
  const F = Math.max(0, Math.min(frameNo ?? 300, N - 1));
  const cold = sha(await S.frame(F / meta.fps));
  for (const j of [N - 1, 0, Math.max(0, F - 1), Math.min(N - 1, F + 13)]) await S.frame(j / meta.fps);
  const warm = sha(await S.frame(F / meta.fps));
  const res = { frame: F, cold: cold.slice(0, 16), warm: warm.slice(0, 16), ok: cold === warm };
  if (meta.loop) {
    // 継ぎ目（最後のコマ→最初のコマ）の変化量が、両側の隣り合うコマの変化量と同程度なら、位置も速度もつながっている。
    // t % duration で包んでも、ここは誤魔化せない（包んだだけで動きが周期的でなければ継ぎ目の差が跳ねる）
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
    // 最新の版はトップに作り直す。前の版（v<N>/）は残す
    fs.mkdirSync(dir, { recursive: true });
    for (const e of fs.readdirSync(dir)) if (!VERSION_DIR.test(e)) fs.rmSync(path.join(dir, e), { recursive: true, force: true });
    const fb = loadFeedback(P.proj);
    const version = 1 + Math.max(0, ...Object.keys(fb).map(Number));
    const warnings = [...sceneWarnings(meta), ...audioWarnings(meta.audio, meta.duration, meta.fps), ...feedbackWarnings(fb[version - 1], version - 1, meta.scenes)];
    const beats = beatsInfo(meta.audio, meta.duration);
    fs.writeFileSync(path.join(dir, 'beats.json'), JSON.stringify(beats, null, 2));
    const sound = hasAudio(meta) ? audioPreview(S, P, dir, warnings) : null;
    const check = await determinismCheck(S, aspects[0], f.frame ? +f.frame : undefined);
    if (!check.ok) warnings.unshift(`決定論チェック失敗: ${JSON.stringify(check)}（render が前フレームの状態を持ち越している）`);
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
      // カット表: カットごとに「はじめ」（最初のコマ）と「おわり」（最後のコマ）
      const cutDir = path.join(ad, 'cuts');
      fs.mkdirSync(cutDir, { recursive: true });
      const cuts = [];
      for (const s of meta.scenes) {
        const c = { id: s.id, start: s.start, end: Math.max(s.start, s.end - 1 / meta.fps), startPng: cutPng(cutDir, s.id, 'start'), endPng: cutPng(cutDir, s.id, 'end') };
        fs.writeFileSync(c.startPng, await S.frame(c.start));
        fs.writeFileSync(c.endPng, await S.frame(c.end));
        cuts.push(c);
      }
      // contact: 1拍に1コマ（多すぎるときは間引いて最大 48 コマ）
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
      // strip: 最も速く動くコマの前後12コマ
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
      // phone: スマホの画面幅（390px）に縮めた代表コマ
      tile(stills.map((x) => x.path), path.join(ad, 'phone.png'), Math.min(4, stills.length), 390);
      const quiet = quietWindows(diffs, meta.fps);
      for (const [a, b] of quiet) warnings.push(`${asp}: ${a}〜${b}s に目立つ変化が無い（2〜4秒ごとに新しい視覚イベントを入れる）`);
      // seam: ループ作品なら最後のコマ・尺ちょうど・最初のコマを並べる
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
    for (const [fam, ok] of Object.entries(manifest.fonts)) if (!ok) warnings.push(`フォント「${fam}」がこのマシンに無い（fallback で描いている）。brand.json の fonts.*.file にフォントファイルを渡す`);
    const compare = compareCuts(dir, version, fb[version - 1], per[aspects[0]].cuts, aspects[0], warnings);
    const sb = { source_hash: S.hash, version, title: meta.title, duration: meta.duration, fps: meta.fps, frames: S.N, aspects, check, warnings, beats: path.join(dir, 'beats.json'), sound, per, manifest, scenes: meta.scenes, feedback: fb[version - 1] || null, compare };
    fs.writeFileSync(path.join(dir, 'storyboard.json'), JSON.stringify(sb, null, 2));
    fs.writeFileSync(path.join(dir, 'storyboard.md'), storyboardMd(sb, dir, P));
    fs.writeFileSync(path.join(dir, 'cutsheet.html'), cutsheetHtml(sb, dir, P, beats, meta, S.brandJson));
    // この版の写しを v<N>/ に残す（同じ版での再実行は上書き）
    const snap = path.join(dir, `v${version}`);
    fs.rmSync(snap, { recursive: true, force: true });
    fs.mkdirSync(snap);
    for (const e of fs.readdirSync(dir)) if (!VERSION_DIR.test(e)) fs.cpSync(path.join(dir, e), path.join(snap, e), { recursive: true });
    // 写しの storyboard.json は写しの中のファイルを指す（トップは次の版で上書きされる）
    const q = (p) => JSON.stringify(p + path.sep).slice(1, -1);
    fs.writeFileSync(path.join(snap, 'storyboard.json'), JSON.stringify(sb, null, 2).split(q(dir)).join(q(snap)));
    console.log(JSON.stringify({ storyboard: path.join(dir, 'storyboard.md'), cutsheet: path.join(dir, 'cutsheet.html'), version, source_hash: S.hash, check: check.ok, warnings, compare, sound: sound && { preview: sound.preview, spectrogram: sound.spectrogram, lufs: sound.lufs, truePeakDb: sound.truePeakDb }, per: Object.fromEntries(Object.entries(per).map(([k, v]) => [k, { contact: v.contact, strip: v.strip, phone: v.phone, seam: v.seam, stills: v.stills.map((x) => x.path) }])) }, null, 2));
  } finally {
    await S.close();
  }
}

const hasAudio = (meta) => !!(meta.audio?.cues?.length || meta.audio?.music);

// 絵コンテの段階で、本番と同じ手順で音を作り、試聴用 WAV とスペクトログラムを出す
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
  if (r.lufs != null && Math.abs(r.lufs - r.target) > 1) warnings.push(`音量 ${r.lufs} LUFS が ${r.target} ±1 に入っていない`);
  const tp = r.aac?.truePeakDb ?? r.truePeakDb;
  if (tp != null && tp > -1) warnings.push(`AAC に符号化した後のトゥルーピーク ${tp} dBFS が -1 を超えている`);
  const bands = bandLevels(preview);
  const sound = { preview, spectrogram: spec, mid, ...r, bands, bgm: r.bgm && { ...r.bgm, stem: undefined, mid: undefined } };
  fs.writeFileSync(path.join(ad, 'audio.json'), JSON.stringify(sound, null, 2));
  return sound;
}

function fmtMotion(m) {
  if (!m || typeof m === 'string') return m || '';
  return ['enter:入場', 'main:主', 'secondary:副', 'exit:退場'].map((kv) => { const [k, l] = kv.split(':'); return m[k] ? `${l}: ${m[k]}` : null; }).filter(Boolean).join(' / ');
}
const cell = (s) => String(s ?? '').replace(/\|/g, '\\|').replace(/\n/g, ' ');

function storyboardMd(sb, dir, P) {
  const rel = (p) => path.relative(dir, p);
  const a0 = sb.aspects[0];
  const L = [];
  L.push(`# 絵コンテ: ${sb.title || path.basename(P.proj)}`, '');
  L.push(`- 版 v${sb.version} / カット表: [cutsheet.html](cutsheet.html)（前の版は v<N>/ に残る）`);
  L.push(`- 尺 ${sb.duration}s / ${sb.fps}fps（${sb.frames} コマ） / ${sb.aspects.join(', ')} / source_hash \`${sb.source_hash.slice(0, 12)}\``);
  L.push(`- 決定論チェック（フレーム ${sb.check.frame} を2回描いて比較）: ${sb.check.ok ? 'OK' : '**NG**'}${sb.check.loop ? ` / ループ継ぎ目: ${sb.check.loop.ok ? 'OK' : '**NG**'}（継ぎ目の差 ${sb.check.loop.seam} / 隣接コマの差 ${sb.check.loop.neighbor}）` : ''}`);
  L.push('');
  if (sb.warnings.length) {
    L.push('## 警告', '');
    for (const w of sb.warnings) L.push(`- ${w}`);
    L.push('');
  }
  L.push('## シーン表', '');
  L.push('| # | 開始-終了 | 伝えること | 画面 | 動き | ナレーション | 音 | トランジション | 代表コマ |');
  L.push('|---|---|---|---|---|---|---|---|---|');
  for (const s of sb.scenes) {
    const st = sb.per[a0].stills.filter((x) => x.scene === s.id).map((x) => `[${x.t.toFixed(2)}s](${rel(x.path)})`).join(' ');
    L.push(`| ${cell(s.id)} | ${s.start.toFixed(2)}–${s.end.toFixed(2)}s | ${cell(s.message)} | ${cell(s.screen)} | ${cell(fmtMotion(s.motion))} | ${cell(s.narration)} | ${cell(s.sound)} | ${cell(s.transition)} | ${st} |`);
  }
  L.push('', '## 書き出し前の証拠', '');
  for (const [asp, v] of Object.entries(sb.per)) {
    L.push(`### ${asp}`, '');
    L.push(`- contact（1拍1コマ）: [contact.png](${rel(v.contact)})`);
    L.push(`- strip（最速の動き ${v.fastestAt}s 付近の連続12コマ、${v.stripFrom}s から）: [strip.png](${rel(v.strip)})`);
    L.push(`- phone（スマホ幅 390px に縮めた代表コマ）: [phone.png](${rel(v.phone)})`);
    if (v.seam) L.push(`- seam（最後のコマ / 尺ちょうど / 最初のコマ）: [seam.png](${rel(v.seam)})`);
    L.push('');
  }
  L.push(`- 拍: [beats.json](${rel(sb.beats)})`, '');
  if (sb.sound) {
    const a = sb.sound;
    L.push('## 音', '');
    L.push(`- 試聴（本番と同じ手順で混ぜたもの）: [preview.wav](${rel(a.preview)})${a.mid ? ` / BGM の MIDI: [bgm.mid](${rel(a.mid)})` : ''}`);
    L.push(`- スペクトログラム（縦=周波数の対数軸・白線=シーンの境目・緑線=ピーク）: [spectrogram.png](${rel(a.spectrogram)})`);
    L.push(`- 音量 ${a.lufs ?? '-'} LUFS（目標 ${a.target} ±1） / トゥルーピーク ${a.truePeakDb ?? '-'} dBFS（AAC に符号化した後 ${a.aac?.truePeakDb ?? '-'} dBFS） / ラウドネスレンジ ${a.lra ?? '-'} LU`);
    L.push(`- 帯域ごとの RMS（dBFS。スペクトログラムの最下段は対数軸でにじむので、こもりはこちらで見る）: ${Object.entries(a.bands).map(([k, v]) => `${k}（${BANDS[k][0]}–${BANDS[k][1] || '∞'}Hz）${v ?? '-'}`).join(' / ')}`);
    if (a.bgm) L.push(`- BGM: ${a.bgm.style} / ${a.bgm.progression.join(' → ')} / ${a.bgm.bars} 小節・${a.bgm.notes} 音 / seed ${a.bgm.seed} / 音源 ${path.basename(a.bgm.soundfont)}（fluidsynth ${a.bgm.fluidsynth}） / リバーブ ${a.bgm.reverb}（IR: ${a.bgm.ir}）`);
    L.push('');
  }
  L.push('## 次の手順', '');
  L.push('1. 自己採点（9項目 1〜10）を済ませ、最悪の3件を直してから人に見せる');
  L.push(`2. カット表 [cutsheet.html](cutsheet.html) を見せ、FB があれば \`feedback/v${sb.version}.json\` に書いてもらう（対応を書いて storyboard を回すと v${sb.version + 1} になる）`);
  L.push('3. **人の OK を得てから** `node render.mjs approve <project> --by "<名前>" --note "<OK の発言>"`');
  L.push('4. `node render.mjs final <project>`（承認後にソースが変わると拒否される）');
  return L.join('\n') + '\n';
}

// ── カット表と FB の往復 ───────────────────────────────────────
// 人は feedback/v<N>.json に版 N へのフィードバックを書き、エージェントは同じファイルの response に対応を書く。
// 次の storyboard は v<N+1> になる（版番号 = FB の付いた最新の版 + 1。FB が無ければ 1）
const VERSION_DIR = /^v\d+$/;
// ファイル名に使えない文字（日本語の ID を含む）は _ にし、~ と元の ID のハッシュを足して衝突させない。
// 置き換えの要らない ID は ~ を含みえないので、置き換えた ID の名前とは重ならない
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
    try { j = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8')); } catch (e) { throw new Error(`feedback/${name} が JSON として読めない: ${e.message}`); }
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
  for (const id of Object.keys(fb.cuts)) if (!ids.has(id)) w.push(`${fb.file}: カット ${id} が今のシーン表に無い（ID を変えたなら FB の側も直す）`);
  const open = [...fb.overall.map((x) => ['全体', x]), ...Object.entries(fb.cuts).flatMap(([id, xs]) => xs.map((x) => [id, x]))].filter(([, x]) => !x.response.trim());
  for (const [id, x] of open) w.push(`v${v} の FB に対応が書かれていない（${fb.file} の response）: ${id}「${x.fb.slice(0, 40)}」`);
  return w;
}

// FB の付いたカットについて、前の版と今の版の「はじめ / おわり」を並べる（上段=前の版・下段=今の版）
function compareCuts(dir, version, fb, cuts, asp, warnings) {
  if (!fb || !Object.keys(fb.cuts).length) return [];
  const prev = path.join(dir, `v${version - 1}`, tag(asp), 'cuts');
  const cd = path.join(dir, 'compare');
  const out = [];
  for (const c of cuts.filter((x) => fb.cuts[x.id])) {
    const before = [cutPng(prev, c.id, 'start'), cutPng(prev, c.id, 'end')];
    if (!before.every((p) => fs.existsSync(p))) {
      warnings.push(`${c.id}: 前の版（v${version - 1}/${tag(asp)}）のコマが無いので比較画像を作れない`);
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

// 秒 → 小節・拍（1始まり）。拍の格子から外れていれば拍数を小数で出す（半コマ以内は拍の上とみなす）
function beatPos(t, B, fps) {
  const b = ((t - B.offset) * B.bpm) / 60;
  const on = Math.abs(b - Math.round(b)) <= (0.5 / fps) * (B.bpm / 60);
  const n = on ? Math.round(b) : b;
  if (n < 0) return `${num(n)}拍（頭出し ${num(B.offset)}s より前）`;
  return on ? `小節${Math.floor(n / B.beatsPerBar) + 1} 拍${(n % B.beatsPerBar) + 1}（${n}拍）` : `${num(n)}拍`;
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
  L.push(`<title>カット表 v${v}: ${esc(sb.title || path.basename(P.proj))}</title>`);
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
.tl .row{display:flex;min-width:640px}.tl .bar{flex:1;border-right:1px solid var(--paper);font-size:10px;padding:2px 3px;white-space:nowrap;overflow:hidden}
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
  L.push(`<h1>CUT SHEET v${v} · ${new Date().toISOString().slice(0, 10)} · PROPOSAL BY CLAUDE</h1>`);
  L.push(`<h2>${esc(sb.title || path.basename(P.proj))}</h2>`);
  L.push(`<p class="guide">1行＝1カット。画は「はじめ」と「おわり」の2コマ、動きは文章で。</p>`);
  if (prevFb?.summary) L.push(`<p class="summary">${br(prevFb.summary)}</p>`);
  L.push(`<div class="chips"><span>${num(B.bpm)} BPM</span><span>${num(meta.duration / barSec)} 小節 = ${num(meta.duration)} 秒</span><span>${cuts.length} カット</span><span>${w}×${h}·${sb.fps}fps</span><span>素材 ${assets} 点</span><span>source ${sb.source_hash.slice(0, 12)}</span></div>`);
  if (sb.warnings.length) L.push(`<div class="warn"><b>警告 ${sb.warnings.length} 件</b><ul>${sb.warnings.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>`);
  // プロジェクト情報
  const colors = brand?.colors ? Object.entries(brand.colors).map(([k, c]) => `<span class="sw" style="background:${esc(c)}"></span>${esc(k)} ${esc(c)}`).join('　') : '—';
  const fonts = brand?.fonts ? Object.entries(brand.fonts).map(([k, x]) => `${esc(k)}: ${esc(x.family || x.file || '')}`).join(' / ') : '—';
  L.push('<h3>プロジェクト情報</h3><dl class="info">');
  for (const [k, val] of [
    ['プロジェクト名', esc(sb.title || path.basename(P.proj))],
    ['全体の尺', `${num(meta.duration)} 秒（${sb.frames} コマ）`],
    ['テンポ・BPM', `${num(B.bpm)} BPM・${B.beatsPerBar} 拍子${B.offset ? `・頭出し ${B.offset}s` : ''}`],
    ['画面比', sb.aspects.map((a) => `${a}（${SIZES[a].join('×')}）`).join(' / ') + ` · ${sb.fps}fps`],
    ['納品物', `final.mp4 / poster.png / contact.png（${(meta.aspects || []).join(' · ')}）`],
    ['参考', br(meta.reference || '—')],
    ['カラー', colors],
    ['フォント', fonts],
  ]) L.push(`<dt>${k}</dt><dd>${val}</dd>`);
  L.push('</dl>');
  // タイムライン帯: 1マス＝1小節、シーンを色帯で、その下にカット番号
  L.push('<h3>タイムライン</h3><div class="tl"><div class="row">');
  for (let i = 0; i < bars; i++) {
    const k = sceneAt(B.offset + i * barSec);
    L.push(`<div class="bar" style="background:${k < 0 ? '#eee' : PAL[k % PAL.length]}">${i + 1}${k >= 0 ? ` ${esc(meta.scenes[k].id)}` : ''}</div>`);
  }
  L.push('</div><div class="cuts">');
  cuts.forEach((c, i) => {
    const s = meta.scenes[i];
    L.push(`<a href="#cut-${esc(c.id)}" style="left:${(s.start / meta.duration) * 100}%;width:${((s.end - s.start) / meta.duration) * 100}%">${String(i + 1).padStart(2, '0')} ${esc(c.id)}</a>`);
  });
  L.push('</div></div>');
  // 前の版の FB への対応
  if (prevFb) {
    const rows = [...prevFb.overall.map((x) => ['全体', x, null]), ...Object.entries(prevFb.cuts).flatMap(([id, xs]) => xs.map((x) => [id, x, id]))];
    L.push(`<h3>v${v - 1} の FB への対応</h3><div class="wrap"><table class="resp"><tr><th>対象</th><th>FB</th><th>v${v} での対応</th><th>カット</th></tr>`);
    for (const [target, x, id] of rows) {
      const cmp = id && sb.compare.find((c) => c.cut === id);
      const cell = cmp ? `<a href="${esc(rel(cmp.path))}"><img src="${esc(rel(cmp.path))}" alt="v${v - 1} と v${v} の比較"></a><div class="sm">上段 v${v - 1} / 下段 v${v}（はじめ・おわり）</div>` : id ? `<a href="#cut-${esc(id)}">${esc(id)}</a>` : '—';
      L.push(`<tr><td>${esc(target)}</td><td>${br(x.fb)}</td><td>${x.response.trim() ? br(x.response) : '<b style="color:#b42318">未記入</b>'}</td><td>${cell}</td></tr>`);
    }
    L.push(`</table></div><p class="sm">FB の原本: ${esc(prevFb.file)}（前の版は <a href="v${v - 1}/cutsheet.html">v${v - 1}/cutsheet.html</a>）</p>`);
  }
  // カット表
  L.push('<h3>カット表</h3><div class="wrap"><table class="cut"><tr>');
  const head = ['No.', '開始（秒・拍）', '尺', 'はじめ', 'おわり', ...(others.length ? ['他の画角（はじめ）'] : []), '画の内容', '動き', '次へのつなぎ', 'テキスト', '音', '検証'];
  L.push(head.map((x) => `<th>${x}</th>`).join('') + '<th class="fb">FB</th></tr>');
  cuts.forEach((c, i) => {
    const s = meta.scenes[i];
    const len = s.end - s.start;
    const other = others.map((a) => { const oc = sb.per[a].cuts[i]; return `<div class="sm">${a}</div><img src="${esc(rel(oc.startPng))}" alt="${a} はじめ">`; }).join('');
    L.push(`<tr id="cut-${esc(c.id)}">`
      + `<td class="no">${String(i + 1).padStart(2, '0')}<div class="sm">${esc(c.id)}</div></td>`
      + `<td>${clock(s.start)}–${clock(s.end)}<div class="sm">${beatPos(s.start, B, sb.fps)}</div></td>`
      + `<td>${num(len)}秒<div class="sm">${num(len / spb)}拍</div></td>`
      + `<td class="img"><img src="${esc(rel(c.startPng))}" alt="はじめ ${num(c.start)}s"><div class="sm">${num(c.start)}s</div></td>`
      + `<td class="img"><img src="${esc(rel(c.endPng))}" alt="おわり ${num(c.end)}s"><div class="sm">${num(c.end)}s</div></td>`
      + (others.length ? `<td class="other">${other}</td>` : '')
      + `<td>${s.message ? `<b>${br(s.message)}</b><br>` : ''}${br(s.screen)}</td>`
      + `<td>${br(fmtMotion(s.motion))}</td>`
      + `<td>${br(s.transition)}</td>`
      + `<td>${br(s.text ?? s.narration)}</td>`
      + `<td>${br(s.sound)}</td>`
      + `<td>${verify(s.verify)}</td>`
      + `<td class="fb"><textarea data-cut="${esc(c.id)}" placeholder="このカットへの FB"></textarea></td></tr>`);
  });
  L.push('</table></div>');
  L.push(`<h3>全体への FB</h3><div class="overall"><textarea id="overall" placeholder="カットに紐づかない FB"></textarea></div>`);
  L.push(`<p><button id="save">FB を保存（v${v}.json）</button></p>`);
  L.push(`<h3>フィードバックの書き方</h3><ul class="guide">
<li>各行右端の黄色い FB 欄に書く。全体への FB は表の下の欄に書く。</li>
<li>書いたら「FB を保存」で <code>v${v}.json</code> を保存し、プロジェクトの <code>feedback/v${v}.json</code> に置く（手で書くなら <code>{"cuts":{"${esc(cuts[0]?.id ?? 's1')}":"…"},"overall":"…"}</code>）。</li>
<li>エージェントが同じファイルの <code>response</code> に対応を書き、次の版（v${v + 1}）のカット表の冒頭に「v${v} の FB への対応」として出す。</li>
<li>検証欄はエージェントのメモ: ● できたこと ▲ リスク・未解決 ◆ 素材・次の予定 ✓ 確認済み。</li>
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
  if (!f.by || f.by === true) die('--by "<OK を出した人>" を指定する');
  const sbp = path.join(P.out, 'storyboard', 'storyboard.json');
  if (!fs.existsSync(sbp)) die('絵コンテがまだ無い。先に storyboard を実行し、人に見せて OK を得る', 3);
  const sb = JSON.parse(fs.readFileSync(sbp, 'utf8'));
  const hash = sourceHash(P);
  if (sb.source_hash !== hash) die('絵コンテを作った後にソースが変わっている。storyboard を作り直して、もう一度見せる', 3);
  const ap = { approved_by: f.by, note: f.note === true ? '' : f.note || '', approved_at: new Date().toISOString(), source_hash: hash, storyboard: sbp };
  fs.writeFileSync(path.join(P.proj, 'approval.json'), JSON.stringify(ap, null, 2) + '\n');
  console.log(JSON.stringify({ approval: path.join(P.proj, 'approval.json'), source_hash: hash }, null, 2));
}

function requireApproval(P) {
  const ap = path.join(P.proj, 'approval.json');
  if (!fs.existsSync(ap)) die('承認が無い。storyboard を人に見せ、OK を得てから approve する（本番書き出しは承認後だけ）', 3);
  const a = JSON.parse(fs.readFileSync(ap, 'utf8'));
  const hash = sourceHash(P);
  if (a.source_hash !== hash) die('承認後にソースが変わっている。storyboard を作り直して、もう一度 OK をもらう', 3);
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
    if (!check.ok) throw new Error(`決定論チェック失敗のため書き出さない: ${JSON.stringify(check)}`);
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
    // ソース一式と README
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
  L.push(`- 尺 ${meta.duration}s / ${meta.fps}fps / H.264 yuv420p CRF16 / サブフレーム ${meta.subframes ?? 4} 枚のモーションブラー`);
  L.push(`- 承認: ${m.approval.approved_by}（${m.approval.approved_at}）「${m.approval.note}」`);
  L.push(`- source_hash: \`${m.source_hash}\``);
  if (m.audio) L.push(`- 音（混ぜた WAV）: ${m.audio.lufs ?? '-'} LUFS / トゥルーピーク ${m.audio.truePeakDb ?? '-'} dBFS${m.audio.bgm ? ` / BGM ${m.audio.bgm.style}（${m.audio.bgm.progression.join(' → ')}・seed ${m.audio.bgm.seed}・${path.basename(m.audio.bgm.soundfont)}）` : ' / 効果音のみ'}`);
  L.push('', '| 画角 | 動画 | ポスター | コンタクト | 解像度 | コマ数 | 音量（mp4） | sha256 |', '|---|---|---|---|---|---|---|---|');
  for (const [asp, r] of Object.entries(m.results)) {
    const rel = (p) => path.relative(deliver, p);
    const ld = r.loudness ? `${r.loudness.lufs} LUFS / TP ${r.loudness.truePeakDb} dBFS` : '-';
    L.push(`| ${asp} | [final.mp4](${rel(r.mp4)}) | [poster.png](${rel(r.poster)}) | [contact.png](${rel(r.contact)}) | ${r.probe.width}x${r.probe.height} | ${r.probe.nb_frames} | ${ld} | \`${r.probe.sha256.slice(0, 16)}\` |`);
  }
  L.push('', '再書き出し: `node ' + path.join(HERE, 'render.mjs') + ' final source/`（source/ に approval.json が入っている）');
  return L.join('\n') + '\n';
}

// ── stills（該当の秒だけ描き直す） ─────────────────────────────
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
    } else die('--times か --from/--to を指定する');
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
  if (!cmds[cmd]) die('使い方: render.mjs <storyboard|check|approve|final|stills|probe> <project> [options]（詳細は SKILL.md）');
  await cmds[cmd](resolveProject(pos, f), f);
}

main().catch((e) => die(e.stack || e.message));
