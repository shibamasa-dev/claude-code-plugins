// harness.js — render.mjs（node）から CDP 経由で呼ばれるページ側の土台。
// プロジェクトの video.js を読み、素材を全部読み込み終えてから、render(ctx, t) を時刻ごとに呼んで1コマを返す。
import * as M from './motion.js';
import * as D from './draw.js';

const out = document.getElementById('out');
const og = out.getContext('2d', { willReadFrequently: true });
const work = document.createElement('canvas');
const g = work.getContext('2d', { willReadFrequently: true });

let mod = null;
let meta = null;
let brand = null;
let ctx = null;
const images = {};
const clips = {};
const used = { images: {}, clips: {} };
const fonts = {};

// 描画中だけ非決定の API を塞ぐ（使ったら例外で止める）
const real = { random: Math.random, now: Date.now, perf: performance.now.bind(performance) };
function lock(on) {
  if (on) {
    Math.random = () => { throw new Error('Math.random は使えない。ctx.M.rng(seed) を使う'); };
    Date.now = () => { throw new Error('Date.now は使えない。時刻は render(ctx, t) の t だけを使う'); };
    performance.now = () => { throw new Error('performance.now は使えない。時刻は t だけを使う'); };
  } else {
    Math.random = real.random;
    Date.now = real.now;
    performance.now = real.perf;
  }
}

function loadImage(src) {
  const img = new Image();
  img.src = src;
  return img.decode().then(() => img, () => { throw new Error(`素材を読めない: ${src}`); });
}

function fontStack(role, size, weight = 700) {
  const f = brand?.fonts?.[role];
  const fam = f ? [f.family, ...(f.fallback || [])] : [role, 'sans-serif'];
  const q = fam.map((n) => (/^(serif|sans-serif|monospace|system-ui)$/.test(n) ? n : `"${n}"`)).join(', ');
  return `${weight} ${size}px ${q}`;
}

// family が実際に使えるか（fallback と字幅が変わるかで判定）
function fontAvailable(family) {
  const probe = 'mmmWWWあいう漢字Il1';
  for (const base of ['monospace', 'serif']) {
    g.font = `48px ${base}`;
    const a = g.measureText(probe).width;
    g.font = `48px "${family}", ${base}`;
    if (g.measureText(probe).width !== a) return true;
  }
  return false;
}

function buildCtx(W, H) {
  return {
    g, W, H, M, D, meta, brand,
    fps: meta.fps,
    duration: meta.duration,
    L: M.layout(W, H),
    beats: M.beatGrid(meta.audio?.bpm ?? 120, meta.audio?.offset ?? 0, meta.audio?.beatsPerBar ?? 4),
    font: fontStack,
    img(key) {
      const im = images[key];
      if (!im) throw new Error(`素材キーが無い: ${key}（meta.assets か brand.logo=@logo に登録する）`);
      used.images[key] = (used.images[key] || 0) + 1;
      return im;
    },
    // 実写クリップの localT 秒目のコマ（ブラウザの <video> は使わない）
    clip(key, localT, { loop = false } = {}) {
      const c = clips[key];
      if (!c) throw new Error(`クリップキーが無い: ${key}（meta.clips に登録する）`);
      let i = Math.floor(Math.max(0, localT) * c.fps + 1e-6);
      i = loop ? i % c.frames.length : Math.min(i, c.frames.length - 1);
      (used.clips[key] ||= {})[i] = true;
      return c.frames[i];
    },
    scene(t) {
      const sc = meta.scenes || [];
      const s = sc.find((x) => t >= x.start && t < x.end) || sc[sc.length - 1];
      if (!s) return null;
      return { ...s, local: t - s.start, p: M.progress(t, s.start, s.end) };
    },
    text: (str, x, y, o) => D.text(g, str, x, y, o),
    image: (im, box, o) => D.image(g, im, box, o),
  };
}

async function drawOnce(t) {
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.globalAlpha = 1;
  g.globalCompositeOperation = 'source-over';
  g.filter = 'none';
  g.shadowBlur = 0;
  g.shadowColor = 'rgba(0,0,0,0)';
  g.clearRect(0, 0, work.width, work.height);
  g.save();
  lock(true);
  try {
    await mod.render(ctx, t);
  } finally {
    lock(false);
    g.restore();
  }
}

// サブフレームを平均してモーションブラー（前フレームではなく、同じコマ内の時刻を混ぜる）
async function composite(t, subframes, shutter) {
  const W = work.width;
  const H = work.height;
  if (subframes <= 1) {
    await drawOnce(t);
    og.clearRect(0, 0, W, H);
    og.drawImage(work, 0, 0);
    return;
  }
  const acc = new Uint32Array(W * H * 4);
  for (let k = 0; k < subframes; k++) {
    await drawOnce(t + (k / subframes) * (shutter / meta.fps));
    const d = g.getImageData(0, 0, W, H).data;
    for (let i = 0; i < d.length; i++) acc[i] += d[i];
  }
  const img = og.createImageData(W, H);
  const half = subframes >> 1;
  for (let i = 0; i < acc.length; i++) img.data[i] = ((acc[i] + half) / subframes) | 0;
  og.putImageData(img, 0, 0);
}

window.__mv = {
  // ① video.js を読み、meta を返す（node はこれを見てクリップを連番化する）
  async load() {
    mod = await import('/project/video.js');
    if (!mod.meta || typeof mod.render !== 'function') throw new Error('video.js は meta と render(ctx, t) を export する');
    meta = { fps: 60, shutter: 0.5, subframes: 4, scenes: [], assets: {}, clips: {}, ...mod.meta };
    return JSON.parse(JSON.stringify(meta));
  },
  // ② 素材・フォント・クリップのコマを全部読み終えてから返す（1コマ目のフォント差し替わりを防ぐ）
  async init({ brandJson, clipCounts }) {
    brand = brandJson || { colors: {}, fonts: {} };
    const jobs = [];
    for (const [role, f] of Object.entries(brand.fonts || {})) {
      if (f.file) {
        const face = new FontFace(f.family, `url(/brand/${encodeURI(f.file)})`, { weight: f.weight || '100 900' });
        document.fonts.add(face);
        jobs.push(face.load().catch(() => { throw new Error(`フォントを読めない: ${f.file}`); }));
      }
    }
    for (const [k, p] of Object.entries(meta.assets || {})) jobs.push(loadImage(`/project/${encodeURI(p)}`).then((im) => (images[k] = im)));
    if (brand.logo) jobs.push(loadImage(`/brand/${encodeURI(brand.logo)}`).then((im) => (images['@logo'] = im)));
    for (const [k, c] of Object.entries(meta.clips || {})) {
      const n = clipCounts[k];
      const frames = new Array(n);
      clips[k] = { fps: c.fps, frames };
      for (let i = 0; i < n; i++) jobs.push(loadImage(`/clips/${k}/${String(i + 1).padStart(5, '0')}.png`).then((im) => (frames[i] = im)));
    }
    await Promise.all(jobs);
    for (const [role, f] of Object.entries(brand.fonts || {})) {
      await document.fonts.load(fontStack(role, 48, 400), 'Aあ');
      await document.fonts.load(fontStack(role, 48, 700), 'Aあ');
      fonts[f.family] = fontAvailable(f.family);
    }
    await document.fonts.ready;
    return { fonts };
  },
  resize(W, H) {
    out.width = work.width = W;
    out.height = work.height = H;
    ctx = buildCtx(W, H);
  },
  // ③ 時刻 t の1コマを PNG(dataURL) で返す
  async frame(t, subframes) {
    await composite(t, subframes ?? meta.subframes, meta.shutter);
    return out.toDataURL('image/png');
  },
  // 全コマを小さな解像度で描き、隣り合うコマの差（動きの量）を返す。strip と「動きの無い区間」の判定に使う
  async motionScan(n) {
    const W = work.width;
    const H = work.height;
    let prev = null;
    const diffs = [];
    for (let i = 0; i < n; i++) {
      await drawOnce(i / meta.fps);
      const d = g.getImageData(0, 0, W, H).data;
      if (prev) {
        let s = 0;
        for (let j = 0; j < d.length; j += 4) s += Math.abs(d[j] - prev[j]) + Math.abs(d[j + 1] - prev[j + 1]) + Math.abs(d[j + 2] - prev[j + 2]);
        diffs.push(s / (W * H * 3 * 255));
      } else diffs.push(0);
      prev = d;
    }
    return diffs;
  },
  // 2つの時刻のコマの差（ループ継ぎ目の連続性を見る）
  async pairDiff(pairs) {
    const W = work.width;
    const H = work.height;
    const res = [];
    for (const [a, b] of pairs) {
      await drawOnce(a);
      const d1 = g.getImageData(0, 0, W, H).data;
      await drawOnce(b);
      const d2 = g.getImageData(0, 0, W, H).data;
      let s = 0;
      for (let j = 0; j < d1.length; j += 4) s += Math.abs(d1[j] - d2[j]) + Math.abs(d1[j + 1] - d2[j + 1]) + Math.abs(d1[j + 2] - d2[j + 2]);
      res.push(s / (W * H * 3 * 255));
    }
    return res;
  },
  manifest() {
    const clipsUsed = {};
    for (const [k, v] of Object.entries(used.clips)) clipsUsed[k] = Object.keys(v).length;
    return { images: used.images, clipFramesDistinct: clipsUsed, fonts };
  },
};
window.__mvReady = true;
