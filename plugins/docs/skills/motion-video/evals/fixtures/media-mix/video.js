// eval (b): 画像素材（スクショ相当の PNG）と実写クリップ（mp4）を両方載せる。30fps。
// assets/screenshot.png と clips/demo.mp4 は evals/run_evals.mjs が ffmpeg で生成する（バイナリをリポに置かない）。
export const meta = {
  title: '画面とクリップ',
  duration: 5,
  fps: 30,
  aspects: ['16:9'],
  assets: { shot: 'assets/screenshot.png' },
  clips: { demo: { src: 'clips/demo.mp4', fps: 30 } },
  scenes: [
    { id: 's1', start: 0, end: 1.5, message: '実際の管理画面', screen: '中央に画面のスクショが枠付きで立ち上がる', motion: { enter: 'スクショが default で拡大しながら入る', exit: '見出しが先に上へ抜ける' }, sound: 'thump', transition: 'スクショの枠が左へ縮んで左柱になる' },
    { id: 's2', start: 1.5, end: 3.5, message: '操作している様子', screen: '右にクリップ、左に縮んだスクショ', motion: { enter: 'クリップ枠が snappy で入る', main: 'クリップが再生される' }, sound: 'whoosh', transition: '2枚が同じ大きさに揃って横並びになる' },
    { id: 's3', start: 3.5, end: 5, message: '画面と操作を並べて見せる', screen: '2分割（横長は左右・縦長は上下）', motion: { main: 'クリップは再生を続ける', exit: '止め' }, sound: 'pop', transition: '終わり（止め）' },
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

  // スクショの枠: full → narrow → left（ターゲットが変わるたびにばねを1本足す）
  const tr = (k) => M.springTrack(t, [{ t: 0, v: full[k] }, { t: 1.35, v: narrow[k] }, { t: 3.35, v: left[k] }], 'default');
  const shotBox = { x: tr('x'), y: tr('y'), w: tr('w'), h: tr('h') };
  const e = M.spring(t - 0.1, 'default');
  g.globalAlpha = M.clamp(e * 1.5);
  ctx.image(ctx.img('shot'), shotBox, { fit: 'cover', radius: 2 * u });
  g.globalAlpha = 1;

  if (t < 1.5) {
    const p = M.spring(t - 0.3, 'default') * (1 - M.ease.inCubic(M.progress(t, 1.05, 1.3)));
    ctx.text('実際の管理画面', L.safe.x, L.safe.y, { font: ctx.font('ja', 6 * u, 800), color: C.paper, alpha: p });
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
    ctx.text('画面 × 操作', L.cx, L.safe.y + L.safe.h, { font: ctx.font('ja', 4.5 * u, 700), color: C.support, align: 'center', baseline: 'bottom', alpha: M.clamp(p) });
  }
}
