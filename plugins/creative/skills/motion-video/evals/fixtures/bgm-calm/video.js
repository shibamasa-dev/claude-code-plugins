// eval (e): BGM つき。コード進行とスタイルを指定して作曲させ、効果音と混ぜる。8 秒・120bpm（1小節 2 秒）。
// 映像の山（4 秒の小節頭で柱が揃う）と曲の山（meta.audio.peaks）を同じ時刻に置く。
export const meta = {
  title: 'BGM つき',
  duration: 8,
  fps: 60,
  aspects: ['16:9'],
  scenes: [
    { id: 's1', start: 0, end: 2, message: '静かな立ち上がり', screen: '中央に主色の柱が1本', motion: { enter: '柱が下から伸びる' }, sound: 'BGM（パッドとピアノ）と小節頭の thump', transition: '柱が2本に分かれる' },
    { id: 's2', start: 2, end: 4, message: '要素が増える', screen: '柱が3本に増える', motion: { main: '柱が拍ごとに伸びる' }, sound: 'whoosh', transition: '柱の高さが揃って山になる' },
    { id: 's3', start: 4, end: 6, message: '山（主役の登場）', screen: '揃った柱の上に円が着地する', motion: { enter: '円が heavy で着地', main: '柱が拍で弾む' }, sound: '曲の山・pop', transition: '柱が縮んで円だけが残る' },
    { id: 's4', start: 6, end: 8, message: '締め', screen: '円が中央に残る', motion: { main: '円がゆっくり脈打つ', exit: '止め' }, sound: 'click と最後の和音', transition: '終わり（止め）' },
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
  const spread = M.spring(t - 1.85, 'default'); // s1→s2: 1本から3本へ
  const even = M.spring(t - 3.85, 'default'); // s2→s3: 高さが揃う
  const shrink = M.spring(t - 5.85, 'heavy'); // s3→s4: 柱が縮む
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
  // 山: 4 秒の小節頭で円が着地
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
