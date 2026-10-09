import test from "node:test";
import assert from "node:assert/strict";
import {
  DAY_NAMES, dayKey, dayName, daysFromToday, groupByDay, isToday,
  pyToJsDay, relativeHint, scheduleSummary, sessionDayLabel,
} from "./dates.js";

// Sunday 12 October 2026, 16:00 local.
const SUN = new Date(2026, 9, 11, 16, 0);
const at = (d, h = 16) => new Date(2026, 9, d, h, 0);

test("day names follow the Arabic week", () => {
  assert.equal(dayName(at(11)), "الأحد");
  assert.equal(dayName(at(13)), "الثلاثاء");
  assert.equal(dayName(at(15)), "الخميس");
  assert.equal(dayName(at(10)), "السبت");
});

test("python weekday numbers map onto JS days", () => {
  // Schedule.WEEKDAYS: 5=السبت, 6=الأحد, 0=الاثنين, 3=الخميس
  assert.equal(DAY_NAMES[pyToJsDay(5)], "السبت");
  assert.equal(DAY_NAMES[pyToJsDay(6)], "الأحد");
  assert.equal(DAY_NAMES[pyToJsDay(0)], "الاثنين");
  assert.equal(DAY_NAMES[pyToJsDay(3)], "الخميس");
});

test("day difference is midnight-based, not 24h-based", () => {
  // 23:30 today -> 00:30 tomorrow is ONE day apart, though barely an hour.
  assert.equal(daysFromToday(at(12, 0), at(11, 23)), 1);
  assert.equal(daysFromToday(at(11, 1), SUN), 0);
  assert.equal(daysFromToday(at(10), SUN), -1);
});

test("today and tomorrow are called out by name", () => {
  assert.match(sessionDayLabel(at(11), SUN), /^اليوم · الأحد/);
  assert.match(sessionDayLabel(at(12), SUN), /^غدًا · الاثنين/);
  assert.match(sessionDayLabel(at(10), SUN), /^أمس · السبت/);
});

test("a day later this week is named without a prefix", () => {
  const label = sessionDayLabel(at(13), SUN);   // Tuesday, 2 days out
  assert.match(label, /^الثلاثاء /);
  assert.ok(!label.includes("القادم"));
});

test("the same weekday next week is marked القادم", () => {
  assert.match(sessionDayLabel(at(20), SUN), /^الثلاثاء القادم /);
});

test("labels always carry the date, never just the day", () => {
  for (const d of [10, 11, 13, 20]) {
    assert.match(sessionDayLabel(at(d), SUN), /\d|[٠-٩]/, "label must contain a date");
  }
});

test("relative hints read naturally", () => {
  assert.equal(relativeHint(at(11), SUN), "اليوم");
  assert.equal(relativeHint(at(12), SUN), "غدًا");
  assert.equal(relativeHint(at(14), SUN), "بعد 3 يوم");
  assert.equal(relativeHint(at(9), SUN), "منذ 2 يوم");
});

test("isToday / dayKey bucket by calendar day", () => {
  assert.ok(isToday(at(11, 1), SUN));
  assert.ok(!isToday(at(12, 1), SUN));
  assert.equal(dayKey(at(11)), "2026-10-11");
  assert.equal(dayKey(at(11, 23)), dayKey(at(11, 0)));
});

test("groupByDay buckets, orders and labels sessions", () => {
  const sessions = [
    { id: 3, scheduled_at: at(13, 18).toISOString() },
    { id: 1, scheduled_at: at(11, 16).toISOString() },
    { id: 2, scheduled_at: at(11, 10).toISOString() },
  ];
  const days = groupByDay(sessions, SUN);
  assert.equal(days.length, 2);
  assert.equal(days[0].key, "2026-10-11");
  assert.ok(days[0].isToday);
  assert.match(days[0].label, /^اليوم · الأحد/);
  assert.deepEqual(days[0].sessions.map((s) => s.id), [2, 1]);  // earliest first
  assert.equal(days[1].name, "الثلاثاء");
  assert.ok(!days[1].isToday);
});

test("groupByDay ignores sessions with no date instead of crashing", () => {
  assert.deepEqual(groupByDay([{ id: 1 }, { id: 2, scheduled_at: null }], SUN), []);
  assert.deepEqual(groupByDay(null, SUN), []);
});

test("schedule summary lists meeting days Saturday-first, de-duplicated", () => {
  // Thursday(3), Saturday(5), Tuesday(1), Saturday again
  assert.equal(
    scheduleSummary([{ weekday: 3 }, { weekday: 5 }, { weekday: 1 }, { weekday: 5 }]),
    "السبت، الثلاثاء، الخميس",
  );
  assert.equal(scheduleSummary([]), "");
});
