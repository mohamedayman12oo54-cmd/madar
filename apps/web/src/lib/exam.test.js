import test from "node:test";
import assert from "node:assert/strict";
import { band, clock, progressPct, warningInfo, warningsText, VIOLATION_TEXT } from "./exam.js";

test("clock shows minutes and seconds in Arabic digits, never negative", () => {
  assert.equal(clock(0), "٠٠:٠٠");
  assert.equal(clock(125), "٠٢:٠٥");
  assert.equal(clock(-5), "٠٠:٠٠");
  assert.equal(clock(3725), "١:٠٢:٠٥");
});

test("result bands follow the percentage", () => {
  assert.equal(band(100).cls, "is-great");
  assert.equal(band(90).cls, "is-great");
  assert.equal(band(89.9).cls, "is-good");
  assert.equal(band(60).cls, "is-fair");
  assert.equal(band(50).cls, "is-pass");
  assert.equal(band(49).cls, "is-low");
  assert.equal(band(undefined).cls, "is-low");
});

test("the warning card says which warning it is and what happens next", () => {
  const first = warningInfo({ type: "hidden", violations: 1, max: 3 });
  assert.equal(first.left, 2);
  assert.equal(first.final, false);
  assert.match(first.reason, /التبويب/);
  assert.match(first.next, /تحذيران/);
  const last = warningInfo({ type: "copy", violations: 2, max: 3 });
  assert.equal(last.final, true);
  assert.equal(last.title, "آخر تحذير");
  assert.match(last.next, /فورًا/);
});

test("every violation the guard can report has plain wording", () => {
  for (const k of ["blur", "hidden", "fullscreen_exit", "copy", "paste", "contextmenu", "print", "shortcut"]) {
    assert.ok(VIOLATION_TEXT[k], k);
  }
  assert.match(warningInfo({ type: "weird", violations: 1, max: 3 }).reason, /غير مسموح/);
});

test("plural forms of 'warning'", () => {
  assert.equal(warningsText(1), "تحذير واحد");
  assert.equal(warningsText(2), "تحذيران");
  assert.match(warningsText(5), /تحذيرات/);
});

test("progress is the share of questions already passed", () => {
  assert.equal(progressPct(0, 10), 0);
  assert.equal(progressPct(3, 10), 30);
  assert.equal(progressPct(10, 10), 100);
  assert.equal(progressPct(1, 0), 0);
});
