#!/usr/bin/env node
// music.mjs — composes BGM from the beat grid and the scene list (writes MIDI in code) and plays it through a soundfont with FluidSynth.
//   node music.mjs --duration 8 --bpm 100 --progression Am,F,C,G --style calm --out bgm.wav [--mid bgm.mid] [--peaks 0,4.8]
//   node music.mjs --styles                                                   # list the styles
// No generative AI. Humanization uses a fixed-seed RNG, so the same input gives the same MIDI and the same waveform.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { beatGrid, rng } from './runtime/motion.js';

export const SR = 48000;
const PPQ = 480;
export const DEFAULT_SF2 = path.join(os.homedir(), '.local/share/motion-video/soundfonts/GeneralUser-GS.sf2');

// ── Chord name -> chord tones ─────────────────────────────────
const PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const QUALITY = {
  '': [0, 4, 7], maj: [0, 4, 7], m: [0, 3, 7], min: [0, 3, 7], dim: [0, 3, 6], aug: [0, 4, 8],
  '7': [0, 4, 7, 10], maj7: [0, 4, 7, 11], M7: [0, 4, 7, 11], m7: [0, 3, 7, 10], m7b5: [0, 3, 6, 10],
  sus2: [0, 2, 7], sus4: [0, 5, 7], add9: [0, 4, 7, 14], madd9: [0, 3, 7, 14], '6': [0, 4, 7, 9], m6: [0, 3, 7, 9],
};
function pitchClass(s) {
  const m = /^([A-G])([#b]?)$/.exec(s);
  if (!m) return null;
  return (PC[m[1]] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0) + 12) % 12;
}
export function parseChord(name) {
  const m = /^([A-G][#b]?)([^/]*)(?:\/([A-G][#b]?))?$/.exec(String(name).trim());
  if (!m || !(m[2] in QUALITY)) throw new Error(`cannot parse chord name: ${name} (e.g. Am / F / Cmaj7 / G7 / Dm7 / Fsus2 / C/E)`);
  const root = pitchClass(m[1]);
  return { name, root, bass: m[3] ? pitchClass(m[3]) : root, intervals: QUALITY[m[2]] };
}

// Fold the chord tones into lo..lo+12 and sort them (inversions keep them in a close register)
function voicing(ch, lo) {
  return ch.intervals.map((iv) => lo + ((((ch.root + iv - lo) % 12) + 12) % 12)).sort((a, b) => a - b);
}
const bassNote = (ch, lo = 40) => lo + ((((ch.bass - lo) % 12) + 12) % 12);

// ── Styles (instruments and which layers come in and out) ─────────
// program is General MIDI (0-based). energy (0..1) brings layers in and out.
export const STYLES = {
  calm: {
    description: 'Pad + piano arpeggio + bass. No drums. For explainers and company intros',
    parts: { pad: { program: 89, ch: 0, vol: 78, pan: 64 }, keys: { program: 0, ch: 1, vol: 92, pan: 58 }, bass: { program: 32, ch: 2, vol: 88, pan: 64 } },
  },
  upbeat: {
    description: 'Drums + eighth-note bass + electric piano chord stabs + pad. For product demos and social media',
    parts: { pad: { program: 89, ch: 0, vol: 60, pan: 64 }, keys: { program: 4, ch: 1, vol: 88, pan: 70 }, bass: { program: 33, ch: 2, vol: 96, pan: 64 }, drums: { program: 0, ch: 9, vol: 96, pan: 64 } },
  },
};

// energy per bar. Uses the scene's energy (0..1) if set; otherwise
// "scene containing a peak (meta.audio.peaks) = 1.0 / first = 0.45 / last = 0.7 / others = 0.65".
function barEnergy(t, scenes, peaks) {
  if (!scenes?.length) return 0.65;
  const i = Math.max(0, scenes.findIndex((s) => t >= s.start - 1e-9 && t < s.end - 1e-9));
  const s = scenes[i];
  if (s.energy != null) return s.energy;
  if (peaks.some((p) => p >= s.start - 1e-9 && p < s.end - 1e-9)) return 1;
  if (i === 0) return 0.45;
  if (i === scenes.length - 1) return 0.7;
  return 0.65;
}

// ── Compose ─────────────────────────────────────────────────────
// The returned notes are in beats, not seconds. offset (seconds) is added when converting to MIDI.
export function compose({ duration, audio = {}, scenes = [], music }) {
  const style = STYLES[music.style || 'calm'];
  if (!style) throw new Error(`unknown style ${music.style} (${Object.keys(STYLES).join(' / ')})`);
  const prog = (music.progression || ['C', 'G', 'Am', 'F']).map(parseChord);
  const bpm = audio.bpm ?? 120;
  const bpb = audio.beatsPerBar ?? 4;
  const offset = audio.offset ?? 0;
  const grid = beatGrid(bpm, offset, bpb);
  const peaks = audio.peaks || [];
  const chordBeats = (music.chordBars ?? 1) * bpb;
  const totalBeats = (duration - offset) / grid.spb;
  const nBars = Math.ceil(totalBeats / bpb - 1e-9);
  const r = rng(music.seed ?? 1);
  const human = music.humanize ?? 1; // amount of humanization (0 = none)
  const notes = []; // { part, beat, len, key, vel }
  const cc = []; // { part, beat, num, val }
  const add = (part, beat, len, key, vel, { exact = false } = {}) => {
    if (!style.parts[part] || beat >= totalBeats) return;
    const jitter = exact || beat === 0 ? 0 : (r() * 2 - 1) * 0.02 * human; // ±2% of a beat
    const vj = Math.round((r() * 2 - 1) * 8 * human);
    notes.push({ part, beat: Math.max(0, beat + jitter), len: Math.min(len, totalBeats - beat), key, vel: Math.max(1, Math.min(127, vel + vj)) });
  };
  const chordAt = (beat) => prog[Math.floor(beat / chordBeats) % prog.length];
  const peakBars = new Set(peaks.map((p) => Math.round((p - offset) / (grid.spb * bpb))));
  const lastBar = nBars - 1;

  for (let bar = 0; bar < nBars; bar++) {
    const b0 = bar * bpb;
    const e = barEnergy(grid.beat(b0), scenes, peaks);
    const isPeak = peakBars.has(bar);
    const prePeak = peakBars.has(bar + 1);
    const final = bar === lastBar;
    for (let cb = 0; cb < bpb; cb += Math.min(bpb, chordBeats)) {
      const beat = b0 + cb;
      const ch = chordAt(beat);
      const span = Math.min(bpb - cb, chordBeats);
      const vel = Math.round(52 + 40 * e);
      // Pad: sustain the chord (in the last bar, until the end of the duration)
      for (const k of voicing(ch, 55)) add('pad', beat, final ? totalBeats - beat : span, k, vel - 10, { exact: true });
      // Bass
      if (style === STYLES.upbeat && !final) {
        for (let i = 0; i < span * 2; i++) add('bass', beat + i / 2, 0.42, bassNote(ch) + (i % 4 === 3 ? 12 : 0), vel + (i % 2 ? -8 : 4));
      } else if (e >= 0.5 || final) {
        add('bass', beat, final ? totalBeats - beat : span * 0.95, bassNote(ch), vel);
      }
      // Keys
      const tones = voicing(ch, 60);
      const arp = [...tones, tones[0] + 12, ...tones.slice(1).reverse()];
      if (final) {
        for (const k of [...tones, tones[0] + 12]) add('keys', beat, totalBeats - beat, k, vel - 4, { exact: true });
      } else if (style === STYLES.calm) {
        const step = e >= 0.6 ? 0.5 : 1; // eighth notes when energy is high, quarter notes when low
        for (let i = 0; i * step < span; i++) add('keys', beat + i * step, step * 1.6, arp[i % arp.length] + (isPeak && i % 2 ? 12 : 0), vel - 6 + (i === 0 ? 8 : 0));
      } else if (e >= 0.6) {
        for (let i = 0; i < span; i++) for (const k of tones) add('keys', beat + i + 0.5, 0.3, k, vel - 10); // offbeat stabs
      }
    }
    // Drums (upbeat only)
    if (style.parts.drums && !final) {
      const v = Math.round(60 + 40 * e);
      for (let i = 0; i < bpb * 2; i++) if (e >= 0.4) add('drums', b0 + i / 2, 0.1, 42, v - 22 + (i % 2 ? -8 : 0)); // eighth-note hi-hat
      if (e >= 0.55) {
        for (let i = 0; i < bpb; i++) {
          if (i % 2 === 0) add('drums', b0 + i, 0.2, 36, v + 6, { exact: i === 0 });
          else if (!(prePeak && i === bpb - 1)) add('drums', b0 + i, 0.2, 38, v);
        }
      }
      if (prePeak) for (let i = 0; i < 4; i++) add('drums', b0 + bpb - 1 + i / 4, 0.1, 38, v - 20 + i * 8); // fill
      if (isPeak) add('drums', b0, 1.5, 49, 112, { exact: true }); // crash
    } else if (style.parts.drums && final) {
      add('drums', b0, 2, 49, 96, { exact: true });
      add('drums', b0, 0.2, 36, 100, { exact: true });
    }
    // Swell the pad in the bar before a peak (CC11)
    if (prePeak && style.parts.pad) for (let i = 0; i <= 8; i++) cc.push({ part: 'pad', beat: b0 + (i / 8) * bpb, num: 11, val: 70 + Math.round((57 * i) / 8) });
    if (isPeak && style.parts.pad) cc.push({ part: 'pad', beat: b0, num: 11, val: 127 });
    if (!isPeak && !prePeak && style.parts.pad) cc.push({ part: 'pad', beat: b0, num: 11, val: 110 });
  }
  return { style: music.style || 'calm', bpm, offset, beatsPerBar: bpb, bars: nBars, parts: style.parts, notes, cc, progression: prog.map((c) => c.name) };
}

// ── Write an SMF (Standard MIDI File, format 1) ─────────────────
function vlq(n) {
  const out = [n & 0x7f];
  while ((n >>= 7)) out.unshift((n & 0x7f) | 0x80);
  return out;
}
function track(events) {
  events.sort((a, b) => a.tick - b.tick || a.order - b.order);
  const bytes = [];
  let last = 0;
  for (const ev of events) {
    bytes.push(...vlq(ev.tick - last), ...ev.data);
    last = ev.tick;
  }
  bytes.push(0, 0xff, 0x2f, 0);
  const b = Buffer.from(bytes);
  return Buffer.concat([Buffer.from('MTrk'), Buffer.from([(b.length >>> 24) & 255, (b.length >>> 16) & 255, (b.length >>> 8) & 255, b.length & 255]), b]);
}
export function toSmf(song) {
  const off = (song.offset * song.bpm) / 60; // offset in seconds -> beats
  const tick = (beat) => Math.round((beat + off) * PPQ);
  const us = Math.round(60e6 / song.bpm);
  const tracks = [track([{ tick: 0, order: 0, data: [0xff, 0x51, 3, (us >> 16) & 255, (us >> 8) & 255, us & 255] }, { tick: 0, order: 1, data: [0xff, 0x58, 4, song.beatsPerBar, 2, 24, 8] }])];
  for (const [name, p] of Object.entries(song.parts)) {
    const ev = [
      { tick: 0, order: 0, data: [0xc0 | p.ch, p.program] },
      { tick: 0, order: 1, data: [0xb0 | p.ch, 7, p.vol] },
      { tick: 0, order: 2, data: [0xb0 | p.ch, 10, p.pan] },
      { tick: 0, order: 3, data: [0xb0 | p.ch, 91, 0] }, // don't use FluidSynth's built-in reverb/chorus (ffmpeg adds them)
      { tick: 0, order: 4, data: [0xb0 | p.ch, 93, 0] },
    ];
    for (const c of song.cc.filter((x) => x.part === name)) ev.push({ tick: tick(c.beat), order: 5, data: [0xb0 | p.ch, c.num, c.val] });
    for (const n of song.notes.filter((x) => x.part === name)) {
      const a = tick(n.beat);
      ev.push({ tick: a, order: 7, data: [0x90 | p.ch, n.key, n.vel] });
      ev.push({ tick: Math.max(a + 1, tick(n.beat + n.len)), order: 6, data: [0x80 | p.ch, n.key, 0] });
    }
    tracks.push(track(ev));
  }
  const head = Buffer.from([0x4d, 0x54, 0x68, 0x64, 0, 0, 0, 6, 0, 1, 0, tracks.length, PPQ >> 8, PPQ & 255]);
  return Buffer.concat([head, ...tracks]);
}

// ── Soundfont ───────────────────────────────────────────────────
export function resolveSoundfont(music = {}, base = process.cwd()) {
  const p = music.soundfont ? path.resolve(base, music.soundfont) : process.env.MOTION_VIDEO_SF2 || DEFAULT_SF2;
  if (!fs.existsSync(p)) throw new Error(`soundfont not found: ${p} (install it as described in references/audio-assets.md, or pass it via music.soundfont / MOTION_VIDEO_SF2)`);
  return p;
}
function fluidsynthVersion() {
  const r = spawnSync('fluidsynth', ['--version'], { encoding: 'utf8' });
  if (r.error || r.status !== 0) throw new Error('fluidsynth not found (brew install fluid-synth). Required for videos that specify music');
  return (/runtime version ([\d.]+)/.exec(r.stdout) || [])[1] || r.stdout.split('\n')[0];
}
const fileSha = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');

// Render MIDI with FluidSynth to a 48kHz / 32-bit float WAV.
// Built-in reverb/chorus are off (-R 0 -C 0). Float output means no dither is applied.
export function renderMidi(midPath, sf2, outWav) {
  const args = ['-ni', '-q', '-R', '0', '-C', '0', '-g', '0.5', '-r', String(SR),
    '-o', 'synth.cpu-cores=1', '-o', 'player.timing-source=sample', '-o', 'audio.file.type=wav', '-o', 'audio.file.format=float',
    '-F', outWav, sf2, midPath];
  const r = spawnSync('fluidsynth', args, { encoding: 'utf8' });
  if (r.status !== 0 || !fs.existsSync(outWav)) throw new Error(`fluidsynth failed: ${r.stderr || r.stdout}`);
}

// Compose the BGM and render it to WAV (uses the cache when the MIDI, soundfont and fluidsynth version are unchanged)
export function renderBgm({ duration, audio, scenes, music, work, base }) {
  const sf2 = resolveSoundfont(music, base);
  const version = fluidsynthVersion();
  const song = compose({ duration, audio, scenes, music });
  const smf = toSmf(song);
  const sf2sha = fileSha(sf2);
  const key = crypto.createHash('sha256').update(smf).update(`|${sf2sha}|${version}|${SR}`).digest('hex');
  const dir = path.join(work, 'bgm', key.slice(0, 16));
  fs.mkdirSync(dir, { recursive: true });
  const mid = path.join(dir, 'bgm.mid');
  const wav = path.join(dir, 'bgm.wav');
  if (!fs.existsSync(wav)) {
    fs.writeFileSync(mid, smf);
    renderMidi(mid, sf2, `${wav}.tmp.wav`);
    fs.renameSync(`${wav}.tmp.wav`, wav);
  }
  return {
    wav, mid,
    info: { style: song.style, progression: song.progression, bars: song.bars, notes: song.notes.length, seed: music.seed ?? 1, soundfont: sf2, soundfontSha256: sf2sha, fluidsynth: version, midiSha256: crypto.createHash('sha256').update(smf).digest('hex') },
  };
}

// ── Impulse response for convolution reverb (synthesized with a fixed seed) ──
// Exponentially decaying stereo noise whose highs die away first over time (approximates room absorption).
export function synthIR({ seconds = 1.6, seed = 7, predelay = 0.012 } = {}) {
  const n = Math.round(SR * seconds);
  const L = new Float32Array(n);
  const R = new Float32Array(n);
  const rl = rng(seed);
  const rr = rng(seed + 1);
  let yl = 0;
  let yr = 0;
  const d0 = Math.round(SR * predelay);
  for (let i = d0; i < n; i++) {
    const t = (i - d0) / SR;
    const env = Math.exp((-6.9 * t) / seconds); // -60 dB at `seconds`
    const cutoff = 9000 * Math.exp(-t * 2.2) + 600;
    const a = 1 - Math.exp((-2 * Math.PI * cutoff) / SR);
    yl += a * (rl() * 2 - 1 - yl);
    yr += a * (rr() * 2 - 1 - yr);
    L[i] = yl * env;
    R[i] = yr * env;
  }
  return { L, R };
}

// ── CLI ────────────────────────────────────────────────────────
if (import.meta.url === `file://${process.argv[1]}`) {
  const a = process.argv.slice(2);
  const get = (k, d) => (a.includes(k) ? a[a.indexOf(k) + 1] : d);
  if (a.includes('--styles')) {
    for (const [k, v] of Object.entries(STYLES)) console.log(`${k}\t${v.description}`);
    process.exit(0);
  }
  const duration = parseFloat(get('--duration', '8'));
  const audio = { bpm: parseFloat(get('--bpm', '120')), peaks: get('--peaks') ? get('--peaks').split(',').map(Number) : [] };
  const music = { progression: get('--progression', 'C,G,Am,F').split(','), style: get('--style', 'calm'), seed: parseInt(get('--seed', '1'), 10) };
  const out = path.resolve(get('--out', 'bgm.wav'));
  const song = compose({ duration, audio, music });
  const smf = toSmf(song);
  const mid = path.resolve(get('--mid', out.replace(/\.wav$/, '') + '.mid'));
  fs.writeFileSync(mid, smf);
  renderMidi(mid, resolveSoundfont(music), out);
  console.log(JSON.stringify({ out, mid, style: song.style, bars: song.bars, notes: song.notes.length }, null, 2));
}
