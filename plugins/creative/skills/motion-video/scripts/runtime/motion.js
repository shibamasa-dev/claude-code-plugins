// motion.js — deterministic motion building blocks (works in browser and node; no DOM dependency)
// All pure functions: put in a time t, get a value. No timers, no Math.random, no state from the previous frame.

// ── Spring (closed-form) ────────────────────────────────────────
// Exact solution of a damped oscillator. Returns the step response from 0 to 1.
// stiffness=k, damping=d, mass=m. ζ = d / (2√(km)) sets the damping character.
// The k and d for snappy / default / playful come from the playbook "Opus 5.5 Motion Design Prompting Techniques".
// heavy is not in that playbook; this skill chose it (a guess, aiming to land heavily with almost no overshoot).
// When to use: UI (cards, buttons) may overshoot slightly -> snappy / playful.
//              Text must not overshoot -> default (ζ≈1) or heavy.
export const PRESETS = {
  snappy: { stiffness: 260, damping: 24, mass: 1 },   // ζ≈0.74 buttons, toggles. Fast, overshoots about 3%
  default: { stiffness: 170, damping: 26, mass: 1 },  // ζ≈1.0 cards, camera, text. No overshoot
  playful: { stiffness: 130, damping: 18, mass: 1 },  // ζ≈0.79 mascots, stickers. Bouncy
  heavy: { stiffness: 120, damping: 30, mass: 2.5 },  // ζ≈0.87 heavy objects, large surfaces (guessed values)
};

function resolvePreset(p) {
  if (!p) return PRESETS.default;
  if (typeof p === 'string') {
    const v = PRESETS[p];
    if (!v) throw new Error(`unknown spring preset: ${p} (${Object.keys(PRESETS).join(' / ')})`);
    return v;
  }
  return { ...PRESETS.default, ...p };
}

// Progress at t seconds (time elapsed since the spring started). 0 for t<=0.
export function spring(t, preset = 'default', { velocity = 0 } = {}) {
  if (t <= 0) return 0;
  const { stiffness: k, damping: c, mass: m } = resolvePreset(preset);
  const w0 = Math.sqrt(k / m);
  const z = c / (2 * Math.sqrt(k * m));
  const x0 = -1; // displacement from the target (1)
  const v0 = velocity;
  let x;
  if (z < 1 - 1e-9) {
    const wd = w0 * Math.sqrt(1 - z * z);
    x = Math.exp(-z * w0 * t) * (x0 * Math.cos(wd * t) + ((v0 + z * w0 * x0) / wd) * Math.sin(wd * t));
  } else if (z > 1 + 1e-9) {
    const s = Math.sqrt(z * z - 1);
    const r1 = -w0 * (z - s);
    const r2 = -w0 * (z + s);
    const A = (v0 - r2 * x0) / (r1 - r2);
    const B = x0 - A;
    x = A * Math.exp(r1 * t) + B * Math.exp(r2 * t);
  } else {
    x = Math.exp(-w0 * t) * (x0 + (v0 + w0 * x0) * t);
  }
  return 1 + x;
}

// Seconds until settled (approximates the first time after which |1-x| < eps holds for good). For estimating scene durations.
export function springDuration(preset = 'default', eps = 0.001) {
  const dt = 1 / 240;
  let last = 0;
  for (let t = 0; t < 20; t += dt) if (Math.abs(1 - spring(t, preset)) >= eps) last = t;
  return Math.round((last + dt) * 1000) / 1000;
}

// Add one spring each time the target changes (superposition).
// keys: [{ t: 0, v: 0 }, { t: 1.2, v: 100 }, { t: 3, v: 40, preset: 'snappy' }]
// value = keys[0].v + Σ (keys[i].v - keys[i-1].v) * spring(t - keys[i].t)
// Because the system is linear, a mid-flight target change connects naturally with continuous velocity.
export function springTrack(t, keys, preset = 'default') {
  if (!keys.length) return 0;
  let v = keys[0].v;
  for (let i = 1; i < keys.length; i++) {
    v += (keys[i].v - keys[i - 1].v) * spring(t - keys[i].t, keys[i].preset ?? preset);
  }
  return v;
}

// ── Interpolation and easing ───────────────────────────────────
export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, p) => a + (b - a) * p;
// Normalize t over [a,b] to 0..1 (clamped outside the range)
export const progress = (t, a, b) => (b === a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a)));
export const ease = {
  linear: (p) => p,
  outCubic: (p) => 1 - Math.pow(1 - p, 3),
  inCubic: (p) => p * p * p,
  inOutCubic: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
  outExpo: (p) => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
};
// Start time of the i-th element (staggered entrance)
export const stagger = (start, i, gap = 0.08) => start + i * gap;

// ── Beat grid ──────────────────────────────────────────────────
// Derives beat times from the BPM. Used to put motion cues and sound effects on the same beat.
export function beatGrid(bpm = 120, offset = 0, beatsPerBar = 4) {
  const spb = 60 / bpm;
  return {
    bpm,
    spb,
    beat: (n) => offset + n * spb,               // time of beat n
    bar: (n, b = 0) => offset + (n * beatsPerBar + b) * spb, // time of beat b in bar n
    index: (t) => Math.floor((t - offset) / spb + 1e-9),     // which beat t falls on
    phase: (t) => ((((t - offset) / spb) % 1) + 1) % 1,       // phase within the beat, 0..1
    nearest: (t) => offset + Math.round((t - offset) / spb) * spb,
  };
}

// ── Random numbers (fixed seed) ────────────────────────────────
// Never use Math.random. The same seed always gives the same sequence.
export function rng(seed = 1) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let x = a;
    x = Math.imul(x ^ (x >>> 15), x | 1);
    x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

// ── Color ──────────────────────────────────────────────────────
export function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const f = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  return [0, 2, 4].map((i) => parseInt(f.slice(i, i + 2), 16));
}
export function mixColor(a, b, p) {
  const A = hexToRgb(a);
  const B = hexToRgb(b);
  const c = A.map((v, i) => Math.round(lerp(v, B[i], clamp(p))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
export function withAlpha(hex, alpha) {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${clamp(alpha)})`;
}

// ── Layout functions ───────────────────────────────────────────
// Place things in units u, where the screen's short side is 100, rather than in fixed pixels.
// This is what lets one scene definition produce 16:9 / 9:16 / 1:1.
export function layout(W, H, { margin = 6 } = {}) {
  const u = Math.min(W, H) / 100;
  const ratio = W / H;
  const orient = ratio > 1.15 ? 'landscape' : ratio < 0.87 ? 'portrait' : 'square';
  const m = margin * u;
  const safe = { x: m, y: m, w: W - 2 * m, h: H - 2 * m };
  return {
    W, H, u, ratio, orient,
    cx: W / 2, cy: H / 2,
    safe,
    // Two-way split: side by side when landscape, stacked when portrait
    split(gap = 4) {
      const g = gap * u;
      if (orient === 'portrait') {
        const h = (safe.h - g) / 2;
        return [{ x: safe.x, y: safe.y, w: safe.w, h }, { x: safe.x, y: safe.y + h + g, w: safe.w, h }];
      }
      const w = (safe.w - g) / 2;
      return [{ x: safe.x, y: safe.y, w, h: safe.h }, { x: safe.x + w + g, y: safe.y, w, h: safe.h }];
    },
    // cols x rows grid
    grid(cols, rows, gap = 3, box = safe) {
      const g = gap * u;
      const w = (box.w - g * (cols - 1)) / cols;
      const h = (box.h - g * (rows - 1)) / rows;
      const cells = [];
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) cells.push({ x: box.x + c * (w + g), y: box.y + r * (h + g), w, h });
      return cells;
    },
  };
}

// Fit an image into a box (contain = whole image visible / cover = fills the box)
export function fit(iw, ih, box, mode = 'contain') {
  const s = mode === 'cover' ? Math.max(box.w / iw, box.h / ih) : Math.min(box.w / iw, box.h / ih);
  const w = iw * s;
  const h = ih * s;
  return { x: box.x + (box.w - w) / 2, y: box.y + (box.h - h) / 2, w, h };
}
