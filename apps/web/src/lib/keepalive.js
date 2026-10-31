// Keeps a signed-in session alive for as long as the page stays open — the opposite of an idle timeout.
// A person is signed out in exactly one situation: they pressed "log out" (or the server really refused the
// credentials, e.g. the password was reset). Being quiet for hours is NOT one of them.
//
// While the tab is open we renew the credentials on a timer and whenever the tab becomes visible / the
// device comes back online, so a laptop that slept overnight is still signed in when it wakes up.
export const KEEPALIVE_MS = 20 * 60 * 1000; // renew every 20 minutes
const MIN_GAP_MS = 5 * 60 * 1000; // …but never more often than every 5 minutes, whatever fires

/** Calls `renew()` periodically. Returns a stop function. `renew` must swallow its own network errors. */
export function startKeepAlive(renew, { every = KEEPALIVE_MS, minGap = MIN_GAP_MS, now = Date.now } = {}) {
  let last = now();
  let running = false;
  const run = async (force = false) => {
    if (running || (!force && now() - last < minGap)) return;
    running = true;
    try {
      await renew();
    } catch {
      /* a failed renewal says nothing about the session: try again next time */
    } finally {
      last = now();
      running = false;
    }
  };
  const timer = setInterval(() => run(true), every);
  const onVisible = () => document.visibilityState === "visible" && run();
  const onOnline = () => run();
  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener("online", onOnline);
  window.addEventListener("focus", onOnline);
  return () => {
    clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onOnline);
    window.removeEventListener("focus", onOnline);
  };
}
