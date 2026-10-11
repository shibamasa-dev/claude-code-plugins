// eval (b): uses both an image asset (a screenshot-like PNG) and a live-action clip (mp4). 30fps.
// assets/screenshot.png and clips/demo.mp4 are generated with ffmpeg by evals/run_evals.mjs (no binaries in the repo).
export const meta = {
  title: 'Screen and clip',
  duration: 5,
  fps: 30,
  aspects: ['16:9'],
  assets: { shot: 'assets/screenshot.png' },
  clips: { demo: { src: 'clips/demo.mp4', fps: 30 } },
  scenes: [
    { id: 's1', start: 0, end: 1.5, message: 'The actual admin screen', screen: 'A framed screenshot rises in the center', motion: { enter: 'The screenshot scales up into place with default', exit: 'The heading exits upward first' }, sound: 'thump', transition: 'The screenshot frame shrinks to the left into a left column' },
    { id: 's2', start: 1.5, end: 3.5, message: 'Someone using it', screen: 'Clip on the right, shrunken screenshot on the left', motion: { enter: 'The clip frame enters with snappy', main: 'The clip plays' }, sound: 'whoosh', transition: 'The two settle to the same size, side by side' },
    { id: 's3', start: 3.5, end: 5, message: 'Show the screen and the interaction together', screen: 'Two-way split (side by side in landscape, stacked in portrait)', motion: { main: 'The clip keeps playing', exit: 'Hold' }, sound: 'pop', transition: 'End (hold)' },
  ],
  audio: { bpm: 120, cues: [{ bar: 0, sfx: 'thump' }, { t: 1.5, sfx: 'whoosh', gain: 0.6 }, { t: 3.5, sfx: 'pop' }] },
};

export function render(ctx, t) {
  const { g, W, H, L, M, D, brand } = ctx;
  const C = brand.colors;
  const u = L.u;
  D.fill(g, W, H, C.ink);
  const [left, right] = L.split(4);
  const full = { x: L.safe.x + L.safe.w * 0.12, y: L.safe.y + 10 * u, w: L.safe.w * 0.76, h: L.safe.h - 10 * u };
  const narrow = L.orient === 'portrait' ? { ...left, h: left.h * 0.8 } : { ...left, w: left.w * 0.8, x: left.x };

  // Screenshot frame: full -> narrow -> left (add one spring each time the target changes)
  const tr = (k) => M.springTrack(t, [{ t: 0, v: full[k] }, { t: 1.35, v: narrow[k] }, { t: 3.35, v: left[k] }], 'default');
  const shotBox = { x: tr('x'), y: tr('y'), w: tr('w'), h: tr('h') };
  const e = M.spring(t - 0.1, 'default');
  g.globalAlpha = M.clamp(e * 1.5);
  ctx.image(ctx.img('shot'), shotBox, { fit: 'cover', radius: 2 * u });
  g.globalAlpha = 1;

  if (t < 1.5) {
    const p = M.spring(t - 0.3, 'default') * (1 - M.ease.inCubic(M.progress(t, 1.05, 1.3)));
    ctx.text('The actual admin screen', L.safe.x, L.safe.y, { font: ctx.font('ja', 6 * u, 800), color: C.paper, alpha: p });
  }
  if (t >= 1.35) {
    const k = M.spring(t - 1.5, 'snappy');
    const box = { x: right.x + (1 - k) * 15 * u, y: right.y, w: right.w, h: right.h };
    g.globalAlpha = M.clamp(k * 1.5);
    ctx.image(ctx.clip('demo', t - 1.5), box, { fit: 'cover', radius: 2 * u });
    g.globalAlpha = 1;
  }
  if (t >= 3.5) {
    const p = M.spring(t - 3.6, 'default');
    ctx.text('Screen × Interaction', L.cx, L.safe.y + L.safe.h, { font: ctx.font('ja', 4.5 * u, 700), color: C.support, align: 'center', baseline: 'bottom', alpha: M.clamp(p) });
  }
}
