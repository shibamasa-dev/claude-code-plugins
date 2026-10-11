// Negative case: a render that uses Math.random. Confirms the harness stops it with an exception while drawing.
export const meta = {
  title: 'bad-random', duration: 2, fps: 30, aspects: ['1:1'],
  scenes: [{ id: 's1', start: 0, end: 2, message: 'x', screen: 'x', motion: 'x', sound: 'x', transition: 'x' }],
};
export function render(ctx, t) {
  ctx.D.fill(ctx.g, ctx.W, ctx.H, '#222');
  ctx.g.fillStyle = '#fff';
  ctx.g.fillRect(Math.random() * ctx.W, ctx.H / 2, 40, 40);
}
