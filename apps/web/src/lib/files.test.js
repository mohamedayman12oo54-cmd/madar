import test from "node:test";
import assert from "node:assert/strict";
import { formatBytes } from "./files.js";

test("formatBytes: empty or invalid sizes give an empty label", () => {
  for (const v of [null, undefined, 0, -5, "abc", NaN]) assert.equal(formatBytes(v), "");
});

test("formatBytes: small files are shown in kilobytes, never as 0.00 MB", () => {
  assert.match(formatBytes(700), /^١ كيلوبايت$/);
  assert.match(formatBytes(150 * 1024), /١٥٠ كيلوبايت/);
});

test("formatBytes: larger files are shown in megabytes with one decimal", () => {
  assert.match(formatBytes(2.5 * 1024 * 1024), /٢٫٥ ميجابايت/);
  assert.match(formatBytes(50 * 1024 * 1024), /٥٠ ميجابايت/);
});
