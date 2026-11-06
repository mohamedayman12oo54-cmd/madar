import test from "node:test";
import assert from "node:assert/strict";
import { clockText, cooldownSeconds, secondsLeft } from "./cooldown.js";

test("clockText shows minutes:seconds in Arabic digits and never goes negative", () => {
  assert.equal(clockText(300), "٥:٠٠");
  assert.equal(clockText(299), "٤:٥٩");
  assert.equal(clockText(61), "١:٠١");
  assert.equal(clockText(9), "٠:٠٩");
  assert.equal(clockText(-4), "٠:٠٠");
  assert.equal(clockText(undefined), "٠:٠٠");
});

test("cooldownSeconds only reads a 429 that says how long to wait", () => {
  assert.equal(cooldownSeconds({ status: 429, data: { retry_after_seconds: 297 } }), 297);
  assert.equal(cooldownSeconds({ status: 429, data: { retry_after_seconds: 12.2 } }), 13);
  assert.equal(cooldownSeconds({ status: 429, data: {} }), 0);
  assert.equal(cooldownSeconds({ status: 500, data: { retry_after_seconds: 30 } }), 0);
  assert.equal(cooldownSeconds(null), 0);
});

test("secondsLeft rounds up and stops at zero", () => {
  assert.equal(secondsLeft(10_000, 9_001), 1);
  assert.equal(secondsLeft(10_000, 10_000), 0);
  assert.equal(secondsLeft(10_000, 20_000), 0);
});
