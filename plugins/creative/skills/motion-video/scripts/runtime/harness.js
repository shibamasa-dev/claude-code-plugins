// harness.js — page-side foundation that render.mjs (node) calls over CDP.
// Loads the project's video.js, waits until every asset has loaded, then calls render(ctx, t) per time and returns one frame.
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

// Block non-deterministic APIs while drawing (using one throws and stops the render)
const real = { random: Math.random, now: Date.now, perf: performance.now.bind(performance) };
function lock(on) {
  if (on) {
    Math.random = () => { throw new Error('Math.random is not allowed. Use ctx.M.rng(seed)'); };
    Date.now = () => { throw new Error('Date.now is not allowed. Use only t from render(ctx, t) for time'); };
    performance.now = () => { throw new Error('performance.now is not allowed. Use only t for time'); };
  } else {
    Math.random = real.random;
    Date.now = real.now;
    performance.now = real.perf;
  }
}

function loadImage(src) {
  const img = new Image();
  img.src = src;
  return img.decode().then(() => img, () => { throw new Error(`cannot load asset: ${src}`); });
}

function fontStack(role, size, weight = 700) {
  const f = brand?.fonts?.[role];
  const fam = f ? [f.family, ...(f.fallback || [])] : [role, 'sans-serif'];
  const q = fam.map((n) => (/^(serif|sans-serif|monospace|system-ui)$/.test(n) ? n : `"${n}"`)).join(', ');
  return `${weight} ${size}px ${q}`;
}

// Whether the family is actually available (judged by whether glyph widths differ from the fallback)
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
      if (!im) throw new Error(`no asset key: ${key} (register it in meta.assets, or as brand.logo=@logo)`);
      used.images[key] = (used.images[key] || 0) + 1;
      return im;
    },
    // Frame of a live-action clip at localT seconds (does not use the browser's <video>)
    clip(key, localT, { loop = false } = {}) {
      const c = clips[key];
      if (!c) throw new Error(`no clip key: ${key} (register it in meta.clips)`);
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

// Motion blur by averaging subframes (blends times within the same frame, not the previous frame)
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
  // (1) Load video.js and return meta (node uses it to split clips into numbered frames)
  async load() {
    mod = await import('/project/video.js');
    if (!mod.meta || typeof mod.render !== 'function') throw new Error('video.js must export meta and render(ctx, t)');
    meta = { fps: 60, shutter: 0.5, subframes: 4, scenes: [], assets: {}, clips: {}, ...mod.meta };
    return JSON.parse(JSON.stringify(meta));
  },
  // (2) Return only after every asset, font and clip frame has loaded (prevents a font swap on the first frame)
  async init({ brandJson, clipCounts }) {
    brand = brandJson || { colors: {}, fonts: {} };
    const jobs = [];
    for (const [role, f] of Object.entries(brand.fonts || {})) {
      if (f.file) {
        const face = new FontFace(f.family, `url(/brand/${encodeURI(f.file)})`, { weight: f.weight || '100 900' });
        document.fonts.add(face);
        jobs.push(face.load().catch(() => { throw new Error(`cannot load font: ${f.file}`); }));
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
  // (3) Return the frame at time t as a PNG (dataURL)
  async frame(t, subframes) {
    await composite(t, subframes ?? meta.subframes, meta.shutter);
    return out.toDataURL('image/png');
  },
  // Draw every frame at a small resolution and return the difference between adjacent frames (amount of motion). Used for the strip and for detecting "stretches without motion"
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
  // Difference between the frames at two times (checks continuity across the loop seam)
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
