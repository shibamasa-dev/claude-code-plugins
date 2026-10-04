#!/usr/bin/env node
// audio.mjs — ビートグリッド・コード合成の効果音・BGM との混ぜ合わせとマスタリング（-14 LUFS / トゥルーピーク -1 dBFS 以下）。
//   node audio.mjs --duration 6 --bpm 120 --cues cues.json [--music music.json --scenes scenes.json --peaks 0,4] --out mix.wav [--spectrogram spec.png]
//   node audio.mjs --list                                                   # 効果音の一覧
// cues.json: [{ "beat": 0, "sfx": "thump" }, { "t": 2.5, "sfx": "whoosh", "gain": 0.7, "pan": -0.3 }]
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { beatGrid, rng } from './runtime/motion.js';
import { renderBgm, synthIR } from './music.mjs';

export const SR = 48000;
const TAU = Math.PI * 2;

// ── 効果音（全部シード固定の決定論） ─────────────────────────────
function click(r) {
  const n = Math.round(SR * 0.04);
  const o = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    o[i] = (r() * 2 - 1) * Math.exp(-t / 0.0025) * 0.5 + Math.sin(TAU * 2800 * t) * Math.exp(-t / 0.008) * 0.5;
  }
  return o;
}
function pop(r) {
  const n = Math.round(SR * 0.16);
  const o = new Float32Array(n);
  let ph = 0;
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    ph += (TAU * (260 + 700 * Math.exp(-t / 0.018))) / SR;
    o[i] = Math.sin(ph) * Math.exp(-t / 0.045) * 0.8;
  }
  return o;
}
function thump(r) {
  const n = Math.round(SR * 0.45);
  const o = new Float32Array(n);
  let ph = 0;
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    ph += (TAU * (42 + 95 * Math.exp(-t / 0.035))) / SR;
    o[i] = Math.sin(ph) * Math.exp(-t / 0.13) * 0.95 + (r() * 2 - 1) * Math.exp(-t / 0.003) * 0.25;
  }
  return o;
}
function whoosh(r) {
  const len = 0.55;
  const n = Math.round(SR * len);
  const o = new Float32Array(n);
  let y1 = 0;
  let y2 = 0;
  for (let i = 0; i < n; i++) {
    const p = i / n;
    const cutoff = 300 + 5200 * Math.sin(Math.PI * p) ** 2;
    const a = 1 - Math.exp((-TAU * cutoff) / SR);
    y1 += a * (r() * 2 - 1 - y1);
    y2 += a * (y1 - y2);
    o[i] = y2 * Math.sin(Math.PI * p) ** 2 * 1.6;
  }
  return o;
}
export const SFX = { click, pop, thump, whoosh };

// cue の時刻（t 秒 / beat 拍目 / bar 小節目）を秒に直す
export function cueTime(c, grid) {
  if (c.t != null) return c.t;
  if (c.bar != null) return grid.bar(c.bar, c.beat ?? 0);
  if (c.beat != null) return grid.beat(c.beat);
  throw new Error(`cue に t / beat / bar のどれも無い: ${JSON.stringify(c)}`);
}

// beats.json の中身（拍・小節頭・ピーク）
export function beatsInfo(audio = {}, duration) {
  const bpm = audio.bpm ?? 120;
  const offset = audio.offset ?? 0;
  const bpb = audio.beatsPerBar ?? 4;
  const grid = beatGrid(bpm, offset, bpb);
  const beats = [];
  const bars = [];
  for (let n = 0; ; n++) {
    const t = grid.beat(n);
    if (t >= duration - 1e-9) break;
    beats.push(round(t));
    if (n % bpb === 0) bars.push(round(t));
  }
  return { bpm, offset, beatsPerBar: bpb, secondsPerBeat: round(grid.spb), beats, bars, peaks: (audio.peaks || []).map(round) };
}
const round = (x) => Math.round(x * 1e6) / 1e6;

// 拍から外れた cue / 小節頭から外れたピークを警告（意図的なら cue に offbeat: true）
export function audioWarnings(audio = {}, duration, fps) {
  const w = [];
  const grid = beatGrid(audio.bpm ?? 120, audio.offset ?? 0, audio.beatsPerBar ?? 4);
  const tol = 0.5 / fps + 1e-6;
  for (const c of audio.cues || []) {
    const t = cueTime(c, grid);
    if (!SFX[c.sfx]) w.push(`未知の効果音 ${c.sfx}（${Object.keys(SFX).join(' / ')}）`);
    if (t < 0 || t >= duration) w.push(`cue ${c.sfx}@${t.toFixed(3)}s が尺の外`);
    if (!c.offbeat && Math.abs(grid.nearest(t) - t) > tol) w.push(`cue ${c.sfx}@${t.toFixed(3)}s が拍に乗っていない（意図的なら offbeat: true）`);
  }
  const spbar = grid.spb * (audio.beatsPerBar ?? 4);
  for (const p of audio.peaks || []) {
    const k = Math.round((p - (audio.offset ?? 0)) / spbar);
    if (Math.abs((audio.offset ?? 0) + k * spbar - p) > tol) w.push(`ピーク ${p}s が小節頭に乗っていない（主役の登場は小節頭へ）`);
  }
  return w;
}

// cue を並べてステレオに混ぜる
export function mix({ duration, audio = {} }) {
  const n = Math.round(duration * SR);
  const L = new Float32Array(n);
  const R = new Float32Array(n);
  const grid = beatGrid(audio.bpm ?? 120, audio.offset ?? 0, audio.beatsPerBar ?? 4);
  (audio.cues || []).forEach((c, idx) => {
    const fn = SFX[c.sfx];
    if (!fn) throw new Error(`未知の効果音: ${c.sfx}`);
    const s = fn(rng(1000 + idx));
    const start = Math.round(cueTime(c, grid) * SR);
    const gain = c.gain ?? 1;
    const pan = Math.max(-1, Math.min(1, c.pan ?? 0));
    const gl = gain * Math.cos(((pan + 1) * Math.PI) / 4);
    const gr = gain * Math.sin(((pan + 1) * Math.PI) / 4);
    for (let i = 0; i < s.length && start + i < n; i++) {
      if (start + i < 0) continue;
      L[start + i] += s[i] * gl;
      R[start + i] += s[i] * gr;
    }
  });
  return { L, R };
}


// 32bit float の WAV（中間ファイル用。16bit に丸めないので桁落ちもクリップもしない）。chans は同じ長さの Float32Array の配列
export function wavF32(chans, gain = 1) {
  const c = chans.length;
  const n = chans[0].length;
  const buf = Buffer.alloc(44 + n * 4 * c);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + n * 4 * c, 4); buf.write('WAVE', 8);
  buf.write('fmt ', 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(3, 20); buf.writeUInt16LE(c, 22);
  buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 4 * c, 28); buf.writeUInt16LE(4 * c, 32); buf.writeUInt16LE(32, 34);
  buf.write('data', 36); buf.writeUInt32LE(n * 4 * c, 40);
  for (let i = 0; i < n; i++) for (let k = 0; k < c; k++) buf.writeFloatLE(chans[k][i] * gain, 44 + (i * c + k) * 4);
  return buf;
}

// 32bit float のステレオ WAV を読む（ffmpeg が書いた pcm_f32le。data チャンクを探す）
function readWavF32(p) {
  const b = fs.readFileSync(p);
  let o = 12;
  while (b.toString('ascii', o, o + 4) !== 'data') o += 8 + b.readUInt32LE(o + 4);
  const n = b.readUInt32LE(o + 4) / 8;
  const L = new Float32Array(n);
  const R = new Float32Array(n);
  for (let i = 0; i < n; i++) { L[i] = b.readFloatLE(o + 8 + i * 8); R[i] = b.readFloatLE(o + 12 + i * 8); }
  return { L, R };
}

// ffmpeg は1スレッドに固定する（フィルタの並列化で浮動小数の足し順が変わらないように）
function ff(args) {
  const r = spawnSync('ffmpeg', ['-hide_banner', '-nostdin', '-y', '-v', 'error', '-threads', '1', '-filter_complex_threads', '1', ...args], { encoding: 'utf8', maxBuffer: 1 << 26 });
  if (r.status !== 0) throw new Error(`ffmpeg が失敗: ${r.stderr}`);
  return r;
}

// ffmpeg の ebur128 で積分ラウドネス・ラウドネスレンジ・サンプルピーク・トゥルーピークを測る（wav でも mp4 でも）
export function measureLoudness(file) {
  const r = spawnSync('ffmpeg', ['-hide_banner', '-nostats', '-i', file, '-map', '0:a:0', '-af', 'ebur128=peak=sample+true', '-f', 'null', '-'], { encoding: 'utf8', maxBuffer: 1 << 26 });
  const txt = (r.stderr || '').slice((r.stderr || '').lastIndexOf('Summary:'));
  const num = (re) => { const m = re.exec(txt); return m && !/inf/.test(m[1]) ? parseFloat(m[1]) : null; };
  return {
    lufs: num(/I:\s*(-?[\d.]+|-inf)\s*LUFS/),
    lra: num(/LRA:\s*(-?[\d.]+)\s*LU/),
    samplePeakDb: num(/Sample peak:\s*\n\s*Peak:\s*(-?[\d.]+|-inf)/),
    truePeakDb: num(/True peak:\s*\n\s*Peak:\s*(-?[\d.]+|-inf)/),
    summary: txt.trim(),
  };
}

// BGM のエフェクト: 50Hz 以下を 24dB/oct で切る（低域の濁り） → 250Hz を少し削る → 効果音の帯域（3kHz）を空ける → 軽くコンプ
// → 畳み込みリバーブ（afir）を混ぜる → ステレオを広げる → 終わりを短くフェード
function bgmChain(D, reverb) {
  return [
    `[0:a]aresample=${SR},atrim=0:${D},apad=whole_dur=${D},highpass=f=50,highpass=f=50,equalizer=f=250:t=q:w=1:g=-3,equalizer=f=3000:t=q:w=1.2:g=-2,`,
    'acompressor=threshold=0.1:ratio=2.5:attack=20:release=250,asplit=2[bd][bw];',
    '[bw][1:a]afir=dry=1:wet=1[bwet];',
    `[bd][bwet]amix=inputs=2:weights=1 ${reverb}:normalize=0,stereowiden=delay=18:feedback=0.2:crossfeed=0.3:drymix=0.85,`,
    `afade=t=out:st=${Math.max(0, D - 0.5)}:d=0.5,atrim=0:${D}[o]`,
  ].join('');
}

const BGM_LUFS = -20; // 効果音と混ぜる前の BGM の大きさ（music.gainDb で上下）
const SFX_PEAK = 0.7; // 効果音の束のピーク（混ぜる前）

// 効果音（と BGM）を混ぜ、-14 LUFS ±1・トゥルーピーク -1 dBFS 以下に仕上げる。
// 手順: BGM にエフェクト → BGM の大きさを揃える → 効果音が鳴る瞬間だけ BGM を下げて（サイドチェーン）混ぜる
// → 全体のゲインを決め、4倍オーバーサンプリングしたリミッターでピークを抑える → 実測して足りなければゲインを詰める。
export function renderAudio({ duration, audio = {}, scenes = [], outPath, work, base, target = -14, ceilingDb = -2, maxTruePeakDb = -1 }) {
  const D = +duration.toFixed(6);
  work = work || path.join(path.dirname(outPath), '.audio-work');
  fs.mkdirSync(work, { recursive: true });
  const music = audio.music || null;
  const m = mix({ duration, audio });
  let peak = 0;
  for (let i = 0; i < m.L.length; i++) peak = Math.max(peak, Math.abs(m.L[i]), Math.abs(m.R[i]));
  if (peak === 0 && !music) {
    fs.writeFileSync(outPath, wav16(m));
    return { lufs: null, lra: null, truePeakDb: null, samplePeakDb: null, gainDb: 0, bgm: null };
  }
  const sfxWav = path.join(work, 'sfx.wav');
  fs.writeFileSync(sfxWav, wavF32([m.L, m.R], peak ? SFX_PEAK / peak : 1));

  let bgm = null;
  let pre = sfxWav;
  if (music) {
    const b = renderBgm({ duration, audio, scenes, music, work, base });
    let irPath;
    if (music.ir) {
      irPath = path.resolve(base || process.cwd(), music.ir);
      if (!fs.existsSync(irPath)) throw new Error(`インパルス応答が無い: ${irPath}`);
    } else {
      irPath = path.join(work, 'ir.wav');
      const ir = synthIR({ seconds: music.reverbSeconds ?? 1.6 });
      fs.writeFileSync(irPath, wavF32([ir.L, ir.R]));
    }
    const reverb = music.reverb ?? 0.3;
    const fx = path.join(work, 'bgm-fx.wav');
    ff(['-i', b.wav, '-i', irPath, '-filter_complex', bgmChain(D, reverb), '-map', '[o]', '-c:a', 'pcm_f32le', fx]);
    const lb = measureLoudness(fx).lufs;
    if (lb == null) throw new Error('BGM が無音になった（progression / style / サウンドフォントを確かめる）');
    const bgmGain = 10 ** ((BGM_LUFS + (music.gainDb ?? 0) - lb) / 20);
    const duck = music.duck ?? 5; // サイドチェーンの圧縮比（1 で下げない）
    // sidechaincompress と amix に別々のファイルを入れると、終端でどちらの入力が先に尽きるかで長さが変わる（実測で毎回違った）。
    // 効果音 2ch と BGM 2ch を1本の 4ch WAV にまとめ、1つの入力から分けて使う。
    const fxs = readWavF32(fx);
    const n = m.L.length;
    const fit = (a) => { const o = new Float32Array(n); o.set(a.subarray(0, n)); return o; };
    const g = peak ? SFX_PEAK / peak : 1;
    const quad = path.join(work, 'stems4.wav');
    fs.writeFileSync(quad, wavF32([m.L.map((x) => x * g), m.R.map((x) => x * g), fit(fxs.L), fit(fxs.R)]));
    pre = path.join(work, 'premix.wav');
    const bv = `volume=${bgmGain.toFixed(6)}`;
    const graph = peak
      ? `[0:a]asplit=2[x][y];[x]pan=stereo|c0=c0|c1=c1,asplit=2[s][sc];[y]pan=stereo|c0=c2|c1=c3,${bv}[b];[b][sc]sidechaincompress=threshold=0.05:ratio=${duck}:attack=5:release=220[d];[d][s]amix=inputs=2:normalize=0[o]`
      : `[0:a]pan=stereo|c0=c2|c1=c3,${bv}[o]`;
    ff(['-i', quad, '-filter_complex', graph, '-map', '[o]', '-c:a', 'pcm_f32le', pre]);
    bgm = { ...b.info, reverb, ir: music.ir ? irPath : 'synth', gainDb: +(20 * Math.log10(bgmGain)).toFixed(2), duck, stem: fx, mid: b.mid };
  }

  const lPre = measureLoudness(pre).lufs;
  let gain = 10 ** ((target - lPre) / 20);
  let res;
  let aac = null;
  const passes = [];
  // AAC に符号化するとピークが 0.5 dB ほど持ち上がる。納品と同じ設定で符号化して測り、
  // トゥルーピークが maxTruePeakDb を超えたらリミッターの天井を下げてやり直す。
  for (let tries = 0; tries < 4; tries++) {
    const limit = 10 ** (ceilingDb / 20);
    for (let k = 0; k < 6; k++) {
      ff(['-i', pre, '-af', `volume=${gain.toFixed(6)},aresample=${SR * 4},alimiter=limit=${limit.toFixed(6)}:attack=2:release=80:level=false:latency=1,aresample=${SR},atrim=0:${D}`, '-c:a', 'pcm_s16le', '-ar', String(SR), outPath]);
      res = measureLoudness(outPath);
      passes.push({ ceilingDb: +ceilingDb.toFixed(2), gainDb: +(20 * Math.log10(gain)).toFixed(2), lufs: res.lufs });
      if (res.lufs == null || Math.abs(res.lufs - target) < 0.2) break;
      gain *= 10 ** ((target - res.lufs) / 20);
    }
    const m4a = path.join(work, 'aac-check.m4a');
    ff(['-i', outPath, ...AAC, m4a]);
    aac = measureLoudness(m4a);
    if (aac.truePeakDb == null || aac.truePeakDb <= maxTruePeakDb - 0.2) break;
    ceilingDb -= aac.truePeakDb - (maxTruePeakDb - 0.3);
  }
  return {
    lufs: res.lufs, lra: res.lra, truePeakDb: res.truePeakDb, samplePeakDb: res.samplePeakDb, gainDb: passes.at(-1).gainDb, passes, target,
    ceilingDb: +ceilingDb.toFixed(2), aac: aac && { lufs: aac.lufs, truePeakDb: aac.truePeakDb }, bgm,
  };
}

// 納品の mp4 と同じ音声の符号化設定（render.mjs の final もこれを使う）
export const AAC = ['-c:a', 'aac', '-b:a', '192k', '-flags:a', '+bitexact'];

// 帯域ごとの RMS（dBFS）。スペクトログラムは対数軸の最下段がにじむので、低域のこもりはこの数字で判断する
export const BANDS = { sub: [0, 40], low: [40, 120], lowmid: [120, 500], mid: [500, 4000], high: [4000, 0] };
export function bandLevels(wav) {
  const out = {};
  for (const [k, [lo, hi]] of Object.entries(BANDS)) {
    const f = [lo ? `highpass=f=${lo},highpass=f=${lo}` : null, hi ? `lowpass=f=${hi},lowpass=f=${hi}` : null].filter(Boolean).join(',');
    const r = spawnSync('ffmpeg', ['-hide_banner', '-nostats', '-i', wav, '-af', `${f},astats=metadata=0`, '-f', 'null', '-'], { encoding: 'utf8', maxBuffer: 1 << 26 });
    const m = [...(r.stderr || '').matchAll(/RMS level dB:\s*(-?[\d.]+|-inf)/g)].at(-1);
    out[k] = m && m[1] !== '-inf' ? +(+m[1]).toFixed(1) : null;
  }
  return out;
}

// スペクトログラム（周波数は対数軸）に、シーンの境目（白）とピーク（緑）の縦線を重ねる。
// showspectrumpic の legend 付きは描画域が左 142px・上 64px ずれるので、その分を足して線を引く。
export function spectrogram({ wav, out, duration, scenes = [], peaks = [] }) {
  const W = 1600;
  const H = 480;
  const x = (t) => 142 + Math.round((t / duration) * W);
  const lines = [
    ...scenes.slice(1).map((s) => `drawbox=x=${x(s.start)}:y=64:w=2:h=${H}:color=white@0.8:t=fill`),
    ...peaks.map((p) => `drawbox=x=${x(p) - 1}:y=64:w=4:h=${H}:color=0x33FF66@0.9:t=fill`),
  ];
  ff(['-i', wav, '-lavfi', [`showspectrumpic=s=${W}x${H}:legend=1:fscale=log:gain=1`, ...lines].join(','), '-frames:v', '1', out]);
  return out;
}

// ── CLI ────────────────────────────────────────────────────────
if (import.meta.url === `file://${process.argv[1]}`) {
  const a = process.argv.slice(2);
  const get = (k, d) => (a.includes(k) ? a[a.indexOf(k) + 1] : d);
  if (a.includes('--list')) {
    console.log(Object.keys(SFX).join('\n'));
    process.exit(0);
  }
  const duration = parseFloat(get('--duration', '4'));
  const cues = get('--cues') ? JSON.parse(fs.readFileSync(get('--cues'), 'utf8')) : [];
  const music = get('--music') ? JSON.parse(fs.readFileSync(get('--music'), 'utf8')) : undefined;
  const scenes = get('--scenes') ? JSON.parse(fs.readFileSync(get('--scenes'), 'utf8')) : [];
  const audio = { bpm: parseFloat(get('--bpm', '120')), peaks: get('--peaks') ? get('--peaks').split(',').map(Number) : [], cues, music };
  const out = path.resolve(get('--out', 'sfx.wav'));
  const res = renderAudio({ duration, audio, scenes, outPath: out, work: path.join(os.tmpdir(), 'motion-video', 'audio-cli') });
  if (get('--spectrogram')) spectrogram({ wav: out, out: path.resolve(get('--spectrogram')), duration, scenes, peaks: audio.peaks });
  console.log(JSON.stringify({ out, ...res, warnings: audioWarnings(audio, duration, 60) }, null, 2));
}
