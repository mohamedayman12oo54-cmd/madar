// Pure helpers behind the exam page's lock-down. They hold the decisions (which key is a copy attempt,
// how much time is left on the SERVER's clock) so they can be unit-tested without a browser.
//
// Honest scope: a web page cannot prevent a screenshot or a photo of the screen. These helpers exist to
// block copying and printing from the page, to notice the student leaving it, and to make any leaked
// picture traceable (watermark). The server keeps the clock and the log.

export const KINDS = {
  FULLSCREEN_EXIT: "fullscreen_exit",
  TAB_HIDDEN: "tab_hidden",
  WINDOW_BLUR: "window_blur",
  PRINT: "print_attempt",
  SCREENSHOT: "screenshot_key",
  COPY: "copy_attempt",
  PASTE: "paste_attempt",
  CONTEXT_MENU: "context_menu",
  DEVTOOLS: "devtools_key",
  RESUMED: "resumed",
};

/** The letter on a key, independent of the keyboard layout: Ctrl+C on an Arabic layout reports
 *  key "ؤ" but code "KeyC". */
function letter(e) {
  const code = String(e.code || "");
  if (code.startsWith("Key")) return code.slice(3).toLowerCase();
  return String(e.key || "").toLowerCase();
}

/** What to do with a key press: `block` it, and/or report an `event` (kind) to the server. */
export function classifyKey(e) {
  const l = letter(e);
  const mod = Boolean(e.ctrlKey || e.metaKey);
  if (e.key === "PrintScreen" || e.code === "PrintScreen")
    return { block: true, event: KINDS.SCREENSHOT };
  // Windows snipping (Win+Shift+S) and the macOS shortcuts (Cmd+Shift+3/4/5)
  if (e.metaKey && e.shiftKey && (l === "s" || ["Digit3", "Digit4", "Digit5"].includes(e.code))) {
    return { block: true, event: KINDS.SCREENSHOT };
  }
  if (
    e.key === "F12" ||
    (mod && e.shiftKey && ["i", "j", "c"].includes(l)) ||
    (e.metaKey && e.altKey && ["i", "j", "c"].includes(l))
  ) {
    return { block: true, event: KINDS.DEVTOOLS };
  }
  if (mod && !e.shiftKey && !e.altKey) {
    if (l === "c" || l === "x" || l === "a") return { block: true, event: KINDS.COPY };
    if (l === "v") return { block: true, event: KINDS.PASTE };
    if (l === "p") return { block: true, event: KINDS.PRINT };
    if (["s", "u", "f", "g", "o"].includes(l)) return { block: true, event: null };
  }
  return { block: false, event: null };
}

/** Whole seconds left, measured on the server's clock: the page's own clock can be wrong or changed. */
export function remainingSeconds({ deadline, serverNow, fetchedAtMs, nowMs = Date.now() }) {
  const offset = Date.parse(serverNow) - fetchedAtMs; // how far the server is ahead of this device
  return Math.max(0, Math.ceil((Date.parse(deadline) - (nowMs + offset)) / 1000));
}

export function formatClock(total) {
  const s = Math.max(0, Math.floor(total));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const pad = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${pad(m)}:${pad(s % 60)}`;
}

/** Lets one event of each kind through per `ms`, so a burst of identical signals is one request. */
export function createRateGate(ms, clock = Date.now) {
  const last = new Map();
  return (key) => {
    const t = clock();
    if (t - (last.get(key) ?? -Infinity) < ms) return false;
    last.set(key, t);
    return true;
  };
}

/** The faint text tiled over the paper. A photo of the screen then carries who it came from. */
export function watermarkLabel(name, phone) {
  const tail = String(phone || "")
    .replace(/\D/g, "")
    .slice(-4);
  return [String(name || "").trim(), tail].filter(Boolean).join(" · ");
}

/** The status the student's own list/detail screens show for an exam. */
export const EXAM_STATUS = {
  upcoming: { label: "لم يبدأ بعد", tone: "warn" },
  open: { label: "متاح الآن", tone: "good" },
  in_progress: { label: "جارٍ", tone: "good" },
  submitted: { label: "تم التسليم", tone: "" },
  missed: { label: "انتهى موعده", tone: "bad" },
};
