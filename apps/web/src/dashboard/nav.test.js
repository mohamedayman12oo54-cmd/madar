import { test } from "node:test";
import assert from "node:assert/strict";
import { dashboardNav } from "./nav.js";

test("every dashboard nav entry has a unique path, a label, and an icon component", () => {
  const paths = dashboardNav.map((n) => n.to);
  assert.equal(new Set(paths).size, paths.length, "duplicate path in dashboardNav");
  for (const entry of dashboardNav) {
    assert.ok(entry.to.startsWith("/app"), `${entry.to} should live under /app`);
    assert.ok(entry.label && entry.label.length > 0, `${entry.to} is missing a label`);
    assert.ok(entry.icon, `${entry.to} is missing an icon component`);
  }
});

test("only the overview entry is an exact-match (end) route", () => {
  const ends = dashboardNav.filter((n) => n.end);
  assert.deepEqual(ends.map((n) => n.to), ["/app"]);
});
