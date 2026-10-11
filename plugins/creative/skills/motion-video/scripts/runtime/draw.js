// draw.js — Canvas 2D drawing helpers (browser only). Every function just takes g (the 2D context) and draws; none keeps state.
import { fit } from './motion.js';

// Characters that must not start a line (simplified Japanese line-breaking rules, kinsoku)
const NO_HEAD = '、。，．・：；？！ー）」』】〉》”’ゃゅょっァィゥェォャュョッ';

// Array of lines wrapped at maxWidth. Japanese breaks per character, English per word. Respects \n line breaks.
export function wrapLines(g, text, maxWidth) {
  const out = [];
  for (const para of String(text).split('\n')) {
    const tokens = para.match(/[A-Za-z0-9@#&%$'’\-_.,:/+]+\s*|\s+|./gu) || [''];
    let line = '';
    for (const tk of tokens) {
      const cand = line + tk;
      if (line && g.measureText(cand.trimEnd()).width > maxWidth) {
        if (NO_HEAD.includes(tk[0])) { line = cand; continue; }
        out.push(line.trimEnd());
        line = tk.trimStart();
      } else line = cand;
    }
    out.push(line.trimEnd());
  }
  return out;
}

// Draw text. Returns the drawn bounds { x, y, w, h, lines }.
// opts: font, color, align(left|center|right), baseline(top|middle|bottom), maxWidth, lineHeight(multiplier), letterSpacing(px), alpha
export function text(g, str, x, y, opts = {}) {
  const { font, color = '#fff', align = 'left', baseline = 'top', maxWidth = Infinity, lineHeight = 1.25, letterSpacing = 0, alpha = 1 } = opts;
  g.save();
  if (font) g.font = font;
  g.fillStyle = color;
  g.globalAlpha *= alpha;
  g.textAlign = align;
  g.textBaseline = 'alphabetic';
  if (letterSpacing) g.letterSpacing = `${letterSpacing}px`;
  const size = parseFloat(/(\d+(?:\.\d+)?)px/.exec(g.font)?.[1] ?? '16');
  const lines = wrapLines(g, str, maxWidth);
  const lh = size * lineHeight;
  const total = lh * lines.length;
  let top = y;
  if (baseline === 'middle') top = y - total / 2;
  else if (baseline === 'bottom') top = y - total;
  let w = 0;
  lines.forEach((ln, i) => {
    g.fillText(ln, x, top + i * lh + size * 0.88);
    w = Math.max(w, g.measureText(ln).width);
  });
  g.restore();
  const left = align === 'center' ? x - w / 2 : align === 'right' ? x - w : x;
  return { x: left, y: top, w, h: total, lines };
}

// Build a rounded rectangle as a path (the caller does fill / clip)
export function roundRect(g, x, y, w, h, r = 0) {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2));
  g.beginPath();
  g.moveTo(x + rr, y);
  g.arcTo(x + w, y, x + w, y + h, rr);
  g.arcTo(x + w, y + h, x, y + h, rr);
  g.arcTo(x, y + h, x, y, rr);
  g.arcTo(x, y, x + w, y, rr);
  g.closePath();
}

// Draw an image fitted into a box. opts: fit(contain|cover), radius, alpha. Returns the rectangle actually drawn.
export function image(g, img, box, opts = {}) {
  const { fit: mode = 'contain', radius = 0, alpha = 1 } = opts;
  const iw = img.naturalWidth || img.width;
  const ih = img.naturalHeight || img.height;
  const r = fit(iw, ih, box, mode);
  g.save();
  g.globalAlpha *= alpha;
  if (radius || mode === 'cover') {
    roundRect(g, box.x, box.y, box.w, box.h, radius);
    g.clip();
  }
  g.drawImage(img, r.x, r.y, r.w, r.h);
  g.restore();
  return mode === 'cover' ? box : r;
}

// Fill the background
export function fill(g, W, H, color) {
  g.save();
  g.fillStyle = color;
  g.fillRect(0, 0, W, H);
  g.restore();
}
