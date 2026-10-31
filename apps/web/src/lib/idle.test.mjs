import test from "node:test";
import assert from "node:assert/strict";
import { IDLE_MS, isIdle } from "./idle.js";

test("idle after two hours without activity, not before", () => {
  const t0 = 1_000_000;
  assert.equal(isIdle(t0 + IDLE_MS - 1, t0), false);
  assert.equal(isIdle(t0 + IDLE_MS + 1, t0), true);
});
test("no recorded activity is never treated as idle (it starts counting instead)", () => {
  assert.equal(isIdle(Date.now(), 0), false);
});
