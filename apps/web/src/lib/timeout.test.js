import test from "node:test";
import assert from "node:assert/strict";
import { withTimeout } from "./timeout.js";

const never = () => new Promise(() => {});

test("a promise that settles in time passes through", async () => {
  assert.equal(await withTimeout(Promise.resolve(7), 1000), 7);
});

test("a promise that never settles gives up with the fallback instead of freezing the caller", async () => {
  assert.equal(await withTimeout(never(), 20), undefined);
  assert.equal(await withTimeout(never(), 20, "late"), "late");
});

test("a rejection of the promise itself is not hidden by the timeout", async () => {
  await assert.rejects(withTimeout(Promise.reject(new Error("boom")), 1000), /boom/);
});

test("a slow success after the deadline does not resolve twice or throw", async () => {
  const slow = new Promise((r) => setTimeout(() => r("slow"), 60));
  assert.equal(await withTimeout(slow, 10, "fallback"), "fallback");
  await new Promise((r) => setTimeout(r, 80));
});

test("with no service worker registered at all, push lookup answers immediately (no waiting)", async () => {
  globalThis.window = { PushManager: {}, Notification: {} };
  Object.defineProperty(globalThis, "navigator", {
    value: { serviceWorker: { ready: never(), getRegistration: () => Promise.resolve(undefined) } }, configurable: true,
  });
  try {
    const { currentSubscription } = await import("./push.js");
    const t0 = Date.now();
    await assert.rejects(currentSubscription(), /service worker not ready/);
    assert.ok(Date.now() - t0 < 500);
  } finally {
    delete globalThis.window;
    delete globalThis.navigator;
  }
});

test("push lookup rejects instead of hanging when no service worker ever becomes ready (this froze sign-out)", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  globalThis.window = { PushManager: {}, Notification: {} };
  Object.defineProperty(globalThis, "navigator", {
    value: { serviceWorker: { ready: never(), getRegistration: () => Promise.resolve({}) } },  // registered, never ready
    configurable: true,
  });
  try {
    const { currentSubscription, detachDevice } = await import("./push.js");
    const lookup = currentSubscription();
    const outcome = assert.rejects(lookup, /service worker not ready/);
    t.mock.timers.tick(4000);
    await outcome;
    // and sign-out's cleanup step swallows that failure rather than blocking
    const cleanup = detachDevice();
    t.mock.timers.tick(4000);
    await cleanup;
  } finally {
    delete globalThis.window;
    delete globalThis.navigator;
  }
});
