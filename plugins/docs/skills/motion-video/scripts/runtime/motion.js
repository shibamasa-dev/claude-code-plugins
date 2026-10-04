// motion.js — 決定論の動きの部品（ブラウザ / node 両用・DOM 非依存）
// すべて「時刻 t を入れると値が決まる」純関数。タイマー・Math.random・前フレームの状態に依存しない。

// ── ばね（closed-form） ─────────────────────────────────────────
// 減衰振動子の厳密解。0→1 へのステップ応答を返す。
// stiffness=k, damping=d, mass=m。ζ = d / (2√(km)) で減衰の性格が決まる。
// snappy / default / playful の k・d はプレイブック「Opus 5.5 Motion Design Prompting Techniques」の値。
// heavy は同資料に無く、このスキルで決めた値（推測。重く・ほぼ行き過ぎずに着地する狙い）。
// 使い分け: UI（カード・ボタン）は小さく行き過ぎてよい → snappy / playful。
//           文字は行き過ぎさせない → default（ζ≈1）か heavy。
export const PRESETS = {
  snappy: { stiffness: 260, damping: 24, mass: 1 },   // ζ≈0.74 ボタン・トグル。速く、3%ほど行き過ぎる
  default: { stiffness: 170, damping: 26, mass: 1 },  // ζ≈1.0 カード・カメラ・文字。行き過ぎない
  playful: { stiffness: 130, damping: 18, mass: 1 },  // ζ≈0.79 マスコット・ステッカー。弾む
  heavy: { stiffness: 120, damping: 30, mass: 2.5 },  // ζ≈0.87 重い物・大きな面（推測値）
};

function resolvePreset(p) {
  if (!p) return PRESETS.default;
  if (typeof p === 'string') {
    const v = PRESETS[p];
    if (!v) throw new Error(`unknown spring preset: ${p}（${Object.keys(PRESETS).join(' / ')}）`);
    return v;
  }
  return { ...PRESETS.default, ...p };
}

// t 秒（ばねが動き出してからの経過）での進捗。t<=0 は 0。
export function spring(t, preset = 'default', { velocity = 0 } = {}) {
  if (t <= 0) return 0;
  const { stiffness: k, damping: c, mass: m } = resolvePreset(preset);
  const w0 = Math.sqrt(k / m);
  const z = c / (2 * Math.sqrt(k * m));
  const x0 = -1; // 目標(1)からの変位
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

// 収束までの秒数（|1-x| < eps が以後ずっと続く最初の時刻の近似）。シーン尺の見積もり用。
export function springDuration(preset = 'default', eps = 0.001) {
  const dt = 1 / 240;
  let last = 0;
  for (let t = 0; t < 20; t += dt) if (Math.abs(1 - spring(t, preset)) >= eps) last = t;
  return Math.round((last + dt) * 1000) / 1000;
}

// ターゲットが変わるたびにばねを1本足す（重ね合わせ）。
// keys: [{ t: 0, v: 0 }, { t: 1.2, v: 100 }, { t: 3, v: 40, preset: 'snappy' }]
// 値 = keys[0].v + Σ (keys[i].v - keys[i-1].v) * spring(t - keys[i].t)
// 線形系なので、途中でターゲットが変わっても速度が連続したまま自然につながる。
export function springTrack(t, keys, preset = 'default') {
  if (!keys.length) return 0;
  let v = keys[0].v;
  for (let i = 1; i < keys.length; i++) {
    v += (keys[i].v - keys[i - 1].v) * spring(t - keys[i].t, keys[i].preset ?? preset);
  }
  return v;
}

// ── 補間・イージング ───────────────────────────────────────────
export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, p) => a + (b - a) * p;
// t を [a,b] で 0..1 に正規化（範囲外はクランプ）
export const progress = (t, a, b) => (b === a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a)));
export const ease = {
  linear: (p) => p,
  outCubic: (p) => 1 - Math.pow(1 - p, 3),
  inCubic: (p) => p * p * p,
  inOutCubic: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
  outExpo: (p) => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
};
// i 番目の要素の開始時刻（ずらし登場）
export const stagger = (start, i, gap = 0.08) => start + i * gap;

// ── ビートグリッド ─────────────────────────────────────────────
// BPM から拍の時刻を出す。動きのきっかけと効果音を同じ拍に揃えるために使う。
export function beatGrid(bpm = 120, offset = 0, beatsPerBar = 4) {
  const spb = 60 / bpm;
  return {
    bpm,
    spb,
    beat: (n) => offset + n * spb,               // n 拍目の時刻
    bar: (n, b = 0) => offset + (n * beatsPerBar + b) * spb, // n 小節目 b 拍の時刻
    index: (t) => Math.floor((t - offset) / spb + 1e-9),     // t が何拍目か
    phase: (t) => ((((t - offset) / spb) % 1) + 1) % 1,       // 拍内の位相 0..1
    nearest: (t) => offset + Math.round((t - offset) / spb) * spb,
  };
}

// ── 乱数（シード固定） ─────────────────────────────────────────
// Math.random は使わない。同じ seed なら毎回同じ列。
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

// ── 色 ─────────────────────────────────────────────────────────
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

// ── レイアウト関数 ─────────────────────────────────────────────
// 固定ピクセルで置かず、画面の短辺を 100 とした単位 u で置く。
// 同じシーン定義から 16:9 / 9:16 / 1:1 を出せるのはこれのおかげ。
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
    // 横長なら横並び、縦長なら縦積みの2分割
    split(gap = 4) {
      const g = gap * u;
      if (orient === 'portrait') {
        const h = (safe.h - g) / 2;
        return [{ x: safe.x, y: safe.y, w: safe.w, h }, { x: safe.x, y: safe.y + h + g, w: safe.w, h }];
      }
      const w = (safe.w - g) / 2;
      return [{ x: safe.x, y: safe.y, w, h: safe.h }, { x: safe.x + w + g, y: safe.y, w, h: safe.h }];
    },
    // cols×rows の格子
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

// 画像を枠に収める（contain=全体が入る / cover=枠を埋める）
export function fit(iw, ih, box, mode = 'contain') {
  const s = mode === 'cover' ? Math.max(box.w / iw, box.h / ih) : Math.min(box.w / iw, box.h / ih);
  const w = iw * s;
  const h = ih * s;
  return { x: box.x + (box.w - w) / 2, y: box.y + (box.h - h) / 2, w, h };
}
