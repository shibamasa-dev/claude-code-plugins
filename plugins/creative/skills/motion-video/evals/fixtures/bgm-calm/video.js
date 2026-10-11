// eval (e): with BGM. Compose from a given chord progression and style, then mix with the sound effects. 8 s at 120bpm (one bar = 2 s).
// The visual peak (the columns line up on the bar start at 4 s) and the music's peak (meta.audio.peaks) sit at the same time.
export const meta = {
  title: 'With BGM',
  duration: 8,
  fps: 60,
  aspects: ['16:9'],
  scenes: [
    { id: 's1', start: 0, end: 2, message: 'Quiet opening', screen: 'One primary-color column in the center', motion: { enter: 'The column grows up from the bottom' }, sound: 'BGM (pad and piano) and a thump on the bar start', transition: 'The column splits into two' },
    { id: 's2', start: 2, end: 4, message: 'More elements', screen: 'The columns grow to three', motion: { main: 'Columns stretch on each beat' }, sound: 'whoosh', transition: 'Column heights even out into a peak' },
    { id: 's3', start: 4, end: 6, message: 'Peak (hero entrance)', screen: 'A circle lands on top of the aligned columns', motion: { enter: 'The circle lands with heavy', main: 'Columns bounce on the beat' }, sound: 'Music peak and pop', transition: 'The columns shrink, leaving only the circle' },
    { id: 's4', start: 6, end: 8, message: 'Close', screen: 'The circle stays in the center', motion: { main: 'The circle pulses slowly', exit: 'Hold' }, sound: 'click and the final chord', transition: 'End (hold)' },
  ],
  audio: {
    bpm: 120,
    peaks: [4],
    music: { progression: ['Am', 'F', 'C', 'G'], style: 'calm', seed: 3 },
    cues: [
      { bar: 0, sfx: 'thump', gain: 0.8 },
      { t: 2, sfx: 'whoosh', gain: 0.5 },
      { bar: 2, sfx: 'pop' },
      { t: 6, sfx: 'click', gain: 0.6 },
    ],
  },
};

export function render(ctx, t) {
  const { g, W, H, L, M, D, brand } = ctx;
  const C = brand.colors;
  const u = L.u;
  D.fill(g, W, H, C.paper);
  const n = 3;
  const colW = 9 * u;
  const base = L.safe.y + L.safe.h;
  const spread = M.spring(t - 1.85, 'default'); // s1->s2: from one column to three
  const even = M.spring(t - 3.85, 'default'); // s2->s3: heights even out
  const shrink = M.spring(t - 5.85, 'heavy'); // s3->s4: columns shrink
  const bounce = 1 + 0.06 * Math.sin(Math.PI * 2 * t) * M.progress(t, 4, 4.5) * (1 - shrink);
  for (let i = 0; i < n; i++) {
    const x = L.cx + (i - 1) * 14 * u * spread - colW / 2;
    const rise = M.spring(t - 0.1 - i * 0.12 * spread, 'default');
    const hRaw = (22 + 14 * i + 8 * Math.sin(Math.PI * t + i)) * u;
    const h = Math.max(0, M.lerp(hRaw, 40 * u, even) * rise * bounce * (1 - 0.9 * shrink));
    g.fillStyle = [C.primary, C.secondary, C.accent][i];
    g.globalAlpha = i === 1 ? 1 : Math.min(1, spread * 1.2);
    D.roundRect(g, x, base - h, colW, h, 2 * u);
    g.fill();
  }
  g.globalAlpha = 1;
  // Peak: the circle lands on the bar start at 4 s
  const land = M.spring(t - 4, 'heavy');
  if (t >= 4) {
    const top = base - 40 * u * (1 - 0.9 * shrink);
    const y = M.lerp(L.safe.y - 20 * u, M.lerp(top - 9 * u, L.cy, shrink), land);
    const r = (8 + 1.2 * Math.sin(Math.PI * 2 * (t - 6) * 0.5) * shrink) * u;
    g.fillStyle = C.support;
    g.beginPath();
    g.arc(L.cx, y, r, 0, Math.PI * 2);
    g.fill();
  }
  const s = ctx.scene(t);
  const a = M.spring(t - s.start - 0.1, 'default') * (1 - M.ease.inCubic(M.progress(t, s.end - 0.45, s.end - 0.2)));
  ctx.text(s.id === 's3' ? 'PEAK' : s.id === 's4' ? 'FIN' : 'BGM', L.safe.x, L.safe.y, { font: ctx.font('heading', 6 * u, 800), color: C.ink, alpha: s.id === 's4' ? Math.min(1, a + M.progress(t, 7.5, 8)) : a });
}
