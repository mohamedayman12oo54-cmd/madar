// VideoPlayer behaviour test: real component, real DOM (jsdom), mocked <video>.
// Covers the student-facing controls: ±5s skip, speed popup, quality popup.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", { url: "http://localhost:5173/learn", pretendToBeVisual: true });
const w = dom.window;
for (const k of ["window", "document", "HTMLElement", "Element", "Node", "MutationObserver", "getComputedStyle", "requestAnimationFrame", "cancelAnimationFrame", "CustomEvent", "Event", "KeyboardEvent", "localStorage", "sessionStorage"]) {
  Object.defineProperty(globalThis, k, { value: k === "window" ? w : w[k], configurable: true, writable: true });
}
Object.defineProperty(globalThis, "navigator", { value: w.navigator, configurable: true });
for (const k of Object.getOwnPropertyNames(w)) {
  if (!(k in globalThis) && /^[A-Z]/.test(k)) Object.defineProperty(globalThis, k, { value: w[k], configurable: true, writable: true });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// jsdom has no media engine: give <video> a tiny fake one.
const proto = w.HTMLMediaElement.prototype;
const state = new WeakMap();
const st = (el) => { if (!state.has(el)) state.set(el, { t: 0, paused: true, rate: 1 }); return state.get(el); };
Object.defineProperty(proto, "currentTime", { configurable: true, get() { return st(this).t; }, set(v) { st(this).t = v; } });
Object.defineProperty(proto, "paused", { configurable: true, get() { return st(this).paused; } });
Object.defineProperty(proto, "playbackRate", { configurable: true, get() { return st(this).rate; }, set(v) { st(this).rate = v; } });
Object.defineProperty(proto, "duration", { configurable: true, get() { return 100; } });
proto.play = function () { st(this).paused = false; this.dispatchEvent(new w.Event("play")); return Promise.resolve(); };
proto.pause = function () { st(this).paused = true; this.dispatchEvent(new w.Event("pause")); };

const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { createServer } = await import("vite");
const vite = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error", optimizeDeps: { noDiscovery: true } });
const { default: VideoPlayer } = await vite.ssrLoadModule("/src/components/VideoPlayer.jsx");
test.after(() => vite.close());

const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
const $ = (sel) => document.querySelector(sel);
const byLabel = (label) => [...document.querySelectorAll("button")].find((b) => b.getAttribute("aria-label") === label);
const byText = (txt) => [...document.querySelectorAll("button")].find((b) => b.textContent.trim().startsWith(txt));
const click = (el) => act(async () => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); });
const key = (el, k) => act(async () => { el.dispatchEvent(new w.KeyboardEvent("keydown", { key: k, bubbles: true })); });
const loaded = (v) => act(async () => { v.dispatchEvent(new w.Event("loadedmetadata")); });

const roots = [];
test.afterEach(async () => { while (roots.length) { const r = roots.pop(); await act(async () => r.unmount()); } });

async function mount({ qualities = [], ticketFor } = {}) {
  document.body.innerHTML = "<div id='root'></div>";
  const calls = [];
  const tf = ticketFor || (async (id, q) => { calls.push([id, q]); return { ticket: q ? `T-${q}` : "T-auto", qualities }; });
  const root = createRoot($("#root"));
  roots.push(root);
  await act(async () => { root.render(React.createElement(VideoPlayer, { itemId: 7, ticketFor: tf })); });
  await flush();
  const v = $("video");
  await loaded(v);
  return { v, calls, root };
}

test("skip buttons move the video exactly 5 seconds and clamp at the start", async () => {
  const { v } = await mount();
  v.currentTime = 20;
  await click(byLabel("تقديم 5 ثواني"));
  assert.equal(v.currentTime, 25);
  await click(byLabel("رجوع 5 ثواني"));
  await click(byLabel("رجوع 5 ثواني"));
  assert.equal(v.currentTime, 15);
  v.currentTime = 3;
  await click(byLabel("رجوع 5 ثواني"));
  assert.equal(v.currentTime, 0, "never negative");
  v.currentTime = 98;
  await click(byLabel("تقديم 5 ثواني"));
  assert.equal(v.currentTime, 100, "never past the end");
});

test("keyboard arrows still seek 5s (mirrored for RTL)", async () => {
  const { v } = await mount();
  v.currentTime = 30;
  await key($(".player-frame"), "ArrowLeft");
  assert.equal(v.currentTime, 35);
  await key($(".player-frame"), "ArrowRight");
  assert.equal(v.currentTime, 30);
});

test("speed button opens a popup; choosing a speed applies it and closes the popup", async () => {
  const { v } = await mount();
  assert.equal($(".pc-popup"), null, "closed by default");
  await click(byText("عادي"));
  const opts = [...document.querySelectorAll(".pc-popup .pc-opt")].map((b) => b.textContent.trim());
  assert.deepEqual(opts, ["0.5×", "0.75×", "عادي", "1.25×", "1.5×", "1.75×", "2×"]);
  await click([...document.querySelectorAll(".pc-opt")].find((b) => b.textContent.includes("1.5×")));
  assert.equal(v.playbackRate, 1.5);
  assert.equal($(".pc-popup"), null, "popup closes after choosing");
  assert.match(byText("1.5×").textContent, /1\.5×/, "button shows current speed");
  await click(byText("1.5×"));
  assert.ok($(".pc-opt.is-active").textContent.includes("1.5×"), "current speed is marked");
});

test("quality popup lists the API's qualities; with none it says so", async () => {
  const none = await mount();
  await click(byText("تلقائي"));
  assert.deepEqual([...document.querySelectorAll(".pc-opt")].map((b) => b.textContent.trim()), ["تلقائي"]);
  assert.ok($(".pc-popup-note"));
  await act(async () => none.root.unmount());

  await mount({ qualities: [{ label: "480p", height: 480 }, { label: "360p", height: 360 }] });
  await click(byText("تلقائي"));
  assert.deepEqual([...document.querySelectorAll(".pc-opt")].map((b) => b.textContent.trim()), ["تلقائي", "480p", "360p"]);
  assert.equal($(".pc-popup-note"), null);
});

test("switching quality fetches a new ticket, keeps position, play state and speed", async () => {
  const { v, calls } = await mount({ qualities: [{ label: "480p", height: 480 }, { label: "360p", height: 360 }] });
  const before = v.getAttribute("src");
  await click(byText("عادي")); await click([...document.querySelectorAll(".pc-opt")].find((b) => b.textContent.includes("2×")));
  v.currentTime = 42;
  await act(async () => { await v.play(); });
  await click(byText("تلقائي"));
  await click([...document.querySelectorAll(".pc-opt")].find((b) => b.textContent.trim() === "360p"));
  await flush();
  assert.deepEqual(calls.at(-1), [7, "360p"]);
  assert.notEqual(v.getAttribute("src"), before);
  assert.match(v.getAttribute("src"), /t=T-360p/);
  v.currentTime = 0; st(v).paused = true;               // what a fresh source looks like
  await loaded(v);
  assert.equal(v.currentTime, 42, "resumes at the same second");
  assert.equal(v.paused, false, "was playing, keeps playing");
  assert.equal(v.playbackRate, 2, "speed survives the switch");
  assert.ok(byText("360p"), "button shows the chosen quality");
});

test("a failed quality switch keeps the current video playing and shows a notice", async () => {
  let n = 0;
  const { v } = await mount({ ticketFor: async (id, q) => { if (q) throw new Error("boom"); n++; return { ticket: "T", qualities: [{ label: "360p", height: 360 }] }; } });
  await click(byText("تلقائي"));
  await click([...document.querySelectorAll(".pc-opt")].find((b) => b.textContent.trim() === "360p"));
  await flush();
  assert.ok($(".player-notice"), "notice shown");
  assert.equal($(".player-state.err"), null, "player is not torn down");
  assert.equal($("video"), v, "same video element stays mounted");
  assert.match(v.getAttribute("src"), /t=T$/, "still on the original source");
});

test("choosing the already-selected quality does nothing", async () => {
  const { calls } = await mount({ qualities: [{ label: "360p", height: 360 }] });
  const n = calls.length;
  await click(byText("تلقائي"));
  await click([...document.querySelectorAll(".pc-opt")].find((b) => b.textContent.trim() === "تلقائي"));
  assert.equal(calls.length, n);
});

// ---------- auto-hiding overlay ----------
const shown = () => $(".player-controls").classList.contains("is-shown");
const tick = (ms) => act(async () => { test.mock.timers.tick(ms); });
const ev = (el, type, init = {}) => act(async () => { el.dispatchEvent(new w.MouseEvent(type, { bubbles: true, ...init })); });
async function mountMocked(opts) {
  const m = await mount(opts);
  test.mock.timers.enable({ apis: ["setTimeout"] });
  await ev($(".player-frame"), "mousemove");           // (re)arm the timer under the mock clock
  return m;
}
test.afterEach(() => test.mock.timers.reset());

test("controls are visible on hover and fade after exactly 5 seconds of stillness", async () => {
  await mountMocked();
  assert.equal(shown(), true);
  await tick(4900);
  assert.equal(shown(), true, "still visible before 5s");
  await tick(200);
  assert.equal(shown(), false, "hidden after 5s");
  await ev($(".player-frame"), "mousemove");
  assert.equal(shown(), true, "mouse movement brings them back");
  await tick(5100);
  assert.equal(shown(), false);
});

test("moving the mouse keeps resetting the 5s countdown", async () => {
  await mountMocked();
  for (let i = 0; i < 4; i++) { await tick(3000); await ev($(".player-frame"), "mousemove"); }
  assert.equal(shown(), true);
  await tick(5100);
  assert.equal(shown(), false);
});

test("controls stay while a popup is open, then fade after it closes", async () => {
  await mountMocked();
  await click(byText("عادي"));
  await tick(12000);
  assert.equal(shown(), true, "open menu pins the bar");
  await click([...document.querySelectorAll(".pc-opt")].find((b) => b.textContent.includes("1.25×")));
  await tick(5100);
  assert.equal(shown(), false);
});

test("controls stay while the pointer rests on the bar itself", async () => {
  await mountMocked();
  await ev($(".player-controls"), "mouseover");
  await tick(8000);
  assert.equal(shown(), true);
  await ev($(".player-controls"), "mouseout");
  await tick(1100);
  assert.equal(shown(), false);
});

test("leaving the player hides the bar at once; a key press wakes it", async () => {
  await mountMocked();
  await ev($(".player-frame"), "mouseout");
  assert.equal(shown(), false);
  await key($(".player-frame"), "ArrowLeft");
  assert.equal(shown(), true);
});

test("a paused video with hidden controls shows a big play mark", async () => {
  await mountMocked();
  assert.equal($(".player-bigplay"), null, "not while controls are visible");
  await tick(5100);
  assert.ok($(".player-bigplay"));
  await ev($(".player-frame"), "mousemove");
  assert.equal($(".player-bigplay"), null);
});
