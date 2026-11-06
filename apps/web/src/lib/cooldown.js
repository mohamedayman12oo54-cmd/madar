// "N tries, then wait": the server answers 429 with retry_after_seconds; the UI turns that into a visible timer.

const AR = new Intl.NumberFormat("ar-EG", { useGrouping: false });

/** 299 -> "٤:٥٩" (minutes:seconds, Arabic digits). */
export function clockText(seconds) {
  const s = Math.max(0, Math.ceil(Number(seconds) || 0));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${AR.format(m)}:${AR.format(r).padStart(2, "٠")}`;
}

/** Seconds to wait if `error` is a throttle answer (HTTP 429) that says how long, otherwise 0. */
export function cooldownSeconds(error) {
  if (!error || error.status !== 429) return 0;
  const n = Number(error.data?.retry_after_seconds);
  return Number.isFinite(n) && n > 0 ? Math.ceil(n) : 0;
}

/** Whole seconds left until `untilMs` (a Date.now()-style timestamp). */
export const secondsLeft = (untilMs, now = Date.now()) => Math.max(0, Math.ceil((untilMs - now) / 1000));
