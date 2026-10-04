#!/usr/bin/env node
// run_evals.mjs — evals.json の各ケースを実際に書き出して機械判定する。
//   sh evals/run.sh [--only <name>] [--work <dir>]
// Chrome を起動するので Claude Code の Bash sandbox 外で実行する。
// 生成物（mp4・PNG・生成した素材）は全部 --work（既定 os.tmpdir() 配下）に置き、スキルのリポジトリには書かない。
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
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

function sh(bin, a, cwd = WORK) {
  const t0 = Date.now();
  const r = spawnSync(bin, a, { cwd, encoding: 'utf8', maxBuffer: 1 << 28 });
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

// スクショ相当の PNG と、短い実写クリップ相当の mp4 を ffmpeg で作る
function makeMedia(dir) {
  fs.mkdirSync(path.join(dir, 'assets'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'clips'), { recursive: true });
  const boxes = [
    [0, 0, 1280, 64, '1F4E79'], [0, 64, 220, 736, 'E3E7EA'], [24, 100, 172, 28, 'C9D1D6'], [24, 150, 150, 28, 'C9D1D6'],
    [260, 100, 300, 150, 'FFFFFF'], [590, 100, 300, 150, 'FFFFFF'], [920, 100, 300, 150, 'FFFFFF'],
    [284, 200, 120, 26, 'E08A2E'], [614, 200, 180, 26, 'C8553D'], [944, 200, 90, 26, 'F2C14E'],
    [260, 280, 960, 470, 'FFFFFF'], [300, 600, 70, 110, '1F4E79'], [400, 520, 70, 190, '1F4E79'], [500, 450, 70, 260, '1F4E79'], [600, 560, 70, 150, '1F4E79'],
  ].map(([x, y, w, h, c]) => `drawbox=x=${x}:y=${y}:w=${w}:h=${h}:color=0x${c}:t=fill`).join(',');
  const a = sh('ffmpeg', ['-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=0xF6F7F9:s=1280x800', '-vf', boxes, '-frames:v', '1', path.join(dir, 'assets', 'screenshot.png')]);
  const b = sh('ffmpeg', ['-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30:duration=3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path.join(dir, 'clips', 'demo.mp4')]);
  if (a.code || b.code) throw new Error(`素材の生成に失敗: ${a.err}${b.err}`);
}

// PNG の中で brand 色（±24）が占める割合
function colorShare(png, hex) {
  const r = spawnSync('ffmpeg', ['-v', 'error', '-i', png, '-vf', 'scale=192:-2', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 26 });
  const buf = r.stdout;
  const [R, G, B] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  let hit = 0;
  for (let i = 0; i < buf.length; i += 3) if (Math.abs(buf[i] - R) <= 24 && Math.abs(buf[i + 1] - G) <= 24 && Math.abs(buf[i + 2] - B) <= 24) hit++;
  return hit / (buf.length / 3);
}

// mp4 の a〜b 秒だけの積分ラウドネス（無音なら null）
function windowLufs(file, [a, b]) {
  const r = sh('ffmpeg', ['-hide_banner', '-nostats', '-ss', String(a), '-t', String(b - a), '-i', file, '-af', 'ebur128', '-f', 'null', '-']);
  const m = /I:\s*(-?[\d.]+|-inf)\s*LUFS/.exec(r.err.slice(r.err.lastIndexOf('Summary:')));
  return m && m[1] !== '-inf' ? parseFloat(m[1]) : null;
}

// ── ケースの実行 ───────────────────────────────────────────────
async function runRenderCase(c) {
  const R = [];
  const add = (text, passed, evidence) => R.push({ text, passed: !!passed, evidence: String(evidence) });
  const e = c.expect;
  const dir = copyFixture(c.fixture, c.name);
  if (c.media) makeMedia(dir);
  const brandArgs = c.brand === 'references' ? ['--brand', path.join(SKILL, 'references', 'brand.example.json')] : [];
  const P = path.relative(WORK, dir);

  // 1. 絵コンテ
  const sb = render('storyboard', P, '--aspect', e.storyboardAspect || 'all', ...brandArgs);
  const sbj = json(fs.existsSync(path.join(dir, 'out/storyboard/storyboard.json')) ? fs.readFileSync(path.join(dir, 'out/storyboard/storyboard.json'), 'utf8') : 'null');
  add('storyboard コマンドが成功し storyboard.md / storyboard.json を出す', sb.code === 0 && sbj && fs.existsSync(path.join(dir, 'out/storyboard/storyboard.md')), `exit=${sb.code} ${sb.err.slice(-300)}`);
  if (!sbj) return R;
  const asps = Object.keys(sbj.per);
  const nStills = asps.reduce((s, a) => s + sbj.per[a].stills.length, 0);
  add('シーンごとの代表コマ（静止画）が画角 × シーン数ぶんある', nStills === asps.length * c.expect.scenes && sbj.per[asps[0]].stills.every((x) => fs.existsSync(x.path)), `stills=${nStills} 期待=${asps.length}×${c.expect.scenes}`);
  const ev = asps.every((a) => ['contact', 'strip', 'phone'].every((k) => fs.existsSync(sbj.per[a][k])) && (!e.loop || fs.existsSync(sbj.per[a].seam || '')));
  add('書き出し前の証拠（contact / strip / phone' + (e.loop ? ' / seam' : '') + '）が出る', ev, asps.map((a) => `${a}: ${['contact', 'strip', 'phone', 'seam'].filter((k) => sbj.per[a][k]).join(',')}`).join(' '));
  add(`決定論チェック（同じコマを2回描いてハッシュ一致${e.loop ? '・ループ継ぎ目の連続性' : ''}）が OK`, sbj.check.ok, JSON.stringify(sbj.check));
  if (e.audio) {
    const a = sbj.sound;
    const ok = a && [a.preview, a.spectrogram].every((p) => fs.existsSync(p) && fs.statSync(p).size > 1000);
    add('絵コンテの段階で音のプレビュー（preview.wav）とスペクトログラム（spectrogram.png）が出る', ok, a ? `${a.preview} ${a.spectrogram} lufs=${a.lufs}` : 'sound が無い');
  }
  if (e.music) add(`絵コンテの BGM が指定どおり（style ${e.music.style}・MIDI あり）`, sbj.sound?.bgm?.style === e.music.style && sbj.sound.bgm.notes > 0 && fs.existsSync(sbj.sound.mid || ''), JSON.stringify(sbj.sound?.bgm && { style: sbj.sound.bgm.style, notes: sbj.sound.bgm.notes, progression: sbj.sound.bgm.progression }));
  if (e.brandColor) {
    const shares = sbj.per[asps[0]].stills.map((x) => colorShare(x.path, e.brandColor));
    add(`brand.json の主色 ${e.brandColor} が代表コマの ${e.brandMinShare * 100}% 以上を占めるコマがある`, Math.max(...shares) >= e.brandMinShare, `割合=${shares.map((s) => s.toFixed(3)).join(',')}`);
  }

  // 2. 承認ゲート（承認前の final は止まる）
  if (e.gate) {
    const g = render('final', P, ...brandArgs);
    add('承認前の final は exit 3 で止まり mp4 を作らない', g.code === 3 && !fs.existsSync(path.join(dir, 'out/deliver')), `exit=${g.code} ${g.err.trim().slice(0, 120)}`);
  }
  const ap = render('approve', P, '--by', 'eval', '--note', 'eval の自動承認', ...brandArgs);
  add('storyboard の後の approve が成功する', ap.code === 0, `exit=${ap.code} ${ap.err.slice(-200)}`);

  // 3. 本番書き出し（2回）
  const f1 = render('final', P, ...brandArgs);
  const r1 = json(f1.out);
  add('final が成功する', f1.code === 0 && r1, `exit=${f1.code} ${f1.sec.toFixed(1)}s ${f1.err.slice(-300)}`);
  if (!r1) return R;
  for (const [asp, [w, h]] of Object.entries(e.aspects)) {
    const pr = r1.results[asp]?.probe;
    if (!pr) { add(`${asp} の mp4 がある`, false, 'results に無い'); continue; }
    const frames = Math.round(e.duration * e.fps);
    add(`${asp}: 解像度 ${w}x${h}`, pr.width === w && pr.height === h, `${pr.width}x${pr.height}`);
    add(`${asp}: fps ${e.fps}・コマ数 ${frames}（尺 ${e.duration}s）`, pr.fps === e.fps && pr.nb_frames === frames && Math.abs(pr.format_duration - e.duration) <= 0.1, `fps=${pr.fps} nb_frames=${pr.nb_frames} format_duration=${pr.format_duration}`);
    add(`${asp}: H.264 / yuv420p${e.audio ? ' / 音声 aac' : ''}`, pr.codec === 'h264' && pr.pix_fmt === 'yuv420p' && (!e.audio || pr.audio === 'aac'), `${pr.codec} ${pr.pix_fmt} audio=${pr.audio}`);
    const od = path.dirname(r1.results[asp].mp4);
    add(`${asp}: poster.png と contact.png が納品物にある`, ['poster.png', 'contact.png'].every((f) => fs.existsSync(path.join(od, f))), od);
  }
  const deliver = r1.deliver;
  add('納品物に README.md・manifest.json・source/video.js がある', ['README.md', 'manifest.json', 'source/video.js'].every((f) => fs.existsSync(path.join(deliver, f))), deliver);
  if (e.audio) {
    for (const asp of Object.keys(e.aspects)) {
      const ld = r1.results[asp]?.loudness;
      add(`${asp}: mp4 の音量が -14 LUFS ±1・トゥルーピーク -1 dBFS 以下（ebur128 で mp4 を実測）`, ld && Math.abs(ld.lufs + 14) <= 1 && ld.truePeakDb <= -1, JSON.stringify(ld));
    }
  }
  if (e.music) {
    const mp4 = r1.results[Object.keys(e.aspects)[0]].mp4;
    const l = windowLufs(mp4, e.music.window);
    add(`効果音の無い ${e.music.window.join('〜')}s にも BGM が鳴っている（-35 LUFS より大きい）`, l != null && l > -35, `lufs=${l}`);
    add('納品物の manifest に BGM の記録（スタイル・音源・MIDI のハッシュ）がある', r1.audio?.bgm?.style === e.music.style && r1.audio.bgm.soundfontSha256 && r1.audio.bgm.midiSha256, JSON.stringify(r1.audio?.bgm && { style: r1.audio.bgm.style, soundfont: r1.audio.bgm.soundfont, midi: r1.audio.bgm.midiSha256?.slice(0, 16) }));
  }
  if (e.silentWindow) {
    const l = windowLufs(r1.results[Object.keys(e.aspects)[0]].mp4, e.silentWindow);
    add(`効果音だけの動画は cue の無い ${e.silentWindow.join('〜')}s が無音（BGM を足していない）`, l == null || l < -60, `lufs=${l}`);
  }
  if (e.media) {
    const u = r1.used;
    add('画像素材（スクショ）を実際に描いた', (u.images.shot || 0) > 0, JSON.stringify(u.images));
    add('実写クリップのコマを2種類以上貼った（クリップが動いている）', (u.clipFramesDistinct.demo || 0) >= 2, JSON.stringify(u.clipFramesDistinct));
  }
  const sha1 = Object.fromEntries(Object.entries(r1.results).map(([a, r]) => [a, r.probe.sha256]));
  const f2 = render('final', P, ...brandArgs);
  const r2 = json(f2.out);
  for (const asp of e.determinism) {
    const s2 = r2?.results?.[asp]?.probe?.sha256;
    add(`${asp}: 同じ入力で2回書き出した mp4 の sha256 が一致`, s2 && s2 === sha1[asp], `${sha1[asp]?.slice(0, 16)} / ${s2?.slice(0, 16)}`);
  }

  // 4. 承認後にソースを変えると止まる
  if (e.gate) {
    fs.appendFileSync(path.join(dir, 'video.js'), '\n// 承認後の変更\n');
    const g2 = render('final', P, ...brandArgs);
    add('承認後に video.js を変えると final は exit 3 で止まる', g2.code === 3, `exit=${g2.code} ${g2.err.trim().slice(0, 120)}`);
    const g3 = render('approve', P, '--by', 'eval', ...brandArgs);
    add('絵コンテを作り直さずに approve し直そうとしても止まる', g3.code === 3, `exit=${g3.code} ${g3.err.trim().slice(0, 120)}`);
  }
  return R;
}

async function runContracts() {
  const R = [];
  const add = (text, passed, evidence) => R.push({ text, passed: !!passed, evidence: String(evidence) });
  // 前フレームの状態の持ち越しを検出できる（検査が落ちうることの確認）
  const st = copyFixture('bad-stateful');
  const c1 = render('check', path.relative(WORK, st));
  add('前フレームの状態を持ち越す render は check が exit 1・ok:false', c1.code === 1 && json(c1.out)?.ok === false, `exit=${c1.code} ${c1.out.replace(/\s+/g, ' ').slice(0, 160)}`);
  // Math.random は描画中に例外で止まる
  const rd = copyFixture('bad-random');
  const c2 = render('storyboard', path.relative(WORK, rd));
  add('Math.random を使う render は storyboard が失敗し理由を出す', c2.code !== 0 && c2.err.includes('Math.random'), `exit=${c2.code} ${c2.err.split('\n').find((l) => l.includes('Math.random'))?.slice(0, 120)}`);
  // ループの継ぎ目が切れていれば検出できる
  const lp = copyFixture('multi-aspect', 'broken-loop');
  const src = path.join(lp, 'video.js');
  fs.writeFileSync(src, fs.readFileSync(src, 'utf8').replace('(2 * Math.PI * t) / PERIOD', '(2 * Math.PI * t) / (PERIOD * 1.25)'));
  const c3 = render('check', path.relative(WORK, lp), '--brand', path.join(SKILL, 'references', 'brand.example.json'));
  const j3 = json(c3.out);
  add('周期がずれたループ作品は check が継ぎ目で失敗する', c3.code === 1 && j3?.loop?.ok === false, `exit=${c3.code} loop=${JSON.stringify(j3?.loop)}`);
  // ばね・ビートグリッドの数式
  const M = await import(pathToFileURL(path.join(SKILL, 'scripts', 'runtime', 'motion.js')).href);
  const peak = (p) => { let m = 0; for (let t = 0; t < 4; t += 1 / 240) m = Math.max(m, M.spring(t, p)); return m; };
  add('spring は t<=0 で 0、十分後に 1 へ収束する（4プリセット）', Object.keys(M.PRESETS).every((p) => M.spring(0, p) === 0 && Math.abs(1 - M.spring(6, p)) < 1e-3), Object.keys(M.PRESETS).map((p) => `${p}:${M.spring(6, p).toFixed(5)}`).join(' '));
  add('default は行き過ぎない・snappy と playful は小さく行き過ぎる（< 10%）', peak('default') <= 1 + 1e-6 && peak('snappy') > 1 && peak('snappy') < 1.1 && peak('playful') > 1 && peak('playful') < 1.1, `default=${peak('default').toFixed(4)} snappy=${peak('snappy').toFixed(4)} playful=${peak('playful').toFixed(4)}`);
  const keys = [{ t: 0, v: 0 }, { t: 0.5, v: 100 }, { t: 0.8, v: 40 }];
  const dv = (t) => (M.springTrack(t + 1e-4, keys) - M.springTrack(t - 1e-4, keys)) / 2e-4;
  add('springTrack はターゲットが変わる瞬間も値と速度が連続', Math.abs(M.springTrack(0.8 + 1e-9, keys) - M.springTrack(0.8 - 1e-9, keys)) < 1e-4 && Math.abs(dv(0.8 + 2e-4) - dv(0.8 - 2e-4)) < 5, `v(0.8)=${M.springTrack(0.8, keys).toFixed(3)} 速度 ${dv(0.8 - 2e-4).toFixed(1)}→${dv(0.8 + 2e-4).toFixed(1)}`);
  // 作曲: 同じ入力なら同じ MIDI、スタイル・seed を変えると変わる
  const Mu = await import(pathToFileURL(path.join(SKILL, 'scripts', 'music.mjs')).href);
  const inp = { duration: 8, audio: { bpm: 120, peaks: [4] }, scenes: [{ start: 0, end: 4 }, { start: 4, end: 8 }] };
  const smf = (music) => Mu.toSmf(Mu.compose({ ...inp, music }));
  const base = { progression: ['Am', 'F', 'C', 'G'], style: 'calm', seed: 3 };
  const a1 = smf(base);
  add('作曲は同じ入力で同じ MIDI・style や seed を変えると別の MIDI（MThd で始まる SMF）', a1.equals(smf(base)) && !a1.equals(smf({ ...base, style: 'upbeat' })) && !a1.equals(smf({ ...base, seed: 4 })) && a1.subarray(0, 4).toString() === 'MThd', `bytes=${a1.length} upbeat=${smf({ ...base, style: 'upbeat' }).length}`);
  let bad = null;
  try { Mu.parseChord('Hm'); } catch (err) { bad = err.message; }
  const cm7 = Mu.parseChord('Cmaj7');
  add('コード名の解釈（Cmaj7 = C E G B・読めない名前は理由付きで止まる）', cm7.root === 0 && cm7.intervals.join() === '0,4,7,11' && Mu.parseChord('C/E').bass === 4 && !!bad, `Cmaj7=${cm7.intervals} C/E bass=${Mu.parseChord('C/E').bass} Hm→${bad}`);
  const bg = M.beatGrid(120, 0, 4);
  add('beatGrid(120): 4拍目=2.0s・2小節目頭=4.0s', bg.beat(4) === 2 && bg.bar(2) === 4, `beat(4)=${bg.beat(4)} bar(2)=${bg.bar(2)}`);
  return R;
}

// ── main ───────────────────────────────────────────────────────
const only = opt('--only');
if (only && !spec.evals.some((c) => c.name === only)) {
  console.error(`--only に一致するケースが無い: ${only}\nケース: ${spec.evals.map((c) => c.name).join(', ')}`);
  process.exit(2);
}
const all = [];
console.log(`work: ${WORK}`);
for (const c of spec.evals) {
  if (only && c.name !== only) continue;
  const t0 = Date.now();
  let res;
  try {
    res = c.kind === 'contracts' ? await runContracts() : await runRenderCase(c);
  } catch (err) {
    res = [{ text: 'ケースが例外なく完走する', passed: false, evidence: err.stack }];
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
