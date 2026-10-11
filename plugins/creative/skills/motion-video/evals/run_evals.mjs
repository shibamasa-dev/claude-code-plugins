#!/usr/bin/env node
// run_evals.mjs — actually renders each case in evals.json and grades it mechanically.
//   sh evals/run.sh [--only <name>] [--work <dir>]
// It launches Chrome, so run it outside Claude Code's Bash sandbox.
// All outputs (mp4, PNG, generated assets) go to --work (default under os.tmpdir()); nothing is written to the skill's repository.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const EVALS = path.dirname(fileURLToPath(import.meta.url));
const SKILL = path.dirname(EVALS);
const RENDER = path.join(SKILL, 'scripts', 'render.mjs');
const args = process.argv.slice(2);
const opt = (k) => (args.includes(k) ? args[args.indexOf(k) + 1] : null);
const WORK = path.resolve(opt('--work') || path.join(os.tmpdir(), `motion-video-evals-${Date.now()}`));
fs.mkdirSync(WORK, { recursive: true });
const spec = JSON.parse(fs.readFileSync(path.join(EVALS, 'evals.json'), 'utf8'));

function sh(bin, a, cwd = WORK, env = process.env) {
  const t0 = Date.now();
  const r = spawnSync(bin, a, { cwd, env, encoding: 'utf8', maxBuffer: 1 << 28 });
  return { code: r.status, out: r.stdout || '', err: r.stderr || '', sec: (Date.now() - t0) / 1000 };
}
const render = (...a) => sh('node', [RENDER, ...a]);
const json = (s) => { try { return JSON.parse(s); } catch { return null; } };

function copyFixture(name, as = name) {
  const dst = path.join(WORK, as);
  fs.rmSync(dst, { recursive: true, force: true });
  fs.cpSync(path.join(EVALS, 'fixtures', name), dst, { recursive: true });
  return dst;
}

// Make a screenshot-like PNG and a short live-action-clip-like mp4 with ffmpeg
function makeMedia(dir) {
  fs.mkdirSync(path.join(dir, 'assets'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'clips'), { recursive: true });
  const boxes = [
    [0, 0, 1280, 64, '2F5D50'], [0, 64, 220, 736, 'E3E7EA'], [24, 100, 172, 28, 'C9D1D6'], [24, 150, 150, 28, 'C9D1D6'],
    [260, 100, 300, 150, 'FFFFFF'], [590, 100, 300, 150, 'FFFFFF'], [920, 100, 300, 150, 'FFFFFF'],
    [284, 200, 120, 26, '3F9C94'], [614, 200, 180, 26, '6B4E9B'], [944, 200, 90, 26, 'C5D86D'],
    [260, 280, 960, 470, 'FFFFFF'], [300, 600, 70, 110, '2F5D50'], [400, 520, 70, 190, '2F5D50'], [500, 450, 70, 260, '2F5D50'], [600, 560, 70, 150, '2F5D50'],
  ].map(([x, y, w, h, c]) => `drawbox=x=${x}:y=${y}:w=${w}:h=${h}:color=0x${c}:t=fill`).join(',');
  const a = sh('ffmpeg', ['-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=0xF6F7F9:s=1280x800', '-vf', boxes, '-frames:v', '1', path.join(dir, 'assets', 'screenshot.png')]);
  const b = sh('ffmpeg', ['-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30:duration=3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path.join(dir, 'clips', 'demo.mp4')]);
  if (a.code || b.code) throw new Error(`Failed to generate assets: ${a.err}${b.err}`);
}

// Share of the PNG covered by the brand color (±24)
function colorShare(png, hex) {
  const r = spawnSync('ffmpeg', ['-v', 'error', '-i', png, '-vf', 'scale=192:-2', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 26 });
  const buf = r.stdout;
  const [R, G, B] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  let hit = 0;
  for (let i = 0; i < buf.length; i += 3) if (Math.abs(buf[i] - R) <= 24 && Math.abs(buf[i + 1] - G) <= 24 && Math.abs(buf[i + 2] - B) <= 24) hit++;
  return hit / (buf.length / 3);
}

// Integrated loudness of only seconds a–b of the mp4 (null if silent)
function windowLufs(file, [a, b]) {
  const r = sh('ffmpeg', ['-hide_banner', '-nostats', '-ss', String(a), '-t', String(b - a), '-i', file, '-af', 'ebur128', '-f', 'null', '-']);
  const m = /I:\s*(-?[\d.]+|-inf)\s*LUFS/.exec(r.err.slice(r.err.lastIndexOf('Summary:')));
  return m && m[1] !== '-inf' ? parseFloat(m[1]) : null;
}

// ── Running a case ──────────────────────────────────────────────
async function runRenderCase(c) {
  const R = [];
  const add = (text, passed, evidence) => R.push({ text, passed: !!passed, evidence: String(evidence) });
  const e = c.expect;
  const dir = copyFixture(c.fixture, c.name);
  if (c.media) makeMedia(dir);
  const brandArgs = c.brand === 'references' ? ['--brand', path.join(SKILL, 'references', 'brand.example.json')] : [];
  const P = path.relative(WORK, dir);

  // 1. Storyboard
  const sb = render('storyboard', P, '--aspect', e.storyboardAspect || 'all', ...brandArgs);
  const sbj = json(fs.existsSync(path.join(dir, 'out/storyboard/storyboard.json')) ? fs.readFileSync(path.join(dir, 'out/storyboard/storyboard.json'), 'utf8') : 'null');
  add('the storyboard command succeeds and outputs storyboard.md / storyboard.json', sb.code === 0 && sbj && fs.existsSync(path.join(dir, 'out/storyboard/storyboard.md')), `exit=${sb.code} ${sb.err.slice(-300)}`);
  if (!sbj) return R;
  const asps = Object.keys(sbj.per);
  const nStills = asps.reduce((s, a) => s + sbj.per[a].stills.length, 0);
  add('there is one representative frame (still) per aspect × scene', nStills === asps.length * c.expect.scenes && sbj.per[asps[0]].stills.every((x) => fs.existsSync(x.path)), `stills=${nStills} expected=${asps.length}×${c.expect.scenes}`);
  const ev = asps.every((a) => ['contact', 'strip', 'phone'].every((k) => fs.existsSync(sbj.per[a][k])) && (!e.loop || fs.existsSync(sbj.per[a].seam || '')));
  add('pre-render evidence (contact / strip / phone' + (e.loop ? ' / seam' : '') + ') is output', ev, asps.map((a) => `${a}: ${['contact', 'strip', 'phone', 'seam'].filter((k) => sbj.per[a][k]).join(',')}`).join(' '));
  add(`determinism check (same frame drawn twice, hashes match${e.loop ? ', loop seam continuity' : ''}) is OK`, sbj.check.ok, JSON.stringify(sbj.check));
  if (e.audio) {
    const a = sbj.sound;
    const ok = a && [a.preview, a.spectrogram].every((p) => fs.existsSync(p) && fs.statSync(p).size > 1000);
    add('a sound preview (preview.wav) and spectrogram (spectrogram.png) are output at the storyboard stage', ok, a ? `${a.preview} ${a.spectrogram} lufs=${a.lufs}` : 'no sound');
  }
  if (e.music) add(`storyboard BGM is as specified (style ${e.music.style}, MIDI present)`, sbj.sound?.bgm?.style === e.music.style && sbj.sound.bgm.notes > 0 && fs.existsSync(sbj.sound.mid || ''), JSON.stringify(sbj.sound?.bgm && { style: sbj.sound.bgm.style, notes: sbj.sound.bgm.notes, progression: sbj.sound.bgm.progression }));
  if (e.brandColor) {
    const shares = sbj.per[asps[0]].stills.map((x) => colorShare(x.path, e.brandColor));
    add(`some representative frame has the brand.json primary color ${e.brandColor} on at least ${e.brandMinShare * 100}% of it`, Math.max(...shares) >= e.brandMinShare, `share=${shares.map((s) => s.toFixed(3)).join(',')}`);
  }

  // 2. Approval gate (final stops before approval)
  if (e.gate) {
    const g = render('final', P, ...brandArgs);
    add('final before approval stops with exit 3 and makes no mp4', g.code === 3 && !fs.existsSync(path.join(dir, 'out/deliver')), `exit=${g.code} ${g.err.trim().slice(0, 120)}`);
  }
  const ap = render('approve', P, '--by', 'eval', '--note', 'automatic approval by eval', ...brandArgs);
  add('approve after storyboard succeeds', ap.code === 0, `exit=${ap.code} ${ap.err.slice(-200)}`);

  // 3. Final render (twice)
  const f1 = render('final', P, ...brandArgs);
  const r1 = json(f1.out);
  add('final succeeds', f1.code === 0 && r1, `exit=${f1.code} ${f1.sec.toFixed(1)}s ${f1.err.slice(-300)}`);
  if (!r1) return R;
  for (const [asp, [w, h]] of Object.entries(e.aspects)) {
    const pr = r1.results[asp]?.probe;
    if (!pr) { add(`${asp} mp4 exists`, false, 'not in results'); continue; }
    const frames = Math.round(e.duration * e.fps);
    add(`${asp}: resolution ${w}x${h}`, pr.width === w && pr.height === h, `${pr.width}x${pr.height}`);
    add(`${asp}: fps ${e.fps}, ${frames} frames (duration ${e.duration}s)`, pr.fps === e.fps && pr.nb_frames === frames && Math.abs(pr.format_duration - e.duration) <= 0.1, `fps=${pr.fps} nb_frames=${pr.nb_frames} format_duration=${pr.format_duration}`);
    add(`${asp}: H.264 / yuv420p${e.audio ? ' / audio aac' : ''}`, pr.codec === 'h264' && pr.pix_fmt === 'yuv420p' && (!e.audio || pr.audio === 'aac'), `${pr.codec} ${pr.pix_fmt} audio=${pr.audio}`);
    const od = path.dirname(r1.results[asp].mp4);
    add(`${asp}: poster.png and contact.png are in the deliverables`, ['poster.png', 'contact.png'].every((f) => fs.existsSync(path.join(od, f))), od);
  }
  const deliver = r1.deliver;
  add('the deliverables contain README.md, manifest.json and source/video.js', ['README.md', 'manifest.json', 'source/video.js'].every((f) => fs.existsSync(path.join(deliver, f))), deliver);
  if (e.audio) {
    for (const asp of Object.keys(e.aspects)) {
      const ld = r1.results[asp]?.loudness;
      add(`${asp}: mp4 loudness is -14 LUFS ±1 with true peak at or below -1 dBFS (measured on the mp4 with ebur128)`, ld && Math.abs(ld.lufs + 14) <= 1 && ld.truePeakDb <= -1, JSON.stringify(ld));
    }
  }
  if (e.music) {
    const mp4 = r1.results[Object.keys(e.aspects)[0]].mp4;
    const l = windowLufs(mp4, e.music.window);
    add(`BGM is audible in ${e.music.window.join('–')}s where there are no sound effects (louder than -35 LUFS)`, l != null && l > -35, `lufs=${l}`);
    add('the deliverables manifest records the BGM (style, soundfont, MIDI hash)', r1.audio?.bgm?.style === e.music.style && r1.audio.bgm.soundfontSha256 && r1.audio.bgm.midiSha256, JSON.stringify(r1.audio?.bgm && { style: r1.audio.bgm.style, soundfont: r1.audio.bgm.soundfont, midi: r1.audio.bgm.midiSha256?.slice(0, 16) }));
  }
  if (e.silentWindow) {
    const l = windowLufs(r1.results[Object.keys(e.aspects)[0]].mp4, e.silentWindow);
    add(`in an SFX-only video, ${e.silentWindow.join('–')}s without cues is silent (no BGM added)`, l == null || l < -60, `lufs=${l}`);
  }
  if (e.media) {
    const u = r1.used;
    add('the image asset (screenshot) was actually drawn', (u.images.shot || 0) > 0, JSON.stringify(u.images));
    add('at least 2 distinct live-action clip frames were drawn (the clip moves)', (u.clipFramesDistinct.demo || 0) >= 2, JSON.stringify(u.clipFramesDistinct));
  }
  const sha1 = Object.fromEntries(Object.entries(r1.results).map(([a, r]) => [a, r.probe.sha256]));
  const f2 = render('final', P, ...brandArgs);
  const r2 = json(f2.out);
  for (const asp of e.determinism) {
    const s2 = r2?.results?.[asp]?.probe?.sha256;
    add(`${asp}: sha256 of two mp4 renders from the same input match`, s2 && s2 === sha1[asp], `${sha1[asp]?.slice(0, 16)} / ${s2?.slice(0, 16)}`);
  }

  // 4. Changing the sources after approval stops it
  if (e.gate) {
    fs.appendFileSync(path.join(dir, 'video.js'), '\n// change after approval\n');
    const g2 = render('final', P, ...brandArgs);
    add('changing video.js after approval makes final stop with exit 3', g2.code === 3, `exit=${g2.code} ${g2.err.trim().slice(0, 120)}`);
    const g3 = render('approve', P, '--by', 'eval', ...brandArgs);
    add('re-approving without rebuilding the storyboard also stops', g3.code === 3, `exit=${g3.code} ${g3.err.trim().slice(0, 120)}`);
  }
  return R;
}

// Cut sheet and FB round trip: storyboard → add FB and re-run → v2 with "Responses to v1 FB", comparison images, warnings for missing responses
async function runCutsheetCase(c) {
  const R = [];
  const add = (text, passed, evidence) => R.push({ text, passed: !!passed, evidence: String(evidence) });
  const e = c.expect;
  const dir = copyFixture(c.fixture, c.name);
  const P = path.relative(WORK, dir);
  const sbDir = path.join(dir, 'out/storyboard');
  const sbJson = () => json(fs.existsSync(path.join(sbDir, 'storyboard.json')) ? fs.readFileSync(path.join(sbDir, 'storyboard.json'), 'utf8') : 'null');
  const html = () => (fs.existsSync(path.join(sbDir, 'cutsheet.html')) ? fs.readFileSync(path.join(sbDir, 'cutsheet.html'), 'utf8') : '');
  const row = (h, id) => (h.split(`<tr id="cut-${id}">`)[1] || '').split('</tr>')[0];
  const tag = e.aspect.replace(':', 'x');

  // 1. v1
  const s1 = render('storyboard', P);
  const j1 = sbJson();
  const h1 = html();
  add('storyboard succeeds and outputs cutsheet.html (version v1)', s1.code === 0 && h1 && j1?.version === 1, `exit=${s1.code} version=${j1?.version} ${s1.err.slice(-200)}`);
  const heads = [...h1.matchAll(/<th[^>]*>([^<]*)<\/th>/g)].map((m) => m[1]);
  const missing = e.columns.filter((col) => !heads.includes(col));
  add(`the cut sheet has the columns ${e.columns.join(' / ')}`, !missing.length, `missing=${missing.join(',') || 'none'} headers=${heads.join(',')}`);
  const pngs = e.cuts.flatMap((id) => ['start', 'end'].map((w) => path.join(sbDir, tag, 'cuts', `${id}-${w}.png`)));
  const differ = e.cuts.filter((id) => !fs.readFileSync(path.join(sbDir, tag, 'cuts', `${id}-start.png`)).equals(fs.readFileSync(path.join(sbDir, tag, 'cuts', `${id}-end.png`))));
  add(`each of the ${e.cuts.length} cuts has "first" and "last" images, and the two frames differ`, pngs.every((p) => fs.existsSync(p)) && differ.length === e.cuts.length, `exist=${pngs.filter((p) => fs.existsSync(p)).length}/${pngs.length} differ=${differ.join(',')}`);
  const cutPng = (id, w) => fs.readFileSync(path.join(sbDir, tag, 'cuts', `${id}-${w}.png`));
  const sameAsNext = e.cuts.slice(0, -1).filter((id, i) => cutPng(id, 'end').equals(cutPng(e.cuts[i + 1], 'start')));
  add('"last" is the last frame of that cut (not the same picture as the next cut\'s "first")', !sameAsNext.length, `same as next first=${sameAsNext.join(',') || 'none'}`);
  const srcs = [...h1.matchAll(/<img src="([^"]+)"/g)].map((m) => m[1]);
  add('images in cutsheet.html use relative paths and all open from cutsheet.html', srcs.length >= e.cuts.length * 2 && srcs.every((s) => !path.isAbsolute(s) && fs.existsSync(path.join(sbDir, s))), `img=${srcs.length} e.g.=${srcs[0]}`);
  const r4 = row(h1, e.beatRow.id);
  add(`start and length are shown in both seconds and beats (${e.beatRow.id}: ${e.beatRow.texts.join(' / ')})`, e.beatRow.texts.every((x) => r4.includes(x)), r4.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 200));
  const s1b = render('storyboard', P);
  add('re-running without FB keeps version v1 (no v2/)', s1b.code === 0 && sbJson()?.version === 1 && !fs.existsSync(path.join(sbDir, 'v2')), `version=${sbJson()?.version} v2=${fs.existsSync(path.join(sbDir, 'v2'))}`);

  // 1b. Japanese cut IDs (non-ASCII becomes _) and a cut that starts before the offset (audio.offset)
  const jd = copyFixture(c.fixture, `${c.name}-ja`);
  const jsrc = path.join(jd, 'video.js');
  let js = fs.readFileSync(jsrc, 'utf8');
  for (const [from, to] of Object.entries(e.jaIds)) js = js.replace(`{ id: '${from}',`, `{ id: '${to}',`);
  // Another cut whose ASCII ID equals a replaced name (the same string as the old naming <replaced>-<8-char hash>)
  const lookalike = `${'_'.repeat(Object.values(e.jaIds)[0].length)}-${crypto.createHash('sha256').update(Object.values(e.jaIds)[0]).digest('hex').slice(0, 8)}`;
  js = js.replace(`{ id: '${e.lookalikeOf}',`, `{ id: '${lookalike}',`);
  fs.writeFileSync(jsrc, js.replace('bpm: 120,', `bpm: 120, offset: ${e.offset.value},`));
  // Build in a time zone whose date always differs from UTC (UTC-12 in the UTC morning, UTC+14 in the afternoon)
  const tz = new Date().getUTCHours() < 12 ? 'Etc/GMT+12' : 'Pacific/Kiritimati';
  const sj = sh('node', [RENDER, 'storyboard', path.relative(WORK, jd)], WORK, { ...process.env, TZ: tz });
  const localDate = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const hj = fs.existsSync(path.join(jd, 'out/storyboard/cutsheet.html')) ? fs.readFileSync(path.join(jd, 'out/storyboard/cutsheet.html'), 'utf8') : '';
  const jaSrc = [...Object.values(e.jaIds), lookalike].map((id) => [...row(hj, id).matchAll(/<img src="([^"]+)"/g)].map((m) => m[1]));
  const jaFiles = jaSrc.flat();
  add(`Japanese cut IDs of the same length (${Object.values(e.jaIds).join(', ')}) and an ASCII ID resembling a replaced name (${lookalike}) still get separate first / last image files`, sj.code === 0 && jaFiles.length === 6 && new Set(jaFiles).size === 6 && jaFiles.every((f) => fs.existsSync(path.join(jd, 'out/storyboard', f))), `exit=${sj.code} img=${jaFiles.join(',')}`);
  const h1Date = (/CUT SHEET v\d+ · (\d{4}-\d{2}-\d{2})/.exec(hj) || [])[1];
  add(`the date in the cut sheet heading is the local date of the machine that built it (${localDate} with TZ=${tz}; UTC is ${new Date().toISOString().slice(0, 10)})`, h1Date === localDate, `heading=${h1Date}`);
  const tl = (hj.split('<div class="tl">')[1] || '').split('</div></div>')[0];
  const barLeft = [...tl.matchAll(/<div class="bar" style="left:([\d.]+)%/g)].map((m) => +m[1]);
  const cutLeft = [...tl.matchAll(/<a href="#cut-[^"]*" style="left:([\d.]+)%/g)].map((m) => +m[1]);
  const T = e.timeline;
  const near = (a, b) => a.length === b.length && a.every((x, i) => Math.abs(x - (b[i] / T.duration) * 100) < 0.01);
  add(`bars and cuts in the timeline strip share the same 0–${T.duration} s axis (bar starts ${T.barStarts.join('/')}s, cut starts ${T.cutStarts.join('/')}s)`, near(barLeft, T.barStarts) && near(cutLeft, T.cutStarts), `bar left%=${barLeft.join(',')} cut left%=${cutLeft.join(',')}`);
  const pre = row(hj, Object.values(e.jaIds)[0]).replace(/<[^>]+>/g, ' ');
  const post = row(hj, Object.values(e.jaIds)[1]).replace(/<[^>]+>/g, ' ');
  add(`a cut starting before the ${e.offset.value}s offset shows a negative beat, not bar 0 / beat 0 (${e.offset.pre} / ${e.offset.post})`, pre.includes(e.offset.pre) && !/bar 0|beat 0/.test(pre) && post.includes(e.offset.post), `${pre.replace(/\s+/g, ' ').slice(0, 80)} | ${post.replace(/\s+/g, ' ').slice(0, 80)}`);

  // 2. Add FB → v2
  const fbFile = path.join(dir, 'feedback', 'v1.json');
  fs.mkdirSync(path.dirname(fbFile), { recursive: true });
  fs.writeFileSync(fbFile, JSON.stringify(e.feedback, null, 2));
  const s2 = render('storyboard', P);
  const j2 = sbJson();
  const h2 = html();
  add('adding FB and re-running advances to v2 and keeps v1/', s2.code === 0 && j2?.version === 2 && fs.existsSync(path.join(sbDir, 'v1', 'cutsheet.html')) && fs.existsSync(path.join(sbDir, 'v1', tag, 'cuts', `${e.cuts[0]}-start.png`)), `exit=${s2.code} version=${j2?.version} v1=${fs.readdirSync(sbDir).filter((x) => /^v\d+$/.test(x))}`);
  const arch = json(fs.readFileSync(path.join(sbDir, 'v1', 'storyboard.json'), 'utf8'));
  const archPaths = arch ? Object.values(arch.per).flatMap((v) => [...v.cuts.flatMap((x) => [x.startPng, x.endPng]), ...v.stills.map((x) => x.path), v.contact]) : [];
  const v1dir = path.join(sbDir, 'v1') + path.sep;
  add('after v2 is built, image paths in v1/storyboard.json point to existing files inside v1/', archPaths.length && archPaths.every((p) => p.startsWith(v1dir) && fs.existsSync(p)), `count=${archPaths.length} outside=${archPaths.filter((p) => !p.startsWith(v1dir)).slice(0, 2).join(',')}`);
  const fbTexts = [e.feedback.overall, ...Object.values(e.feedback.cuts).map((x) => (typeof x === 'string' ? x : x.fb))];
  add('the cut sheet shows a "Responses to v1 FB" table containing every FB text', h2.includes('Responses to v1 FB') && fbTexts.every((t) => h2.includes(t)), `heading=${h2.includes('Responses to v1 FB')} missing=${fbTexts.filter((t) => !h2.includes(t))}`);
  const unans = e.unanswered.map((id) => j2?.warnings?.find((w) => w.includes('has no response') && w.includes(`${id} "`)));
  const wrongly = e.answered.filter((id) => j2?.warnings?.some((w) => w.includes('has no response') && w.includes(`${id} "`)));
  add(`FB without a response (${e.unanswered.join(', ')}) is warned about, and FB with one (${e.answered.join(', ')}) is not`, unans.every(Boolean) && !wrongly.length && s2.out.includes('has no response'), `warnings=${JSON.stringify(j2?.warnings)}`);
  const fbCuts = Object.keys(e.feedback.cuts);
  const cmp = fs.existsSync(path.join(sbDir, 'compare')) ? fs.readdirSync(path.join(sbDir, 'compare')) : [];
  const dims = cmp.map((f) => sh('ffprobe', ['-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', path.join(sbDir, 'compare', f)]).out.trim().split(',').map(Number));
  add(`only cuts with FB (${fbCuts.join(', ')}) get a v1 vs v2 comparison image (first, last × 2 versions = 2×2)`, cmp.length === fbCuts.length && fbCuts.every((id) => cmp.some((f) => f.startsWith(`${id}-`))) && dims.every(([w, h]) => w / h > 1.5 && w / h < 2.1), `compare=${cmp.join(',')} size=${dims.map((d) => d.join('x')).join(',')}`);

  // 3. Write responses and re-run → warnings disappear, version stays v2
  const answered = { ...e.feedback, overall: { fb: e.feedback.overall, response: 'Increased the whitespace 1.2x' }, cuts: Object.fromEntries(Object.entries(e.feedback.cuts).map(([k, v]) => [k, typeof v === 'string' ? { fb: v, response: 'Done' } : v])) };
  fs.writeFileSync(fbFile, JSON.stringify(answered, null, 2));
  const s3 = render('storyboard', P);
  const j3 = sbJson();
  add('writing responses and re-running removes the missing-response warnings, version stays v2 (v1/ still kept)', s3.code === 0 && j3?.version === 2 && !j3.warnings.some((w) => w.includes('has no response')) && fs.existsSync(path.join(sbDir, 'v1')) && !fs.existsSync(path.join(sbDir, 'v3')), `version=${j3?.version} warnings=${JSON.stringify(j3?.warnings)}`);

  // 4. Approval hash: FB files are part of the sources
  const ap = render('approve', P, '--by', 'eval', '--note', 'automatic approval by eval');
  fs.writeFileSync(path.join(dir, 'feedback', 'v2.json'), JSON.stringify({ cuts: { [e.cuts[0]]: 'New FB' } }));
  const ap2 = render('final', P);
  add('approve after storyboard passes, and adding FB afterwards makes final stop with exit 3 (FB is in the approval hash)', ap.code === 0 && ap2.code === 3, `approve=${ap.code} final=${ap2.code} ${ap2.err.trim().slice(0, 120)}`);
  return R;
}

async function runContracts() {
  const R = [];
  const add = (text, passed, evidence) => R.push({ text, passed: !!passed, evidence: String(evidence) });
  // State carried over from previous frames is detected (confirms the check can fail)
  const st = copyFixture('bad-stateful');
  const c1 = render('check', path.relative(WORK, st));
  add('check gives exit 1 and ok:false for a render that carries state over from previous frames', c1.code === 1 && json(c1.out)?.ok === false, `exit=${c1.code} ${c1.out.replace(/\s+/g, ' ').slice(0, 160)}`);
  // Math.random throws during drawing
  const rd = copyFixture('bad-random');
  const c2 = render('storyboard', path.relative(WORK, rd));
  add('storyboard fails with a reason for a render that uses Math.random', c2.code !== 0 && c2.err.includes('Math.random'), `exit=${c2.code} ${c2.err.split('\n').find((l) => l.includes('Math.random'))?.slice(0, 120)}`);
  // A broken loop seam is detected
  const lp = copyFixture('multi-aspect', 'broken-loop');
  const src = path.join(lp, 'video.js');
  fs.writeFileSync(src, fs.readFileSync(src, 'utf8').replace('(2 * Math.PI * t) / PERIOD', '(2 * Math.PI * t) / (PERIOD * 1.25)'));
  const c3 = render('check', path.relative(WORK, lp), '--brand', path.join(SKILL, 'references', 'brand.example.json'));
  const j3 = json(c3.out);
  add('check fails at the seam for a loop whose period is off', c3.code === 1 && j3?.loop?.ok === false, `exit=${c3.code} loop=${JSON.stringify(j3?.loop)}`);
  // Spring and beat-grid math
  const M = await import(pathToFileURL(path.join(SKILL, 'scripts', 'runtime', 'motion.js')).href);
  const peak = (p) => { let m = 0; for (let t = 0; t < 4; t += 1 / 240) m = Math.max(m, M.spring(t, p)); return m; };
  add('spring is 0 at t<=0 and converges to 1 later (4 presets)', Object.keys(M.PRESETS).every((p) => M.spring(0, p) === 0 && Math.abs(1 - M.spring(6, p)) < 1e-3), Object.keys(M.PRESETS).map((p) => `${p}:${M.spring(6, p).toFixed(5)}`).join(' '));
  add('default does not overshoot; snappy and playful overshoot slightly (< 10%)', peak('default') <= 1 + 1e-6 && peak('snappy') > 1 && peak('snappy') < 1.1 && peak('playful') > 1 && peak('playful') < 1.1, `default=${peak('default').toFixed(4)} snappy=${peak('snappy').toFixed(4)} playful=${peak('playful').toFixed(4)}`);
  const keys = [{ t: 0, v: 0 }, { t: 0.5, v: 100 }, { t: 0.8, v: 40 }];
  const dv = (t) => (M.springTrack(t + 1e-4, keys) - M.springTrack(t - 1e-4, keys)) / 2e-4;
  add('springTrack keeps value and velocity continuous when the target changes', Math.abs(M.springTrack(0.8 + 1e-9, keys) - M.springTrack(0.8 - 1e-9, keys)) < 1e-4 && Math.abs(dv(0.8 + 2e-4) - dv(0.8 - 2e-4)) < 5, `v(0.8)=${M.springTrack(0.8, keys).toFixed(3)} velocity ${dv(0.8 - 2e-4).toFixed(1)}→${dv(0.8 + 2e-4).toFixed(1)}`);
  // Composition: same input gives the same MIDI; changing style or seed changes it
  const Mu = await import(pathToFileURL(path.join(SKILL, 'scripts', 'music.mjs')).href);
  const inp = { duration: 8, audio: { bpm: 120, peaks: [4] }, scenes: [{ start: 0, end: 4 }, { start: 4, end: 8 }] };
  const smf = (music) => Mu.toSmf(Mu.compose({ ...inp, music }));
  const base = { progression: ['Am', 'F', 'C', 'G'], style: 'calm', seed: 3 };
  const a1 = smf(base);
  add('composition gives the same MIDI for the same input and a different MIDI when style or seed changes (an SMF starting with MThd)', a1.equals(smf(base)) && !a1.equals(smf({ ...base, style: 'upbeat' })) && !a1.equals(smf({ ...base, seed: 4 })) && a1.subarray(0, 4).toString() === 'MThd', `bytes=${a1.length} upbeat=${smf({ ...base, style: 'upbeat' }).length}`);
  let bad = null;
  try { Mu.parseChord('Hm'); } catch (err) { bad = err.message; }
  const cm7 = Mu.parseChord('Cmaj7');
  add('chord name parsing (Cmaj7 = C E G B; unreadable names stop with a reason)', cm7.root === 0 && cm7.intervals.join() === '0,4,7,11' && Mu.parseChord('C/E').bass === 4 && !!bad, `Cmaj7=${cm7.intervals} C/E bass=${Mu.parseChord('C/E').bass} Hm→${bad}`);
  const bg = M.beatGrid(120, 0, 4);
  add('beatGrid(120): beat 4 = 2.0s, start of bar 2 = 4.0s', bg.beat(4) === 2 && bg.bar(2) === 4, `beat(4)=${bg.beat(4)} bar(2)=${bg.bar(2)}`);
  return R;
}

// ── main ───────────────────────────────────────────────────────
const only = opt('--only');
if (only && !spec.evals.some((c) => c.name === only)) {
  console.error(`No case matches --only: ${only}\nCases: ${spec.evals.map((c) => c.name).join(', ')}`);
  process.exit(2);
}
const all = [];
console.log(`work: ${WORK}`);
for (const c of spec.evals) {
  if (only && c.name !== only) continue;
  const t0 = Date.now();
  let res;
  try {
    res = c.kind === 'contracts' ? await runContracts() : c.kind === 'cutsheet' ? await runCutsheetCase(c) : await runRenderCase(c);
  } catch (err) {
    res = [{ text: 'the case runs to completion without an exception', passed: false, evidence: err.stack }];
  }
  const pass = res.filter((r) => r.passed).length;
  const sec = (Date.now() - t0) / 1000;
  all.push({ id: c.id, name: c.name, passed: pass === res.length, pass, total: res.length, sec, expectations: res });
  fs.mkdirSync(path.join(WORK, 'grading'), { recursive: true });
  fs.writeFileSync(path.join(WORK, 'grading', `${c.name}.json`), JSON.stringify({ expectations: res }, null, 2));
  console.log(`\n[${pass === res.length ? 'PASS' : 'FAIL'}] ${c.id}. ${c.name}  ${pass}/${res.length}  (${sec.toFixed(1)}s)`);
  for (const r of res) console.log(`  ${r.passed ? '✓' : '✗'} ${r.text}${r.passed ? '' : `\n      → ${r.evidence.slice(0, 400)}`}`);
}
const P = all.reduce((s, c) => s + c.pass, 0);
const T = all.reduce((s, c) => s + c.total, 0);
const summary = { pass_rate: T ? +(P / T).toFixed(4) : 0, assertions: `${P}/${T}`, cases_passed: `${all.filter((c) => c.passed).length}/${all.length}`, work: WORK, cases: all.map(({ expectations, ...x }) => x) };
fs.writeFileSync(path.join(WORK, 'results.json'), JSON.stringify({ ...summary, cases: all }, null, 2));
console.log(`\npass_rate=${summary.pass_rate} (${summary.assertions}) cases=${summary.cases_passed}\nresults: ${path.join(WORK, 'results.json')}`);
process.exit(P === T && T > 0 ? 0 : 1);
