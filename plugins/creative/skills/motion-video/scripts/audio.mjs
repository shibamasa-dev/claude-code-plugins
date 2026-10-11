#!/usr/bin/env node
// audio.mjs — beat grid, code-synthesized sound effects (SFX), mixing with BGM, and mastering (-14 LUFS / true peak at or below -1 dBFS).
//   node audio.mjs --duration 6 --bpm 120 --cues cues.json [--music music.json --scenes scenes.json --peaks 0,4] --out mix.wav [--spectrogram spec.png]
//   node audio.mjs --list                                                   # list the sound effects
// cues.json: [{ "beat": 0, "sfx": "thump" }, { "t": 2.5, "sfx": "whoosh", "gain": 0.7, "pan": -0.3 }]
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { beatGrid, rng } from './runtime/motion.js';
import { renderBgm, synthIR } from './music.mjs';

export const SR = 48000;
const TAU = Math.PI * 2;

// ── Sound effects (all deterministic with fixed seeds) ──────────────
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

// Convert a cue's time (t seconds / beat index / bar index) to seconds
export function cueTime(c, grid) {
  if (c.t != null) return c.t;
  if (c.bar != null) return grid.bar(c.bar, c.beat ?? 0);
  if (c.beat != null) return grid.beat(c.beat);
  throw new Error(`cue has none of t / beat / bar: ${JSON.stringify(c)}`);
}

// Contents of beats.json (beats, bar starts, peaks)
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

// Warn about cues off the beat / peaks off a bar start (if intentional, set offbeat: true on the cue)
export function audioWarnings(audio = {}, duration, fps) {
  const w = [];
  const grid = beatGrid(audio.bpm ?? 120, audio.offset ?? 0, audio.beatsPerBar ?? 4);
  const tol = 0.5 / fps + 1e-6;
  for (const c of audio.cues || []) {
    const t = cueTime(c, grid);
    if (!SFX[c.sfx]) w.push(`unknown sound effect ${c.sfx} (${Object.keys(SFX).join(' / ')})`);
    if (t < 0 || t >= duration) w.push(`cue ${c.sfx}@${t.toFixed(3)}s is outside the duration`);
    if (!c.offbeat && Math.abs(grid.nearest(t) - t) > tol) w.push(`cue ${c.sfx}@${t.toFixed(3)}s is not on a beat (if intentional, set offbeat: true)`);
  }
  const spbar = grid.spb * (audio.beatsPerBar ?? 4);
  for (const p of audio.peaks || []) {
    const k = Math.round((p - (audio.offset ?? 0)) / spbar);
    if (Math.abs((audio.offset ?? 0) + k * spbar - p) > tol) w.push(`peak ${p}s is not on a bar start (put the hero's entrance on a bar start)`);
  }
  return w;
}

// Lay out the cues and mix them to stereo
export function mix({ duration, audio = {} }) {
  const n = Math.round(duration * SR);
  const L = new Float32Array(n);
  const R = new Float32Array(n);
  const grid = beatGrid(audio.bpm ?? 120, audio.offset ?? 0, audio.beatsPerBar ?? 4);
  (audio.cues || []).forEach((c, idx) => {
    const fn = SFX[c.sfx];
    if (!fn) throw new Error(`unknown sound effect: ${c.sfx}`);
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


// 32-bit float WAV (for intermediate files; no rounding to 16-bit, so no precision loss and no clipping). chans is an array of equal-length Float32Arrays
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

// Read a 32-bit float stereo WAV (pcm_f32le written by ffmpeg; looks for the data chunk)
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

// Pin ffmpeg to one thread (so filter parallelism cannot change the order of floating-point additions)
function ff(args) {
  const r = spawnSync('ffmpeg', ['-hide_banner', '-nostdin', '-y', '-v', 'error', '-threads', '1', '-filter_complex_threads', '1', ...args], { encoding: 'utf8', maxBuffer: 1 << 26 });
  if (r.status !== 0) throw new Error(`ffmpeg failed: ${r.stderr}`);
  return r;
}

// Measure integrated loudness, loudness range, sample peak and true peak with ffmpeg's ebur128 (works on wav or mp4)
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

// BGM effects: cut below 50Hz at 24dB/oct (low-end mud) -> trim 250Hz slightly -> make room in the SFX band (3kHz) -> light compression
// -> blend in convolution reverb (afir) -> widen the stereo image -> short fade at the end
function bgmChain(D, reverb) {
  return [
    `[0:a]aresample=${SR},atrim=0:${D},apad=whole_dur=${D},highpass=f=50,highpass=f=50,equalizer=f=250:t=q:w=1:g=-3,equalizer=f=3000:t=q:w=1.2:g=-2,`,
    'acompressor=threshold=0.1:ratio=2.5:attack=20:release=250,asplit=2[bd][bw];',
    '[bw][1:a]afir=dry=1:wet=1[bwet];',
    `[bd][bwet]amix=inputs=2:weights=1 ${reverb}:normalize=0,stereowiden=delay=18:feedback=0.2:crossfeed=0.3:drymix=0.85,`,
    `afade=t=out:st=${Math.max(0, D - 0.5)}:d=0.5,atrim=0:${D}[o]`,
  ].join('');
}

const BGM_LUFS = -20; // BGM loudness before mixing with SFX (adjust with music.gainDb)
const SFX_PEAK = 0.7; // peak of the combined SFX (before mixing)

// Mix the SFX (and BGM) and master to -14 LUFS ±1 with true peak at or below -1 dBFS.
// Steps: effects on the BGM -> normalize BGM loudness -> duck the BGM only while SFX play (sidechain) and mix
// -> set the overall gain and tame peaks with a 4x-oversampled limiter -> measure, and refine the gain if it falls short.
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
      if (!fs.existsSync(irPath)) throw new Error(`impulse response not found: ${irPath}`);
    } else {
      irPath = path.join(work, 'ir.wav');
      const ir = synthIR({ seconds: music.reverbSeconds ?? 1.6 });
      fs.writeFileSync(irPath, wavF32([ir.L, ir.R]));
    }
    const reverb = music.reverb ?? 0.3;
    const fx = path.join(work, 'bgm-fx.wav');
    ff(['-i', b.wav, '-i', irPath, '-filter_complex', bgmChain(D, reverb), '-map', '[o]', '-c:a', 'pcm_f32le', fx]);
    const lb = measureLoudness(fx).lufs;
    if (lb == null) throw new Error('BGM came out silent (check progression / style / soundfont)');
    const bgmGain = 10 ** ((BGM_LUFS + (music.gainDb ?? 0) - lb) / 20);
    const duck = music.duck ?? 5; // sidechain compression ratio (1 = no ducking)
    // Feeding separate files to sidechaincompress and amix makes the length depend on which input runs out first at the end (it varied on every measured run).
    // So pack the 2ch SFX and 2ch BGM into one 4ch WAV and split them from that single input.
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
  // Encoding to AAC raises peaks by about 0.5 dB. Encode with the same settings as the delivery and measure;
  // if the true peak exceeds maxTruePeakDb, lower the limiter ceiling and retry.
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

// Audio encoding settings identical to the delivered mp4 (render.mjs's final uses these too)
export const AAC = ['-c:a', 'aac', '-b:a', '192k', '-flags:a', '+bitexact'];

// RMS per band (dBFS). The bottom of the log-scale spectrogram smears, so judge low-end muddiness by these numbers
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

// Overlay vertical lines for scene boundaries (white) and peaks (green) on a spectrogram (log frequency axis).
// With legend enabled, showspectrumpic offsets the plot area by 142px left and 64px top, so add that when drawing the lines.
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
