import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const win = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" }).window;
globalThis.window = win;
globalThis.document = win.document;
const { KEEPALIVE_MS, startKeepAlive } = await import("./keepalive.js");

const tick = () => new Promise((r) => setTimeout(r, 5));

test("renews on the timer, and stops when asked", async () => {
  let n = 0;
  const stop = startKeepAlive(() => { n += 1; }, { every: 20, minGap: 0 });
  await new Promise((r) => setTimeout(r, 90));
  stop();
  const seen = n;
  assert.ok(seen >= 2, `renewed ${seen} times`);
  await new Promise((r) => setTimeout(r, 60));
  assert.equal(n, seen, "no renewal after stop");
});

test("waking up (focus) renews, but not more often than the minimum gap", async () => {
  let n = 0;
  let t = 1_000;
  const stop = startKeepAlive(() => { n += 1; }, { every: 10_000_000, minGap: 1_000, now: () => t });
  win.dispatchEvent(new win.Event("focus"));
  await tick();
  assert.equal(n, 0, "too soon after start");
  t += 5_000;
  win.dispatchEvent(new win.Event("focus"));
  await tick();
  assert.equal(n, 1);
  win.dispatchEvent(new win.Event("focus"));
  await tick();
  assert.equal(n, 1, "just renewed");
  stop();
});

test("a renewal that throws never breaks the loop", async () => {
  let n = 0;
  const stop = startKeepAlive(() => { n += 1; throw new Error("offline"); }, { every: 15, minGap: 0 });
  await new Promise((r) => setTimeout(r, 70));
  stop();
  assert.ok(n >= 2);
});

test("the default is a renewal well inside the access-token life (30 min)", () => {
  assert.ok(KEEPALIVE_MS < 30 * 60 * 1000);
});
