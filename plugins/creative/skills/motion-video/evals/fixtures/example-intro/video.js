// eval (a): Example Co. (a fictional furniture store) intro, 15 s, 16:9. Brand colors, typefaces and logo come from brand.json (no hard-coded colors here).
// Built on the five-beat product-video template (problem -> the mechanism assembles -> three things it does -> one number -> logo + CTA).
// The on-screen copy and narration stay in Japanese on purpose: this fixture exercises CJK font handling with the `ja` font role.
export const meta = {
  title: 'Example Co. intro',
  duration: 15,
  fps: 60,
  aspects: ['16:9'],
  scenes: [
    { id: 's1', start: 0, end: 3, key: 1.6, message: 'Problem: not sure which furniture fits the room', screen: 'Primary-color panel on the left, large knocked-out white heading', motion: { enter: 'The panel springs up from the bottom', main: 'The heading comes in word by word', exit: 'The heading exits upward first' }, narration: 'その棚、部屋に入りますか。', sound: 'thump on the bar start', transition: 'The primary-color panel shrinks into the left column of the next scene' },
    { id: 's2', start: 3, end: 6, key: 4.8, message: 'Pick by size and the room assembles', screen: 'Heading in the left column, three UI cards stack up on the right', motion: { enter: 'Cards enter with snappy on each beat', main: 'Bars inside the cards grow', exit: 'Cards exit to the right' }, narration: 'サイズから選んで、並べてみる。', sound: 'whoosh and pop x3', transition: 'The left column tips over upward into a heading band' },
    { id: 's3', start: 6, end: 9.5, key: 8.2, message: 'Three things it does', screen: 'Band on top, three feature cards below', motion: { enter: 'One card per beat', main: 'The selection marker moves left to right', exit: 'Cards sink downward' }, narration: '採寸、配置、お届けまで。', sound: 'click x3', transition: 'The band folds into a square in the center' },
    { id: 's4', start: 9.5, end: 12, key: 11.2, message: 'One number: founded in 1987', screen: 'Large number in the center square', motion: { enter: 'The number counts up with a spring', main: 'An underline grows', exit: 'The number disappears first' }, narration: '1987 年に創業。', sound: 'pop', transition: 'The square expands to fill the screen and becomes the logo background' },
    { id: 's5', start: 12, end: 15, key: 13.8, message: 'Logo and CTA', screen: 'Full primary-color screen, logo and a tagline in the center', motion: { enter: 'The logo lands with heavy', main: 'The CTA comes in from below', exit: 'Hold' }, narration: '新しい部屋を、一緒に。', sound: 'thump on the bar start', transition: 'End (hold)' },
  ],
  audio: {
    bpm: 120,
    peaks: [0, 12],
    cues: [
      { bar: 0, sfx: 'thump' },
      { t: 3, sfx: 'whoosh', gain: 0.6 },
      { t: 3.5, sfx: 'pop', gain: 0.7 }, { t: 4, sfx: 'pop', gain: 0.7 }, { t: 4.5, sfx: 'pop', gain: 0.7 },
      { t: 6.5, sfx: 'click' }, { t: 7, sfx: 'click' }, { t: 7.5, sfx: 'click' },
      { t: 9.5, sfx: 'whoosh', gain: 0.6 }, { t: 10, sfx: 'pop' },
      { bar: 6, sfx: 'thump' },
    ],
  },
};

// Panel position per scene (layout functions; no fixed pixels)
function panelFor(id, L) {
  const s = L.safe;
  const land = L.orient !== 'portrait';
  switch (id) {
    case 's1': return land ? { x: s.x, y: s.y, w: s.w * 0.62, h: s.h, r: 3 } : { x: s.x, y: s.y, w: s.w, h: s.h * 0.62, r: 3 };
    case 's2': return land ? { x: s.x, y: s.y, w: s.w * 0.34, h: s.h, r: 3 } : { x: s.x, y: s.y, w: s.w, h: s.h * 0.3, r: 3 };
    case 's3': return { x: s.x, y: s.y, w: s.w, h: s.h * 0.24, r: 3 };
    case 's4': { const d = Math.min(s.w, s.h) * 0.7; return { x: L.cx - d / 2, y: L.cy - d / 2, w: d, h: d, r: 6 }; }
    default: return { x: 0, y: 0, w: L.W, h: L.H, r: 0 };
  }
}

export function render(ctx, t) {
  const { g, W, H, L, M, D, brand } = ctx;
  const C = brand.colors;
  const u = L.u;
  D.fill(g, W, H, C.paper);

  // Panel: add one spring each time the scene changes (springTrack). The morph starts 0.15 s before the scene boundary
  const ids = ['s1', 's2', 's3', 's4', 's5'];
  const starts = [0, 3, 6, 9.5, 12];
  const rects = ids.map((id) => panelFor(id, L));
  const track = (k) => M.springTrack(t, rects.map((r, i) => ({ t: i === 0 ? 0 : starts[i] - 0.15, v: r[k] })), 'default');
  const rise = M.spring(t, 'snappy');
  const pr = { x: track('x'), y: track('y') + (1 - rise) * H * 0.4, w: track('w'), h: track('h'), r: track('r') };
  g.fillStyle = C.primary;
  D.roundRect(g, pr.x, pr.y, pr.w, pr.h, pr.r * u);
  g.fill();

  // Text in/out: exits happen before the panel morph, entrances after the morph starts
  const inOut = (a, b) => M.spring(t - a, 'default') * (1 - M.ease.inCubic(M.progress(t, b - 0.45, b - 0.2)));

  // s1 problem
  if (t < 3) {
    const words = ['その棚、', '部屋に', '入る？'];
    words.forEach((w, i) => {
      const p = inOut(0.35 + i * 0.25, 3);
      ctx.text(w, pr.x + 7 * u, pr.y + 12 * u + i * 17 * u + (1 - p) * 6 * u, { font: ctx.font('ja', 15 * u, 800), color: C.paper, alpha: p });
    });
  }
  // s2 the mechanism assembles
  if (t >= 2.85 && t < 6) {
    const p = inOut(3.15, 6);
    ctx.text('サイズで\n選んで、\n並べる', pr.x + 5 * u, pr.y + 8 * u, { font: ctx.font('ja', 8.5 * u, 800), color: C.paper, alpha: p, lineHeight: 1.3, maxWidth: pr.w - 10 * u });
    const colX = L.orient === 'portrait' ? L.safe.x : pr.x + pr.w + 4 * u;
    const colY = L.orient === 'portrait' ? pr.y + pr.h + 4 * u : L.safe.y;
    const colW = L.orient === 'portrait' ? L.safe.w : L.safe.x + L.safe.w - colX;
    const cardH = ((L.orient === 'portrait' ? L.safe.y + L.safe.h - colY : L.safe.h) - 8 * u) / 3;
    [C.accent, C.secondary, C.support].forEach((col, i) => {
      const a = 3.5 + i * 0.5;
      const e = M.spring(t - a, 'snappy');
      const out = M.ease.inCubic(M.progress(t, 5.55, 5.85));
      const x = colX + (1 - e) * 20 * u + out * W * 0.6;
      const y = colY + i * (cardH + 4 * u);
      g.fillStyle = '#FFFFFF';
      D.roundRect(g, x, y, colW, cardH, 2.5 * u);
      g.fill();
      g.fillStyle = col;
      D.roundRect(g, x + 3 * u, y + cardH * 0.35, (colW - 6 * u) * M.clamp(M.spring(t - a - 0.2, 'default')) * (0.55 + 0.15 * i), cardH * 0.3, 1.5 * u);
      g.fill();
    });
  }
  // s3 three things it does
  if (t >= 5.85 && t < 9.5) {
    const p = inOut(6.15, 9.5);
    ctx.text('できること', pr.x + 5 * u, pr.y + pr.h / 2, { font: ctx.font('ja', 8 * u, 800), color: C.paper, baseline: 'middle', alpha: p });
    const box = { x: L.safe.x, y: pr.y + pr.h + 5 * u, w: L.safe.w, h: L.safe.y + L.safe.h - (pr.y + pr.h + 5 * u) };
    const cells = L.orient === 'portrait' ? L.grid(1, 3, 3, box) : L.grid(3, 1, 3, box);
    const labels = ['採寸の\n無料相談', '部屋の\n配置プラン', '組み立て\nお届け'];
    const sel = M.springTrack(t, [{ t: 0, v: 0 }, { t: 7.5, v: 1 }, { t: 8.5, v: 2 }], 'snappy');
    cells.forEach((c, i) => {
      const e = M.spring(t - (6.5 + i * 0.5), 'snappy');
      const sink = M.ease.inCubic(M.progress(t, 9.05, 9.35));
      const y = c.y + (1 - e) * 10 * u + sink * H * 0.5;
      g.globalAlpha = M.clamp(e * 1.4);
      g.fillStyle = '#FFFFFF';
      D.roundRect(g, c.x, y, c.w, c.h, 2.5 * u);
      g.fill();
      ctx.text(labels[i], c.x + c.w / 2, y + c.h / 2, { font: ctx.font('ja', 5.2 * u, 700), color: C.ink, align: 'center', baseline: 'middle', lineHeight: 1.35 });
      g.globalAlpha = 1;
    });
    const c0 = cells[0];
    const c2 = cells[cells.length - 1];
    const sx = M.lerp(c0.x, c2.x, sel / 2);
    const sy = M.lerp(c0.y, c2.y, sel / 2) + M.ease.inCubic(M.progress(t, 9.05, 9.35)) * H * 0.5;
    // Accent-color bar under the selected card (no outline)
    g.fillStyle = C.accent;
    g.globalAlpha = M.clamp(M.spring(t - 7.2, 'default'));
    D.roundRect(g, sx + c0.w * 0.2, sy + c0.h - 3 * u, c0.w * 0.6, 1.4 * u, 0.7 * u);
    g.fill();
    g.globalAlpha = 1;
  }
  // s4 one number
  if (t >= 9.35 && t < 12) {
    const p = inOut(9.7, 12);
    const n = Math.round(M.lerp(1962, 1987, M.clamp(M.spring(t - 9.8, 'default'))));
    ctx.text(String(n), L.cx, L.cy - 4 * u, { font: ctx.font('heading', 22 * u, 800), color: C.paper, align: 'center', baseline: 'middle', alpha: p });
    ctx.text('年に創業', L.cx, L.cy + 12 * u, { font: ctx.font('ja', 5 * u, 700), color: C.support, align: 'center', baseline: 'middle', alpha: p });
    g.fillStyle = C.support;
    const lw = pr.w * 0.5 * M.clamp(M.spring(t - 10.4, 'default')) * p;
    g.fillRect(L.cx - lw / 2, L.cy + 18 * u, lw, 0.8 * u);
  }
  // s5 logo + CTA
  if (t >= 12) {
    const e = M.spring(t - 12.25, 'heavy');
    const logo = ctx.img('@logo');
    const lw = Math.min(L.safe.w * 0.55, 60 * u);
    const lh = lw * (logo.naturalHeight / logo.naturalWidth);
    ctx.image(logo, { x: L.cx - lw / 2, y: L.cy - lh / 2 - 8 * u + (1 - e) * 12 * u, w: lw, h: lh }, { alpha: M.clamp(e) });
    const c = M.spring(t - 12.9, 'default');
    ctx.text('新しい部屋を、一緒に。', L.cx, L.cy + 14 * u + (1 - c) * 5 * u, { font: ctx.font('ja', 5.5 * u, 700), color: C.paper, align: 'center', baseline: 'middle', alpha: M.clamp(c) });
    const d = M.spring(t - 13.3, 'default');
    ctx.text('example.com', L.cx, L.cy + 23 * u, { font: ctx.font('heading', 3.6 * u, 600), color: C.support, align: 'center', baseline: 'middle', alpha: M.clamp(d), letterSpacing: 0.3 * u });
  }
}
