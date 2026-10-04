// eval (c): 同じシーン定義から 9:16 → 1:1 → 16:9 を書き出す（横のマスターを切り抜かない）。
// ループ作品として作ってあり、最後のコマから最初のコマへ位置も速度もつながる（動きを t の周期関数で書く）。
const PERIOD = 4;
export const meta = {
  title: '3画角ループ',
  duration: PERIOD,
  fps: 60,
  loop: true,
  aspects: ['9:16', '1:1', '16:9'],
  scenes: [
    { id: 's1', start: 0, end: 2, message: '1つの定義から3画角', screen: '主色の角丸タイルが画面の対角を回る', motion: { main: 'タイルが周回し、補助色の点が追いかける' }, sound: 'click', transition: 'タイルがそのまま次のシーンの位置へ回り込む' },
    { id: 's2', start: 2, end: 4, message: 'ループで最初に戻る', screen: 'タイルが反対側を回る', motion: { main: '周回を続けて最初の位置へ戻る' }, sound: 'click', transition: '最初のコマへ連続してつながる（ループ）' },
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
  // 主役のタイル
  const x = L.cx + Math.cos(ph) * rx;
  const y = L.cy + Math.sin(ph) * ry;
  g.save();
  g.translate(x, y);
  g.rotate(ph);
  g.fillStyle = C.primary;
  D.roundRect(g, -s / 2, -s / 2, s, s, 4 * u);
  g.fill();
  g.restore();
  // 追いかける点（位相を遅らせる）
  for (let i = 1; i <= 3; i++) {
    const q = ph - i * 0.35;
    g.fillStyle = [C.support, C.secondary, C.accent][i - 1];
    g.beginPath();
    g.arc(L.cx + Math.cos(q) * rx, L.cy + Math.sin(q) * ry, (5 - i) * u, 0, Math.PI * 2);
    g.fill();
  }
  // 見出し（周期関数で濃さが入れ替わる）
  const a = 0.5 + 0.5 * Math.cos(ph);
  ctx.text('ONE SCENE', L.cx, L.safe.y + 4 * u, { font: ctx.font('heading', 7 * u, 800), color: C.ink, align: 'center', alpha: 0.35 + 0.65 * a });
  ctx.text('THREE FRAMES', L.cx, L.safe.y + L.safe.h, { font: ctx.font('heading', 7 * u, 800), color: C.ink, align: 'center', baseline: 'bottom', alpha: 0.35 + 0.65 * (1 - a) });
}
