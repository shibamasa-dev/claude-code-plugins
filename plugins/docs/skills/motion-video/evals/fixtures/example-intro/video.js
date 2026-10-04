// eval (a): Example Co.（架空の会社）紹介 15 秒・16:9。ブランドの色・書体・ロゴは brand.json から読む（ここに色を直書きしない）。
// 製品動画の5拍（課題 → 仕組みが組み上がる → できること3つ → 数字1つ → ロゴ＋CTA）の型で組んである。
export const meta = {
  title: 'Example Co. 紹介',
  duration: 15,
  fps: 60,
  aspects: ['16:9'],
  scenes: [
    { id: 's1', start: 0, end: 3, key: 1.6, message: '課題: DX を何から始めればいいか分からない', screen: '左に主色の面、白抜きの大見出し', motion: { enter: '面が下からばねで立ち上がる', main: '見出しが1語ずつ入る', exit: '見出しが先に上へ抜ける' }, narration: 'DX、何から始めますか。', sound: '小節頭で thump', transition: '主色の面が縮んで次のシーンの左柱になる' },
    { id: 's2', start: 3, end: 6, key: 4.8, message: 'AI 駆動で仕組みが組み上がる', screen: '左柱に見出し、右に UI カードが3枚積み上がる', motion: { enter: 'カードが拍ごとに snappy で入る', main: 'カード内のバーが伸びる', exit: 'カードが右へ抜ける' }, narration: 'AI 駆動で、速く・小さく作る。', sound: 'whoosh と pop×3', transition: '左柱が上へ倒れて見出し帯になる' },
    { id: 's3', start: 6, end: 9.5, key: 8.2, message: 'できること3つ', screen: '上に帯、下に3枚の機能カード', motion: { enter: '拍に合わせて1枚ずつ', main: '選択枠が左から右へ移る', exit: 'カードが下へ沈む' }, narration: '導入支援、PMO、開発まで。', sound: 'click×3', transition: '帯が中央の正方形に畳まれる' },
    { id: 's4', start: 9.5, end: 12, key: 11.2, message: '数字1つ: 2025 年設立', screen: '中央の正方形に大きな数字', motion: { enter: '数字がばねで数え上がる', main: '下線が伸びる', exit: '数字が先に消える' }, narration: '2025 年に設立。', sound: 'pop', transition: '正方形が画面全体に広がってロゴの背景になる' },
    { id: 's5', start: 12, end: 15, key: 13.8, message: 'ロゴと CTA', screen: '主色の全面、中央にロゴと一言', motion: { enter: 'ロゴが heavy で着地', main: 'CTA が下から入る', exit: '止め' }, narration: 'はじめの一歩を、一緒に。', sound: '小節頭で thump', transition: '終わり（止め）' },
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

// シーンごとの「面」の位置（レイアウト関数。固定ピクセルを使わない）
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

  // 面: シーンが替わるたびにばねを1本足す（springTrack）。変形はシーン境界の 0.15 秒前から始まる
  const ids = ['s1', 's2', 's3', 's4', 's5'];
  const starts = [0, 3, 6, 9.5, 12];
  const rects = ids.map((id) => panelFor(id, L));
  const track = (k) => M.springTrack(t, rects.map((r, i) => ({ t: i === 0 ? 0 : starts[i] - 0.15, v: r[k] })), 'default');
  const rise = M.spring(t, 'snappy');
  const pr = { x: track('x'), y: track('y') + (1 - rise) * H * 0.4, w: track('w'), h: track('h'), r: track('r') };
  g.fillStyle = C.primary;
  D.roundRect(g, pr.x, pr.y, pr.w, pr.h, pr.r * u);
  g.fill();

  // 文字の出入り: 退場は面の変形より先、入場は変形開始の後
  const inOut = (a, b) => M.spring(t - a, 'default') * (1 - M.ease.inCubic(M.progress(t, b - 0.45, b - 0.2)));

  // s1 課題
  if (t < 3) {
    const words = ['DX、', '何から', '始める？'];
    words.forEach((w, i) => {
      const p = inOut(0.35 + i * 0.25, 3);
      ctx.text(w, pr.x + 7 * u, pr.y + 12 * u + i * 17 * u + (1 - p) * 6 * u, { font: ctx.font('ja', 15 * u, 800), color: C.paper, alpha: p });
    });
  }
  // s2 仕組みが組み上がる
  if (t >= 2.85 && t < 6) {
    const p = inOut(3.15, 6);
    ctx.text('AI 駆動で\n速く、\n小さく', pr.x + 5 * u, pr.y + 8 * u, { font: ctx.font('ja', 8.5 * u, 800), color: C.paper, alpha: p, lineHeight: 1.3, maxWidth: pr.w - 10 * u });
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
  // s3 できること3つ
  if (t >= 5.85 && t < 9.5) {
    const p = inOut(6.15, 9.5);
    ctx.text('できること', pr.x + 5 * u, pr.y + pr.h / 2, { font: ctx.font('ja', 8 * u, 800), color: C.paper, baseline: 'middle', alpha: p });
    const box = { x: L.safe.x, y: pr.y + pr.h + 5 * u, w: L.safe.w, h: L.safe.y + L.safe.h - (pr.y + pr.h + 5 * u) };
    const cells = L.orient === 'portrait' ? L.grid(1, 3, 3, box) : L.grid(3, 1, 3, box);
    const labels = ['DX・AI\n導入支援', 'PMO・\nPM 支援', 'AI 駆動の\n開発'];
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
    // 選択中のカードの下に主張色の帯（枠線は使わない）
    g.fillStyle = C.accent;
    g.globalAlpha = M.clamp(M.spring(t - 7.2, 'default'));
    D.roundRect(g, sx + c0.w * 0.2, sy + c0.h - 3 * u, c0.w * 0.6, 1.4 * u, 0.7 * u);
    g.fill();
    g.globalAlpha = 1;
  }
  // s4 数字1つ
  if (t >= 9.35 && t < 12) {
    const p = inOut(9.7, 12);
    const n = Math.round(M.lerp(2000, 2025, M.clamp(M.spring(t - 9.8, 'default'))));
    ctx.text(String(n), L.cx, L.cy - 4 * u, { font: ctx.font('heading', 22 * u, 800), color: C.paper, align: 'center', baseline: 'middle', alpha: p });
    ctx.text('年に設立', L.cx, L.cy + 12 * u, { font: ctx.font('ja', 5 * u, 700), color: C.support, align: 'center', baseline: 'middle', alpha: p });
    g.fillStyle = C.support;
    const lw = pr.w * 0.5 * M.clamp(M.spring(t - 10.4, 'default')) * p;
    g.fillRect(L.cx - lw / 2, L.cy + 18 * u, lw, 0.8 * u);
  }
  // s5 ロゴ + CTA
  if (t >= 12) {
    const e = M.spring(t - 12.25, 'heavy');
    const logo = ctx.img('@logo');
    const lw = Math.min(L.safe.w * 0.55, 60 * u);
    const lh = lw * (logo.naturalHeight / logo.naturalWidth);
    ctx.image(logo, { x: L.cx - lw / 2, y: L.cy - lh / 2 - 8 * u + (1 - e) * 12 * u, w: lw, h: lh }, { alpha: M.clamp(e) });
    const c = M.spring(t - 12.9, 'default');
    ctx.text('はじめの一歩を、一緒に。', L.cx, L.cy + 14 * u + (1 - c) * 5 * u, { font: ctx.font('ja', 5.5 * u, 700), color: C.paper, align: 'center', baseline: 'middle', alpha: M.clamp(c) });
    const d = M.spring(t - 13.3, 'default');
    ctx.text('example.com', L.cx, L.cy + 23 * u, { font: ctx.font('heading', 3.6 * u, 600), color: C.support, align: 'center', baseline: 'middle', alpha: M.clamp(d), letterSpacing: 0.3 * u });
  }
}
