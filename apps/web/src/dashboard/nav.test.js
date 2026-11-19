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
  assert.deepEqual(
    ends.map((n) => n.to),
    ["/app"]
  );
});

import { dashboardNavGroups, mobileTabs, quickActions } from "./nav.js";

test("the sidebar groups contain every page exactly once and the flat list is derived from them", () => {
  const grouped = dashboardNavGroups.flatMap((g) => g.items.map((i) => i.to));
  assert.deepEqual(grouped, dashboardNav.map((n) => n.to));
  assert.equal(new Set(grouped).size, grouped.length);
  for (const g of dashboardNavGroups.slice(1)) assert.ok(g.title, "every group after the first has a heading");
});

test("the phone bottom bar and the quick-create menu only point at real dashboard pages", () => {
  const known = new Set(dashboardNav.map((n) => n.to));
  assert.equal(mobileTabs.length, 4);
  for (const t of mobileTabs) assert.ok(t && known.has(t.to), "mobile tab target must be a nav page");
  for (const a of quickActions) {
    assert.ok(known.has(a.to), `${a.to} is not a dashboard page`);
    assert.ok(a.label && a.hint && a.icon);
  }
});

test("groups come before students in the sidebar (a student is added into a group), and in the quick-create menu", () => {
  const order = dashboardNav.map((n) => n.to);
  assert.ok(order.indexOf("/app/groups") < order.indexOf("/app/students"));
  const quick = quickActions.map((a) => a.to);
  assert.ok(quick.indexOf("/app/groups") < quick.indexOf("/app/students"));
});
