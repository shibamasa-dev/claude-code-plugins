// eval (c): export 9:16 -> 1:1 -> 16:9 from the same scene definition (no cropping of a landscape master).
// Built as a loop: position and velocity carry over from the last frame to the first (motion is written as periodic functions of t).
const PERIOD = 4;
export const meta = {
  title: 'Three-aspect loop',
  duration: PERIOD,
  fps: 60,
  loop: true,
  aspects: ['9:16', '1:1', '16:9'],
  scenes: [
    { id: 's1', start: 0, end: 2, message: 'Three aspects from one definition', screen: 'A primary-color rounded tile circles across the diagonal of the screen', motion: { main: 'The tile orbits while support-color dots chase it' }, sound: 'click', transition: 'The tile keeps orbiting into its position in the next scene' },
    { id: 's2', start: 2, end: 4, message: 'Loop back to the start', screen: 'The tile orbits the opposite side', motion: { main: 'Keeps orbiting back to the starting position' }, sound: 'click', transition: 'Connects seamlessly to the first frame (loop)' },
  ],
  audio: { bpm: 120, cues: [{ beat: 0, sfx: 'click' }, { beat: 4, sfx: 'click' }] },
};

export function render(ctx, t) {
  const { g, W, H, L, M, D, brand } = ctx;
  const C = brand.colors;
  const u = L.u;
  const ph = (2 * Math.PI * t) / PERIOD;
  D.fill(g, W, H, C.paper);
  const rx = L.safe.w * 0.3;
  const ry = L.safe.h * 0.3;
  const s = 22 * u;
  // The hero tile
  const x = L.cx + Math.cos(ph) * rx;
  const y = L.cy + Math.sin(ph) * ry;
  g.save();
  g.translate(x, y);
  g.rotate(ph);
  g.fillStyle = C.primary;
  D.roundRect(g, -s / 2, -s / 2, s, s, 4 * u);
  g.fill();
  g.restore();
  // Chasing dots (phase-delayed)
  for (let i = 1; i <= 3; i++) {
    const q = ph - i * 0.35;
    g.fillStyle = [C.support, C.secondary, C.accent][i - 1];
    g.beginPath();
    g.arc(L.cx + Math.cos(q) * rx, L.cy + Math.sin(q) * ry, (5 - i) * u, 0, Math.PI * 2);
    g.fill();
  }
  // Headings (opacity alternates via a periodic function)
  const a = 0.5 + 0.5 * Math.cos(ph);
  ctx.text('ONE SCENE', L.cx, L.safe.y + 4 * u, { font: ctx.font('heading', 7 * u, 800), color: C.ink, align: 'center', alpha: 0.35 + 0.65 * a });
  ctx.text('THREE FRAMES', L.cx, L.safe.y + L.safe.h, { font: ctx.font('heading', 7 * u, 800), color: C.ink, align: 'center', baseline: 'bottom', alpha: 0.35 + 0.65 * (1 - a) });
}
