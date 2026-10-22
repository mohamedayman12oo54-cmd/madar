// Each lazily loaded area ships only the CSS it imports. A screen that uses the dashboard's shared
// classes (cards, rows, chips) without importing dashboard.css renders as bare stacked text when it is
// opened directly (e.g. a guardian landing on /parent). This guard fails the build if that happens.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));
const read = (f) => fs.readFileSync(f, "utf8");

const SHARED = /className=["{`][^"`}]*\b(dash-cards|dash-card|list-rows|list-row|chip-s|mini-btn|dash-section-head)\b/;

test("every area entry that uses dashboard classes imports dashboard.css", () => {
  const entries = ["parent/ParentPortal.jsx", "student/StudentLayout.jsx", "team/TeamLayout.jsx", "dashboard/DashboardLayout.jsx"];
  for (const rel of entries) {
    const dir = path.dirname(path.join(SRC, rel));
    const usesShared = walk(dir).filter((f) => /\.jsx$/.test(f)).some((f) => SHARED.test(read(f)));
    if (!usesShared) continue;
    assert.match(read(path.join(SRC, rel)), /import\s+["'](\.\.\/dashboard\/|\.\/)dashboard\.css["']/, `${rel} uses dashboard classes but does not import dashboard.css`);
  }
});

test("dashboard.css is imported before an area's own stylesheet so the area can override it", () => {
  for (const rel of ["parent/ParentPortal.jsx", "student/StudentLayout.jsx"]) {
    const t = read(path.join(SRC, rel));
    assert.ok(t.indexOf("dashboard.css") !== -1 && t.indexOf("dashboard.css") < t.indexOf("student.css"), `${rel}: import order`);
  }
});
