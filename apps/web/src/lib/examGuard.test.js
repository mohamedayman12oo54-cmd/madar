import test from "node:test";
import assert from "node:assert/strict";
import {
  classifyKey,
  createRateGate,
  formatClock,
  remainingSeconds,
  watermarkLabel,
} from "./examGuard.js";

const key = (o) => ({
  key: "",
  code: "",
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  altKey: false,
  ...o,
});

test("copy, cut, select-all, paste and print shortcuts are blocked and reported", () => {
  assert.deepEqual(classifyKey(key({ key: "c", code: "KeyC", ctrlKey: true })), {
    block: true,
    event: "copy_attempt",
  });
  assert.deepEqual(classifyKey(key({ key: "x", code: "KeyX", metaKey: true })), {
    block: true,
    event: "copy_attempt",
  });
  assert.deepEqual(classifyKey(key({ key: "a", code: "KeyA", ctrlKey: true })), {
    block: true,
    event: "copy_attempt",
  });
  assert.deepEqual(classifyKey(key({ key: "v", code: "KeyV", ctrlKey: true })), {
    block: true,
    event: "paste_attempt",
  });
  assert.deepEqual(classifyKey(key({ key: "p", code: "KeyP", ctrlKey: true })), {
    block: true,
    event: "print_attempt",
  });
});

test("the shortcut is recognised on an Arabic keyboard layout (key is an Arabic letter, code is KeyC)", () => {
  assert.equal(classifyKey(key({ key: "ؤ", code: "KeyC", ctrlKey: true })).event, "copy_attempt");
  assert.equal(classifyKey(key({ key: "ر", code: "KeyV", ctrlKey: true })).event, "paste_attempt");
});

test("screenshot keys are blocked and reported", () => {
  assert.equal(
    classifyKey(key({ key: "PrintScreen", code: "PrintScreen" })).event,
    "screenshot_key"
  );
  assert.equal(
    classifyKey(key({ key: "S", code: "KeyS", metaKey: true, shiftKey: true })).event,
    "screenshot_key"
  );
  assert.equal(
    classifyKey(key({ key: "4", code: "Digit4", metaKey: true, shiftKey: true })).event,
    "screenshot_key"
  );
});

test("developer-tools shortcuts are blocked and reported", () => {
  assert.equal(classifyKey(key({ key: "F12", code: "F12" })).event, "devtools_key");
  assert.equal(
    classifyKey(key({ key: "I", code: "KeyI", ctrlKey: true, shiftKey: true })).event,
    "devtools_key"
  );
  assert.equal(
    classifyKey(key({ key: "i", code: "KeyI", metaKey: true, altKey: true })).event,
    "devtools_key"
  );
});

test("save / view-source / find are blocked quietly; ordinary typing and navigation pass", () => {
  assert.deepEqual(classifyKey(key({ key: "s", code: "KeyS", ctrlKey: true })), {
    block: true,
    event: null,
  });
  assert.deepEqual(classifyKey(key({ key: "u", code: "KeyU", ctrlKey: true })), {
    block: true,
    event: null,
  });
  for (const k of [
    key({ key: "ArrowLeft", code: "ArrowLeft" }),
    key({ key: "1", code: "Digit1" }),
    key({ key: "Enter", code: "Enter" }),
    key({ key: "c", code: "KeyC" }),
  ]) {
    assert.deepEqual(classifyKey(k), { block: false, event: null });
  }
});

test("remaining time follows the server clock, not the device clock", () => {
  // the device clock is 10 minutes slow: server says it is 12:00:00 when the device thinks 11:50:00
  const fetchedAtMs = Date.parse("2026-01-01T11:50:00Z");
  const base = { deadline: "2026-01-01T12:30:00Z", serverNow: "2026-01-01T12:00:00Z", fetchedAtMs };
  assert.equal(remainingSeconds({ ...base, nowMs: fetchedAtMs }), 30 * 60);
  assert.equal(remainingSeconds({ ...base, nowMs: fetchedAtMs + 5 * 60 * 1000 }), 25 * 60);
  assert.equal(remainingSeconds({ ...base, nowMs: fetchedAtMs + 31 * 60 * 1000 }), 0); // never negative
});

test("clock formatting", () => {
  assert.equal(formatClock(65), "01:05");
  assert.equal(formatClock(3725), "1:02:05");
  assert.equal(formatClock(-4), "00:00");
});

test("the rate gate lets one signal of each kind through per window", () => {
  let t = 0;
  const gate = createRateGate(1000, () => t);
  assert.equal(gate("blur"), true);
  assert.equal(gate("blur"), false);
  assert.equal(gate("hidden"), true); // a different kind is independent
  t = 1500;
  assert.equal(gate("blur"), true);
});

test("watermark carries the name and only the last four digits of the phone", () => {
  assert.equal(watermarkLabel("سارة أحمد", "+201012345678"), "سارة أحمد · 5678");
  assert.equal(watermarkLabel("", ""), "");
});
