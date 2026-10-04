// 否定ケース: 前フレームの状態を持ち越す render。check が「失敗」を出せることの確認用（このまま使ってはいけない書き方）。
export const meta = {
  title: 'bad-stateful', duration: 6, fps: 60, aspects: ['16:9'],
  scenes: [{ id: 's1', start: 0, end: 6, message: 'x', screen: 'x', motion: 'x', sound: 'x', transition: 'x' }],
};
let x = 0; // ← 前フレームからの持ち越し（禁止）
export function render(ctx, t) {
  x += 3; // 呼ばれた回数で位置が変わる＝時刻 t だけで決まらない
  ctx.D.fill(ctx.g, ctx.W, ctx.H, '#222');
  ctx.g.fillStyle = '#fff';
  ctx.g.fillRect(x % ctx.W, ctx.H / 2, 40, 40);
}
