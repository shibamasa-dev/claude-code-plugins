// Negative case: a render that carries state over from the previous frame. Confirms check can report a failure (do not write code like this).
export const meta = {
  title: 'bad-stateful', duration: 6, fps: 60, aspects: ['16:9'],
  scenes: [{ id: 's1', start: 0, end: 6, message: 'x', screen: 'x', motion: 'x', sound: 'x', transition: 'x' }],
};
let x = 0; // <- carried over from the previous frame (forbidden)
export function render(ctx, t) {
  x += 3; // position depends on how many times render was called = not determined by t alone
  ctx.D.fill(ctx.g, ctx.W, ctx.H, '#222');
  ctx.g.fillStyle = '#fff';
  ctx.g.fillRect(x % ctx.W, ctx.H / 2, 40, 40);
}
