/**
 * Arabic date helpers for the session calendar.
 *
 * Sessions are never shown as a bare timestamp: a teacher thinks in
 * "الأحد ١٢ أكتوبر", not "2026-10-12T16:00:00Z". Everything here produces the
 * named day plus its date, and marks today / tomorrow explicitly so the
 * current lesson is obvious at a glance.
 *
 * Weeks start on Saturday (Egypt), which is also the order the backend lists
 * its weekday choices in.
 */
const AR = "ar-EG";

// JS getDay(): 0=Sunday .. 6=Saturday. Saturday-first order for display.
export const WEEK_ORDER = [6, 0, 1, 2, 3, 4, 5];

export const DAY_NAMES = {
  6: "السبت", 0: "الأحد", 1: "الاثنين", 2: "الثلاثاء",
  3: "الأربعاء", 4: "الخميس", 5: "الجمعة",
};

/** Python weekday (Mon=0 .. Sun=6, what the Schedule model stores) → JS getDay(). */
export const pyToJsDay = (py) => (Number(py) + 1) % 7;

const asDate = (value) => (value instanceof Date ? value : new Date(value));

export const dayName = (value) => DAY_NAMES[asDate(value).getDay()] ?? "";

/** Midnight-based day difference, so 23:59 → 00:01 counts as one day, not zero. */
export function daysFromToday(value, now = new Date()) {
  const a = asDate(value);
  const d1 = new Date(a.getFullYear(), a.getMonth(), a.getDate());
  const d0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((d1 - d0) / 86400000);
}

export const isToday = (value, now = new Date()) => daysFromToday(value, now) === 0;

/** "١٢ أكتوبر" — day + month, no year unless it differs from the current one. */
export function dateLabel(value, now = new Date()) {
  const d = asDate(value);
  const opts = { day: "numeric", month: "long" };
  if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
  return new Intl.DateTimeFormat(AR, opts).format(d);
}

export const timeLabel = (value) =>
  new Intl.DateTimeFormat(AR, { hour: "numeric", minute: "2-digit" }).format(asDate(value));

/**
 * The headline for a session row.
 *
 * today      -> "اليوم · الأحد ١٢ أكتوبر"
 * tomorrow   -> "غدًا · الاثنين ١٣ أكتوبر"
 * this week  -> "الثلاثاء ١٤ أكتوبر"
 * next week  -> "الثلاثاء القادم ٢١ أكتوبر"
 * past       -> "الأحد ٥ أكتوبر"
 */
export function sessionDayLabel(value, now = new Date()) {
  const diff = daysFromToday(value, now);
  const name = dayName(value);
  const date = dateLabel(value, now);
  if (diff === 0) return `اليوم · ${name} ${date}`;
  if (diff === 1) return `غدًا · ${name} ${date}`;
  if (diff === -1) return `أمس · ${name} ${date}`;
  if (diff > 1 && diff <= 7) return `${name} ${date}`;
  if (diff > 7 && diff <= 14) return `${name} القادم ${date}`;
  return `${name} ${date}`;
}

/** Short relative hint shown next to the headline. */
export function relativeHint(value, now = new Date()) {
  const diff = daysFromToday(value, now);
  if (diff === 0) return "اليوم";
  if (diff === 1) return "غدًا";
  if (diff < 0) return `منذ ${Math.abs(diff)} يوم`;
  if (diff <= 7) return `بعد ${diff} يوم`;
  return `بعد ${Math.ceil(diff / 7)} أسبوع`;
}

/** Stable bucket key for grouping sessions by calendar day (local time). */
export function dayKey(value) {
  const d = asDate(value);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/**
 * Group sessions into ordered day buckets for the calendar view.
 * Each bucket: { key, date, name, label, hint, isToday, sessions }.
 */
export function groupByDay(sessions, now = new Date()) {
  const buckets = new Map();
  for (const s of sessions || []) {
    const when = s.scheduled_at;
    if (!when) continue;
    const key = dayKey(when);
    if (!buckets.has(key)) {
      buckets.set(key, {
        key,
        date: asDate(when),
        name: dayName(when),
        label: sessionDayLabel(when, now),
        hint: relativeHint(when, now),
        isToday: isToday(when, now),
        sessions: [],
      });
    }
    buckets.get(key).sessions.push(s);
  }
  const out = [...buckets.values()].sort((a, b) => a.date - b.date);
  for (const b of out) {
    b.sessions.sort((x, y) => new Date(x.scheduled_at) - new Date(y.scheduled_at));
  }
  return out;
}

/** The weekdays a group actually meets, e.g. "السبت، الثلاثاء، الخميس". */
export function scheduleSummary(schedules) {
  const names = (schedules || [])
    .map((s) => pyToJsDay(s.weekday))
    .filter((d, i, arr) => arr.indexOf(d) === i)
    .sort((a, b) => WEEK_ORDER.indexOf(a) - WEEK_ORDER.indexOf(b))
    .map((d) => DAY_NAMES[d]);
  return names.join("، ");
}
