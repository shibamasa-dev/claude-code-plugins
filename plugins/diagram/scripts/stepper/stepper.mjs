#!/usr/bin/env node
// Walks the reader through several points on one figure: Back / Next switch which elements are emphasised,
// while the layout and every color stay as drawn.
//
// Usage: node stepper.mjs SPEC.json [--out FILE] [--preview DIR]
//
// Ported from the stepper in u-ichi/agent-plugins (plugins/figure-docs/skills/figure-docs/scripts/stepper.mjs,
// https://github.com/u-ichi/agent-plugins), MIT License, Copyright (c) 2026 u-ichi.
// Changes from the original:
// - Emphasis is opacity and stroke width only. No rule sets stroke, fill or color on the figure's own elements,
//   so a colored arrow keeps its color when focused and when dimmed (the original recolored arrows and their labels).
// - Colors are the theme variables of skills/one-page-diagram/references/svg.md, carried in the fragment itself for
//   light and dark, instead of a chat-widget host's variables, so the fragment works inline and in a standalone file.
// - Messages and button labels are in English; `labels` in the spec overrides the buttons.
// - Each fragment finds its own root by a unique id (several fragments on one page no longer pick each other's root),
//   a container that holds the current point fades only its own parts (the original faded the point with it), the
//   step data inlined into the script cannot close the script tag, and the figure's own font sizes are left alone.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

const HEX_OR_RGB = /#[0-9a-fA-F]{3,8}\b|rgba?\(/;

// The theme variables of skills/one-page-diagram/references/svg.md; a test keeps the two in step.
export const THEME = {
  light: { bg: "#ffffff", ink: "#1f2328", muted: "#656d76", line: "#8c959f", box: "#f6f8fa", accent: "#0969da", pill: "#eaeef2", badge: "#0969da", "badge-ink": "#ffffff" },
  dark: { bg: "#0d1117", ink: "#e6edf3", muted: "#8d96a0", line: "#6e7681", box: "#161b22", accent: "#4493f8", pill: "#21262d", badge: "#4493f8", "badge-ink": "#0d1117" },
};

export function check(spec) {
  const errors = [];
  const svg = spec.svg ?? "";
  if (!spec.title) errors.push("No title.");
  if (!svg.trim().startsWith("<svg")) errors.push("svg does not start with <svg.");
  if (HEX_OR_RGB.test(svg))
    errors.push("svg contains a color value (#... or rgb(...)). Set colors through classes that use the theme variables. An id reference such as url(#ab1-arrow) also matches: rename the id so no 3+ hex characters follow the #.");
  if (/<script\b|\son[a-z]+\s*=\s*["']/i.test(svg)) errors.push("svg contains a script element or an event attribute (onload=...). The figure is markup only; the stepper adds the script.");
  const boxes = [...svg.matchAll(/data-box="([^"]+)"/g)].map((m) => m[1]);
  const arrows = [...svg.matchAll(/data-arrow="([^"]+)"/g)].map((m) => m[1]);
  const ids = new Set([...boxes, ...arrows]);
  const steps = spec.steps ?? [];
  if (steps.length < 2) errors.push("Fewer than 2 steps. With one point, draw one figure without the stepper.");
  steps.forEach((s, k) => {
    const n = k + 1;
    if (!s.name) errors.push(`Step ${n} has no name.`);
    if (!s.point) errors.push(`Step ${n} has no point (the one-line conclusion under the figure).`);
    const focus = s.focus ?? [];
    if (focus.length === 0) errors.push(`Step ${n} has an empty focus.`);
    for (const id of focus) if (!ids.has(id)) errors.push(`Step ${n}: focus id ${id} is not a data-box or data-arrow in the svg.`);
    if (s.here && !boxes.includes(s.here)) errors.push(`Step ${n}: here ${s.here} is not a data-box in the svg.`);
    if (s.here && !focus.includes(s.here)) errors.push(`Step ${n}: here ${s.here} is not in focus.`);
    if (s.mark && !s.here) errors.push(`Step ${n} has a mark but no here box to put it on.`);
  });
  return errors;
}

const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const vars = (t) => Object.entries(t).map(([k, v]) => `--${k}:${v}`).join(";");
// Which elements to fade for one step. Runs in the browser (inlined into the fragment's script) and in the tests,
// so it uses only children and getAttribute. A tagged element outside the focus fades as a whole, unless it contains
// a focused element: then only its own untagged parts fade, so the focused element inside stays at full strength.
// Tagged elements inside a faded whole are not faded again (opacity would compound). Untagged elements outside any
// tagged one (lifelines, legend) never fade.
export function dimTargets(root, focus) {
  const tagOf = (el) => (el.getAttribute ? el.getAttribute("data-box") ?? el.getAttribute("data-arrow") : null);
  const kids = (el) => Array.from(el.children || []);
  const hasTag = (el) => kids(el).some((c) => tagOf(c) != null || hasTag(c));
  const hasFocus = (el) => kids(el).some((c) => focus.includes(tagOf(c)) || hasFocus(c));
  const out = [];
  const own = (el) => {
    for (const c of kids(el)) {
      if (tagOf(c) != null) continue;
      if (hasTag(c)) own(c);
      else out.push(c);
    }
  };
  const walk = (el) => {
    for (const c of kids(el)) {
      const t = tagOf(c);
      if (t == null || focus.includes(t)) {
        walk(c);
      } else if (hasFocus(c)) {
        own(c);
        walk(c);
      } else {
        out.push(c);
      }
    }
  };
  walk(root);
  return out;
}

export function build(spec) {
  // Unique per fragment, so two fragments on one page (even of the same spec) each find their own root
  const id = `fs-${randomUUID().slice(0, 8)}`;
  const labels = { back: "Back", next: "Next", all: "Whole figure", ...spec.labels };
  const steps = spec.steps.map((s) => ({ focus: s.focus, here: s.here ?? null, mark: s.mark ?? null }));
  const list = spec.steps
    .map((s, k) => `<li data-step="${k}"><button type="button">${k + 1} ${esc(s.name)}</button><span class="pt">${esc(s.point)}</span></li>`)
    .join("");
  const source = spec.source ? `<div class="fs-src"><b>${esc(spec.source.label)}</b>${esc(spec.source.text)}</div>` : "";
  const lead = spec.lead ? `<div class="fs-lead">${esc(spec.lead)}</div>` : "";
  const shapes = ":is(rect,polygon,circle,ellipse,path):not(.fs-badge-bg)";
  return `<style>
.fs,.fs-page{${vars(THEME.light)}}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) :is(.fs,.fs-page){${vars(THEME.dark)}}}
:root[data-theme="dark"] :is(.fs,.fs-page){${vars(THEME.dark)}}
.fs{font-family:system-ui,-apple-system,"Segoe UI","Hiragino Sans","Noto Sans JP",sans-serif;color:var(--ink);background:var(--bg);padding:12px}
.fs svg{color:var(--ink);display:block;max-width:100%;height:auto;margin:6px auto}
.fs h3{margin:0 0 2px;font-size:16px}
.fs-lead{font-size:12px;color:var(--muted);margin-bottom:6px}
.fs-src{font-size:13px;margin-bottom:8px}.fs-src b{font-size:11px;font-weight:600;border:1px solid var(--line);border-radius:8px;padding:1px 6px;margin-right:6px;color:var(--muted)}
.fs ol{list-style:none;margin:0 0 4px;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.fs button{font:inherit;font-size:12px;border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:12px;padding:3px 10px;cursor:pointer}
.fs li.on button{background:var(--box);font-weight:600;border-color:var(--ink)}
.fs .pt{display:block;font-size:12px;color:var(--muted);margin:2px 0 0 4px}
.fs.js .pt{display:none}
.fs svg .fs-pill{fill:var(--pill);stroke:var(--line);stroke-width:.5px}
.fs svg .fs-badge-bg{fill:var(--badge);stroke:none}
.fs svg .fs-badge{fill:var(--badge-ink);font-size:11px;font-weight:700}
.fs svg [data-box],.fs svg [data-arrow]{transition:opacity .2s}
.fs.fs-step svg .fs-dim{opacity:.3}
.fs.fs-step svg [data-arrow].fs-hot :is(path,line,polyline){stroke-width:2px}
.fs.fs-step svg [data-arrow].fs-hot text{font-weight:700}
.fs.fs-step svg [data-box].fs-on ${shapes}{stroke-width:2.5px}
.fs.fs-step svg [data-box].fs-here ${shapes}{stroke-width:3.5px}
.fs-point{text-align:center;font-weight:700;font-size:16px;min-height:22px;margin-top:4px}
.fs-nav{display:none;justify-content:center;align-items:center;gap:6px;margin-top:6px;font-size:12px;color:var(--muted)}
.fs.js .fs-nav{display:flex}
</style>
<div class="fs" id="${id}">
<h3>${esc(spec.title)}</h3>${lead}${source}
<ol>${list}</ol>
${spec.svg}
<div class="fs-point"></div>
<div class="fs-nav"><button type="button" data-go="-1">${esc(labels.back)}</button><span class="fs-pos"></span><button type="button" data-go="1">${esc(labels.next)}</button><button type="button" data-all>${esc(labels.all)}</button></div>
</div>
<script>
(()=>{const root=document.getElementById(${JSON.stringify(id)});if(!root||root.classList.contains("js"))return;root.classList.add("js");
const steps=${JSON.stringify(steps).replace(/</g, "\\u003c")};const svg=root.querySelector("svg");const items=[...root.querySelectorAll("li[data-step]")];
const NS="http://www.w3.org/2000/svg";let i=0,all=false;
${dimTargets.toString()}
svg.querySelectorAll("[data-arrow] text").forEach(t=>{const b=t.getBBox();const r=document.createElementNS(NS,"rect");r.setAttribute("class","fs-pill");r.setAttribute("x",b.x-5);r.setAttribute("y",b.y-2);r.setAttribute("width",b.width+10);r.setAttribute("height",b.height+4);r.setAttribute("rx",4);t.before(r);});
function draw(){root.classList.toggle("fs-step",!all);items.forEach((li,k)=>li.classList.toggle("on",!all&&k===i));
svg.querySelectorAll(".fs-badge,.fs-badge-bg").forEach(e=>e.remove());
svg.querySelectorAll(".fs-dim").forEach(e=>e.classList.remove("fs-dim"));
if(!all)dimTargets(svg,steps[i].focus).forEach(e=>e.classList.add("fs-dim"));
svg.querySelectorAll("[data-box],[data-arrow]").forEach(g=>{g.classList.remove("fs-on","fs-hot","fs-here");if(all)return;
const isBox=g.dataset.box!==undefined;const id=isBox?g.dataset.box:g.dataset.arrow;if(!steps[i].focus.includes(id))return;
g.classList.add(isBox?"fs-on":"fs-hot");
if(isBox&&id===steps[i].here){g.classList.add("fs-here");if(steps[i].mark){const b=g.getBBox();const t=document.createElementNS(NS,"text");t.setAttribute("class","fs-badge");t.setAttribute("x",b.x+6);t.setAttribute("y",b.y+b.height+15);t.textContent=steps[i].mark;g.appendChild(t);const w=t.getBBox().width;const bg=document.createElementNS(NS,"rect");bg.setAttribute("class","fs-badge-bg");bg.setAttribute("x",b.x);bg.setAttribute("y",b.y+b.height+3);bg.setAttribute("width",w+12);bg.setAttribute("height",16);bg.setAttribute("rx",3);t.before(bg);}}});
root.querySelector(".fs-point").textContent=all?"":items[i].querySelector(".pt").textContent;
root.querySelector(".fs-pos").textContent=all?${JSON.stringify(labels.all)}:(i+1)+" / "+steps.length;}
items.forEach((li,k)=>li.querySelector("button").onclick=()=>{i=k;all=false;draw();});
root.querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>{all=false;i=Math.min(steps.length-1,Math.max(0,i+(+b.dataset.go)));draw();});
root.querySelector("[data-all]").onclick=()=>{all=true;draw();};draw();})();
</script>`;
}

// A page to look at the fragment outside its host, with the theme fixed to light or dark
export function preview(fragment, theme) {
  return `<!doctype html><html lang="en" data-theme="${theme}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="${theme}"><title>stepper preview (${theme})</title>
<body class="fs-page" style="margin:0;padding:16px;max-width:960px;background:var(--bg)">${fragment}</body></html>`;
}

const isMain = () => {
  try {
    return fs.realpathSync(fileURLToPath(import.meta.url)) === fs.realpathSync(process.argv[1]);
  } catch {
    return false;
  }
};

if (isMain()) {
  const [file, ...rest] = process.argv.slice(2);
  if (!file) {
    console.error("Usage: node stepper.mjs SPEC.json [--out FILE] [--preview DIR]");
    process.exit(2);
  }
  const opt = (name) => {
    const k = rest.indexOf(name);
    return k < 0 ? null : rest[k + 1];
  };
  const spec = JSON.parse(fs.readFileSync(file, "utf8"));
  if (spec.svgFile) spec.svg = fs.readFileSync(path.resolve(path.dirname(file), spec.svgFile), "utf8");
  const errors = check(spec);
  if (errors.length) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  const html = build(spec);
  if (opt("--out")) fs.writeFileSync(opt("--out"), html);
  else process.stdout.write(html);
  const dir = opt("--preview");
  if (dir) {
    fs.mkdirSync(dir, { recursive: true });
    for (const theme of Object.keys(THEME)) fs.writeFileSync(path.join(dir, `${theme}.html`), preview(html, theme));
  }
  console.error(`${Buffer.byteLength(html)} bytes. Points for the reply text: ${spec.title} (${spec.steps.length} points: ${spec.steps.map((s) => s.name).join(", ")})`);
}
