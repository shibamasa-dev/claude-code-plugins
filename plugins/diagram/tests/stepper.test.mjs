// Tests for scripts/stepper/stepper.mjs. Run through tests/test-stepper.sh (bash tests/run-all.sh).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { check, build, THEME } from "../scripts/stepper/stepper.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const STEPPER = path.join(here, "../scripts/stepper/stepper.mjs");
const SPEC = path.join(here, "fixtures/checkout-sequence.json");
const SVG_MD = path.join(here, "../skills/one-page-diagram/references/svg.md");
const fixture = () => {
  const spec = JSON.parse(fs.readFileSync(SPEC, "utf8"));
  spec.svg = fs.readFileSync(path.join(here, "fixtures", spec.svgFile), "utf8");
  return spec;
};

test("check accepts the 2-step sequence fixture", () => {
  assert.deepEqual(check(fixture()), []);
});

// One row per refusal reason: how the spec is broken, and the error that names the reason
const refusals = [
  ["no title", (s) => delete s.title, /No title/],
  ["svg not starting with <svg", (s) => (s.svg = `<div>${s.svg}</div>`), /does not start with <svg/],
  ["hard-coded hex color", (s) => (s.svg = s.svg.replace('d="M474,408H298"', 'd="M474,408H298" stroke="#cf222e"')), /color value/],
  ["hard-coded rgb color", (s) => (s.svg = s.svg.replace('d="M474,408H298"', 'd="M474,408H298" stroke="rgb(207,34,46)"')), /color value/],
  ["fewer than 2 steps", (s) => (s.steps = s.steps.slice(0, 1)), /Fewer than 2 steps/],
  ["focus id missing from the svg", (s) => s.steps[1].focus.push("m-refund"), /focus id m-refund/],
  ["here is an arrow, not a box", (s) => { s.steps[0].here = "m-auth-req"; }, /here m-auth-req is not a data-box/],
  ["here not in focus", (s) => { s.steps[0].here = "card"; }, /here card is not in focus/],
  ["mark without here", (s) => delete s.steps[1].here, /mark but no here/],
];
for (const [name, breakIt, reason] of refusals) {
  test(`check refuses: ${name}`, () => {
    const spec = fixture();
    breakIt(spec);
    assert.match(check(spec).join("\n"), reason);
  });
}

test("no CSS rule sets stroke, fill or color on the figure's own elements", () => {
  const css = build(fixture()).match(/<style>([\s\S]*?)<\/style>/)[1];
  const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ sel: m[1].trim(), body: m[2] }));
  const reachesFigure = rules.filter((r) => /data-box|data-arrow|fs-on|fs-hot|fs-here|fs-dim/.test(r.sel));
  assert.ok(reachesFigure.length >= 4, "expected the focus and dim rules to be found");
  for (const r of reachesFigure) assert.doesNotMatch(r.body, /(^|;)\s*(stroke|fill|color)\s*:/, r.sel);
});

test("the figure markup is passed through unchanged", () => {
  const spec = fixture();
  assert.ok(build(spec).includes(spec.svg));
});

test("every step's name and point are in the markup without the script", () => {
  const spec = fixture();
  const staticHtml = build(spec).replace(/<script>[\s\S]*?<\/script>/, "");
  for (const s of spec.steps) {
    assert.ok(staticHtml.includes(s.name), s.name);
    assert.ok(staticHtml.includes(s.point), s.point);
  }
});

test("two fragments on one page get different root ids", () => {
  const a = fixture();
  const b = fixture();
  b.title = "別の図";
  const id = (html) => html.match(/<div class="fs" id="([^"]+)"/)[1];
  assert.notEqual(id(build(a)), id(build(b)));
});

test("--preview writes a light and a dark page", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "stepper-test-"));
  try {
    execFileSync(process.execPath, [STEPPER, SPEC, "--out", path.join(dir, "fragment.html"), "--preview", dir], { stdio: "pipe" });
    assert.match(fs.readFileSync(path.join(dir, "light.html"), "utf8"), /<html[^>]*data-theme="light"/);
    assert.match(fs.readFileSync(path.join(dir, "dark.html"), "utf8"), /<html[^>]*data-theme="dark"/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("the theme values match references/svg.md in both themes", () => {
  const md = fs.readFileSync(SVG_MD, "utf8");
  const block = (start) => {
    const body = md.slice(md.indexOf(start)).match(/\{([^{}]*)\}/)[1];
    return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]+)/g)].map((m) => [m[1], m[2]]));
  };
  assert.deepEqual(block(":root {"), THEME.light);
  assert.deepEqual(block("@media (prefers-color-scheme: dark) {\n    :root {"), THEME.dark);
});
