// Idle sign-out: the session survives closing the tab/app (tokens live in localStorage for days), but a
// person who does NOTHING for IDLE_MS is signed out and must log in again — protects a teacher's phone
// or a shared computer left open. "Doing something" = touching, clicking, typing, scrolling, or a video
// playing. The last-activity time lives in localStorage so every tab and the installed app agree.
export const IDLE_MS = 2 * 60 * 60 * 1000; // two hours
const KEY = "madar:last-active";
const WRITE_EVERY_MS = 15 * 1000; // don't hammer storage on every mouse move

export const lastActive = () => {
  try {
    return Number(localStorage.getItem(KEY)) || 0;
  } catch {
    return 0;
  }
};
export const touchActivity = (now = Date.now()) => {
  try {
    localStorage.setItem(KEY, String(now));
  } catch {
    /* storage blocked: idle sign-out simply cannot be tracked */
  }
};
export const clearActivity = () => {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
};
export const isIdle = (now = Date.now(), last = lastActive()) => last > 0 && now - last > IDLE_MS;

/** Starts tracking; calls onIdle() once when the limit passes. Returns a stop function. */
export function watchIdle(onIdle) {
  // A session that predates this feature has no timestamp yet: start counting from now.
  if (!lastActive()) touchActivity();
  let lastWrite = 0;
  let fired = false;
  const check = () => {
    if (!fired && isIdle()) {
      fired = true;
      onIdle();
    }
  };
  const mark = () => {
    const now = Date.now();
    // Returning after a long absence must NOT silently revive the session: check first.
    if (isIdle(now)) return check();
    if (now - lastWrite > WRITE_EVERY_MS) {
      lastWrite = now;
      touchActivity(now);
    }
    return undefined;
  };
  const events = ["pointerdown", "keydown", "touchstart", "wheel", "scroll", "timeupdate", "play"];
  for (const e of events) document.addEventListener(e, mark, { capture: true, passive: true });
  const onVisible = () => document.visibilityState === "visible" && check();
  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener("focus", check);
  const timer = setInterval(check, 30 * 1000);
  check();
  return () => {
    for (const e of events) document.removeEventListener(e, mark, { capture: true });
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("focus", check);
    clearInterval(timer);
  };
}
