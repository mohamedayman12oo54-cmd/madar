// Static security regression guards for the whole frontend. They read the source and fail the build if
// a dangerous pattern is (re)introduced. Each rule names the attack it blocks.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
  const p = path.join(dir, e.name);
  return e.isDirectory() ? walk(p) : [p];
});
const files = walk(SRC).filter((f) => /\.(jsx?|mjs)$/.test(f) && !/\.test\.(m?js|jsx)$/.test(f));
const read = (f) => fs.readFileSync(f, "utf8");
const rel = (f) => path.relative(SRC, f);
const offenders = (re, allow = []) => files.filter((f) => re.test(read(f)) && !allow.includes(rel(f))).map(rel);

test("no HTML injection sinks anywhere (stored/reflected XSS)", () => {
  assert.deepEqual(offenders(/dangerouslySetInnerHTML|\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML|document\.write\s*\(/), []);
});

test("no dynamic code execution", () => {
  assert.deepEqual(offenders(/\beval\s*\(|new\s+Function\s*\(|setTimeout\(\s*["'`]|setInterval\(\s*["'`]/), []);
});

test("the only direct browser navigation is the billing redirect, which is allow-listed by safeCheckoutUrl", () => {
  assert.deepEqual(offenders(/window\.location\.(assign|replace)\s*\(|location\.href\s*=|window\.open\s*\(/, ["dashboard/BillingPage.jsx"]), []);
  const billing = read(path.join(SRC, "dashboard/BillingPage.jsx"));
  assert.match(billing, /safeCheckoutUrl\(/);
});

test("secrets never come from the client bundle: only VITE_API_URL is read from the environment", () => {
  const vars = new Set();
  for (const f of files) for (const m of read(f).matchAll(/import\.meta\.env\??\.([A-Z_]+)/g)) vars.add(m[1]);
  const allowed = new Set(["VITE_API_URL", "PROD", "DEV"]);
  assert.deepEqual([...vars].filter((v) => !allowed.has(v)), []);
});

test("auth tokens are only touched by lib/api.js (and the parent session by lib/parentApi.js)", () => {
  assert.deepEqual(offenders(/madar\.tokens|TOKEN_KEY/, ["lib/api.js"]), []);
  // quizDraft.js holds only quiz answer indexes (no token / PII) and is cleared on sign-out.
  assert.deepEqual(offenders(/sessionStorage/, ["lib/parentApi.js", "lib/quizDraft.js"]), []);
});

test("nothing logs to the console (tokens, PII and payloads must never reach it)", () => {
  assert.deepEqual(offenders(/\bconsole\.(log|debug|info|dir|trace)\b/), []);
});

test("every router navigation target is a constant, a lookup in a constant table, or a fixed in-app path prefix", () => {
  // react-router 6.x has an open-redirect advisory for user-controlled targets. This proves there are none.
  const bad = [];
  for (const f of files) {
    for (const m of read(f).matchAll(/(?:<(?:Link|NavLink|Navigate)\b[^>]*?\sto=\{([^}]+(?:\}`)?)\})/g)) {
      const expr = m[1].trim();
      const ok = /^`\/[a-z]/.test(expr) || /^(i\.to|to|LOGIN_PATH\[role\] \|\| "\/auth"|ENV_SELECT_PATH\[role\] \|\| "\/auth")$/.test(expr) || /^"\/.*"$/.test(expr);
      if (!ok) bad.push(`${rel(f)}: ${expr}`);
    }
  }
  assert.deepEqual(bad, []);
});

test("production HTML is served with a Content-Security-Policy and without inline scripts or source maps", () => {
  const cfg = read(path.resolve(SRC, "../vite.config.js"));
  assert.match(cfg, /script-src 'self'"/);
  assert.match(cfg, /object-src 'none'/);
  assert.match(cfg, /frame-src https:\/\/www\.youtube-nocookie\.com/);
  assert.match(cfg, /sourcemap: false/);
  assert.doesNotMatch(cfg, /"script-src[^"]*unsafe-(inline|eval)/);
  const html = read(path.resolve(SRC, "../index.html"));
  assert.doesNotMatch(html, /<script(?![^>]*\ssrc=)[^>]*>/);
});

test("the API client never sends ambient credentials and never caches authenticated responses", () => {
  const api = read(path.join(SRC, "lib/api.js"));
  assert.match(api, /credentials: "omit"/);
  assert.match(api, /cache: "no-store"/);
  assert.match(api, /referrerPolicy: "no-referrer"/);
});

test("every <iframe> in the app uses the embed allow-list and a sandbox", () => {
  for (const f of files) {
    const text = read(f);
    for (const m of text.matchAll(/<iframe\s[^>]*>/g)) {
      assert.match(m[0], /sandbox=/, `${rel(f)}: iframe without sandbox`);
      assert.match(m[0], /src=\{url\}/, `${rel(f)}: iframe src must be the validated url`);
    }
    if (/<iframe\s/.test(text)) assert.match(text, /safeEmbedUrl\(/, `${rel(f)}: iframe without safeEmbedUrl`);
  }
});

test("production CSP is generated at build time and never allows script or object loading", () => {
  const cfg = read(path.resolve(SRC, "..", "vite.config.js"));
  assert.match(cfg, /"script-src 'self'"/, "script-src must stay 'self' only");
  const scriptSrc = cfg.match(/"(script-src [^"]*)"/)?.[1] ?? "";
  assert.ok(scriptSrc && !/unsafe-|\*|https?:/.test(scriptSrc), `script-src must not be loosened: ${scriptSrc}`);
  assert.match(cfg, /"object-src 'none'"/);
  assert.match(cfg, /"base-uri 'self'"/);
  assert.match(cfg, /frame-src https:\/\/www\.youtube-nocookie\.com https:\/\/player\.vimeo\.com/);
  assert.match(cfg, /sourcemap: false/, "source maps would publish the original source");
  assert.match(cfg, /apply: "build"/, "the CSP meta tag is for the production build only");
});

test("the team area is gated to the team role and routed lazily", () => {
  const app = read(path.join(SRC, "App.jsx"));
  assert.match(app, /isTeam/);
  assert.match(app, /TeamRoutes/);
  const kb = read(path.join(SRC, "lib", "knowledgeApi.js"));
  assert.match(kb, /const AUTH = \{ auth: true \}/);
  const calls = kb.match(/api\.(get|post|patch|put|delete)\(/g) || [];
  assert.ok(calls.length >= 4, "knowledge API should cover list/create/update/publish/unpublish/remove");
  assert.ok((kb.match(/\bAUTH\b/g) || []).length > calls.length, "every knowledge call must pass AUTH");
});

test("deploy/security-headers.conf (nginx) carries every header of public/_headers", () => {
  const root = path.resolve(SRC, "..");
  const netlify = read(path.join(root, "public", "_headers"));
  const nginx = read(path.join(root, "deploy", "security-headers.conf"));
  const names = [...netlify.matchAll(/^\s{2}(X-Content-Type-Options|X-Frame-Options|Referrer-Policy|Strict-Transport-Security|Cross-Origin-Opener-Policy|Permissions-Policy|Content-Security-Policy):\s*(.+)$/gm)];
  assert.ok(names.length >= 7, "expected the 7 security headers in public/_headers");
  for (const [, name, value] of names) {
    const line = nginx.split("\n").find((l) => l.startsWith("add_header") && l.includes(name));
    assert.ok(line, `${name} missing from deploy/security-headers.conf`);
    assert.ok(line.includes(value.trim()), `${name} value differs between _headers and security-headers.conf`);
  }
});
