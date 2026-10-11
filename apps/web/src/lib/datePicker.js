// Pure helpers behind <DateTimePicker>. No DOM, no React: easy to test.
// A "local value" is the same string a <input type="datetime-local"> uses,
// "YYYY-MM-DDTHH:mm", so callers keep their existing toIso()/toLocalInput().
const pad = (n) => String(n).padStart(2, "0");

export function parseLocal(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(value || ""));
  if (!m) return null;
  const [, y, mo, d, h, mi] = m.map(Number);
  const date = new Date(y, mo - 1, d, h, mi);
  return Number.isNaN(date.getTime()) ? null : { y, m: mo - 1, d, h, mi };
}

export function formatLocal({ y, m, d, h, mi }) {
  return `${y}-${pad(m + 1)}-${pad(d)}T${pad(h)}:${pad(mi)}`;
}

/** Weeks start on Saturday (Egypt). Returns rows of 7 cells; null = padding. */
export function monthGrid(year, month) {
  const lead = (new Date(year, month, 1).getDay() + 1) % 7; // Sat=0 .. Fri=6
  const days = new Date(year, month + 1, 0).getDate();
  const cells = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  const rows = [];
  for (let i = 0; i < cells.length; i += 7) rows.push(cells.slice(i, i + 7));
  return rows;
}

/** 24h -> { hour12: 1..12, pm } and back. 12 AM = 00:00, 12 PM = 12:00. */
export const to12h = (h24) => ({ hour12: h24 % 12 === 0 ? 12 : h24 % 12, pm: h24 >= 12 });
export const from12h = (hour12, pm) => (hour12 % 12) + (pm ? 12 : 0);

export const shiftMonth = (year, month, delta) => {
  const d = new Date(year, month + delta, 1);
  return { year: d.getFullYear(), month: d.getMonth() };
};
