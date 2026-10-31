/**
 * Installability is easy to break silently — a renamed icon or a missing
 * manifest field just makes the install prompt stop appearing, with no error.
 * These tests assert the contract instead.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PUBLIC = join(ROOT, "public");
const manifest = JSON.parse(readFileSync(join(PUBLIC, "manifest.webmanifest"), "utf8"));

test("manifest carries everything a browser needs to offer installation", () => {
  for (const key of [
    "name",
    "short_name",
    "start_url",
    "scope",
    "display",
    "icons",
    "background_color",
    "theme_color",
  ]) {
    assert.ok(manifest[key], `manifest is missing ${key}`);
  }
  assert.equal(manifest.display, "standalone", "must open without browser chrome");
  assert.equal(manifest.lang, "ar");
  assert.equal(manifest.dir, "rtl");
});

test("manifest ships the icon sizes Android and Chrome require", () => {
  const sizes = manifest.icons.map((i) => i.sizes);
  assert.ok(sizes.includes("192x192"), "192px icon required for installability");
  assert.ok(sizes.includes("512x512"), "512px icon required for the splash screen");
  const maskable = manifest.icons.find((i) => (i.purpose || "").includes("maskable"));
  assert.ok(maskable, "a maskable icon is required or Android crops the logo badly");
});

test("every icon the manifest references actually exists", () => {
  for (const icon of manifest.icons) {
    const path = join(PUBLIC, icon.src.replace(/^\//, "").split("?")[0]);
    assert.ok(existsSync(path), `missing icon file: ${icon.src}`);
  }
  assert.ok(existsSync(join(PUBLIC, "apple-touch-icon.png")), "iOS needs apple-touch-icon.png");
});

test("index.html links the manifest, theme colour and iOS icon", () => {
  const html = readFileSync(join(ROOT, "index.html"), "utf8");
  assert.match(html, /rel="manifest"/);
  assert.match(html, /name="theme-color"/);
  assert.match(html, /rel="apple-touch-icon"/);
  assert.match(html, /viewport-fit=cover/, "needed so the installed app clears the notch");
});

test("the service worker never caches API responses", () => {
  const sw = readFileSync(join(PUBLIC, "sw.js"), "utf8");
  assert.match(sw, /\/api\//, "sw must explicitly exclude the API");
  assert.match(sw, /request\.method !== "GET"/, "writes must never be served from cache");
  assert.match(sw, /url\.origin !== self\.location\.origin/, "cross-origin must be left alone");
});

test("navigations are network-first so a deploy is never masked by cache", () => {
  const sw = readFileSync(join(PUBLIC, "sw.js"), "utf8");
  const nav = sw.slice(sw.indexOf('request.mode === "navigate"'));
  const fetchAt = nav.indexOf("fetch(request)");
  const cacheAt = nav.indexOf("caches.match");
  assert.ok(fetchAt > -1 && cacheAt > -1, "navigation handler must try both");
  assert.ok(fetchAt < cacheAt, "network must be attempted before falling back to cache");
});

test("the service worker is only registered in production builds", () => {
  const main = readFileSync(join(ROOT, "src", "main.jsx"), "utf8");
  assert.match(
    main,
    /import\.meta\.env\?\.PROD/,
    "registering in dev would cache the module graph"
  );
  assert.match(main, /serviceWorker/);
});

test("install prompt respects dismissal and an already-installed app", () => {
  const src = readFileSync(join(ROOT, "src", "components", "InstallPrompt.jsx"), "utf8");
  assert.match(src, /display-mode: standalone/, "must not nag inside the installed app");
  assert.match(src, /beforeinstallprompt/);
  assert.match(src, /appinstalled/, "must hide itself once installed");
  assert.match(src, /iphone\|ipad\|ipod/i, "iOS has no install API and needs instructions");
  assert.match(src, /localStorage/, "dismissal must be remembered");
});
