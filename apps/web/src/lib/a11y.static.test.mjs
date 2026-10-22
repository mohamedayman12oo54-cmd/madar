// Accessibility regression guards that can run without a browser.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const css = fs.readFileSync(path.join(SRC, "index.css"), "utf8");
const tok = (name) => css.match(new RegExp(`--${name}:\\s*(#[0-9A-Fa-f]{6})`))[1];

const lum = (h) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

test("every text colour token meets WCAG AA (4.5:1) on every surface it can sit on", () => {
  const surfaces = ["cream", "surface", "panel", "bg-2"].map((n) => [n, tok(n)]);
  for (const text of ["ink", "muted", "soft", "navy"]) {
    for (const [name, bg] of surfaces) {
      assert.ok(ratio(tok(text), bg) >= 4.5, `--${text} on --${name} is ${ratio(tok(text), bg).toFixed(2)}:1`);
    }
  }
});

test("status colours used for chips and notices meet AA on the cream surface", () => {
  for (const c of ["#2A7352", "#8a5a12", "#b4442f"]) assert.ok(ratio(c, tok("cream")) >= 4.5, c);
});

test("a visible keyboard focus indicator exists globally and no control removes it without a replacement", () => {
  // Whitespace-tolerant on purpose: the stylesheets are Prettier-formatted, so a compact-only pattern
  // would silently match nothing and the guard would pass while checking nothing.
  assert.match(css, /:focus-visible\s*\{\s*outline:\s*2px solid/);
  // Interactive controls only. Containers that receive focus programmatically (dialog panels, headings
  // moved to for screen readers, the video frame) are not keyboard targets and are exempt by design.
  const CONTROL = /\b(input|select|textarea|button)\b|\.inp\b|\.channel-opt\b|\.otp\b/;
  for (const f of ["dashboard/dashboard.css", "auth/auth.css", "student/student.css", "student/quiz.css"]) {
    const text = fs.readFileSync(path.join(SRC, f), "utf8");
    for (const m of text.matchAll(/([^{}]+):focus(?:-visible)?\s*\{([^}]*outline:\s*none[^}]*)\}/g)) {
      if (!CONTROL.test(m[1])) continue;
      const base = m[1].trim().split(",").pop().trim().split(" ")[0].replace(/[.]/g, "\\.");
      // A replacement is a ring on the control itself, or on a wrapper via :focus-within.
      const hasReplacement =
        /box-shadow|border-color/.test(m[2]) || new RegExp(`${base}[^{}]*:focus-within`).test(text);
      assert.ok(hasReplacement, `${f}: ${m[1].trim()} removes the outline without a replacement`);
    }
  }
});

test("the document declares Arabic + RTL and a viewport that does not block zoom", () => {
  const html = fs.readFileSync(path.resolve(SRC, "../index.html"), "utf8");
  assert.match(html, /<html lang="ar" dir="rtl">/);
  assert.doesNotMatch(html, /user-scalable\s*=\s*no|maximum-scale\s*=\s*1(\.0)?\b/);
});
