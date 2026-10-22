import test from "node:test";
import assert from "node:assert/strict";
import { parseLocal, formatLocal, monthGrid, to12h, from12h, shiftMonth } from "./datePicker.js";

test("parse/format round-trips a local value", () => {
  const p = parseLocal("2026-10-12T16:05");
  assert.deepEqual(p, { y: 2026, m: 9, d: 12, h: 16, mi: 5 });
  assert.equal(formatLocal(p), "2026-10-12T16:05");
  assert.equal(parseLocal(""), null);
  assert.equal(parseLocal("nope"), null);
});

test("month grid is Saturday-first and padded to whole weeks", () => {
  // 1 Oct 2026 is a Thursday -> 5 leading blanks when the week starts on Saturday.
  const rows = monthGrid(2026, 9);
  assert.ok(rows.every((r) => r.length === 7));
  assert.equal(
    rows[0].findIndex((c) => c === 1),
    5
  );
  assert.equal(rows.flat().filter(Boolean).length, 31);
  // 1 Aug 2026 is a Saturday -> no leading blanks.
  assert.equal(monthGrid(2026, 7)[0][0], 1);
});

test("12-hour conversion handles midnight and noon", () => {
  assert.deepEqual(to12h(0), { hour12: 12, pm: false });
  assert.deepEqual(to12h(12), { hour12: 12, pm: true });
  assert.deepEqual(to12h(16), { hour12: 4, pm: true });
  for (let h = 0; h < 24; h++) {
    const { hour12, pm } = to12h(h);
    assert.equal(from12h(hour12, pm), h);
  }
});

test("shiftMonth crosses year boundaries", () => {
  assert.deepEqual(shiftMonth(2026, 11, 1), { year: 2027, month: 0 });
  assert.deepEqual(shiftMonth(2026, 0, -1), { year: 2025, month: 11 });
});
