// Browser-side exam guard. IMPORTANT — what this can and cannot do:
//   * It DETECTS and reports: leaving the page/tab, losing focus, exiting full screen, copy/cut/paste,
//     the context menu, print, developer-tool and save shortcuts. The server counts the reports and
//     closes the attempt itself at the teacher's limit.
//   * It BLOCKS what a web page is allowed to block: copy/cut/paste/select/drag/context menu/print.
//   * It CANNOT stop a screenshot or a photo of the screen: browsers give pages no way to do that
//     (only a native app can). The defences against that are the visible per-student watermark, the
//     per-student shuffled order, and one-question-at-a-time delivery.
export const BLOCKED_KEYS = new Set(["c", "x", "v", "a", "p", "s", "u", "f", "g", "j", "i"]);

export const GRACE_MS = 1500; // entering full screen shakes focus around for a moment: not the student's doing

export function startGuard(report, { grace = GRACE_MS, now = Date.now } = {}) {
  const armedAt = now() + grace;
  const rep = (type) => {
    if (now() >= armedAt) report(type);
  };
  const on = (target, type, fn, opts) => {
    target.addEventListener(type, fn, opts);
    return () => target.removeEventListener(type, fn, opts);
  };
  const stop = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };
  const offs = [
    on(document, "visibilitychange", () => document.visibilityState === "hidden" && rep("hidden")),
    on(window, "blur", () => rep("blur")),
    on(document, "fullscreenchange", () => !document.fullscreenElement && rep("fullscreen_exit")),
    on(document, "copy", (e) => (stop(e), rep("copy")), true),
    on(document, "cut", (e) => (stop(e), rep("copy")), true),
    on(document, "paste", (e) => (stop(e), rep("paste")), true),
    on(document, "contextmenu", (e) => (stop(e), rep("contextmenu")), true),
    on(document, "dragstart", stop, true),
    on(document, "selectstart", stop, true),
    on(window, "beforeprint", () => rep("print")),
    on(
      document,
      "keydown",
      (e) => {
        const k = (e.key || "").toLowerCase();
        if (k === "printscreen") {
          rep("print");
          // Best effort only: replace whatever the OS put on the clipboard.
          navigator.clipboard?.writeText?.("").catch(() => {});
          return;
        }
        const devtools = k === "f12" || ((e.ctrlKey || e.metaKey) && e.shiftKey && ["i", "j", "c"].includes(k));
        if (devtools || ((e.ctrlKey || e.metaKey) && BLOCKED_KEYS.has(k))) {
          stop(e);
          rep("shortcut");
        }
      },
      true
    ),
    on(window, "beforeunload", (e) => {
      e.preventDefault();
      e.returnValue = "";
    }),
  ];
  return () => offs.forEach((off) => off());
}

export const enterFullscreen = () => {
  const el = document.documentElement;
  const fn = el.requestFullscreen || el.webkitRequestFullscreen;
  return fn ? Promise.resolve(fn.call(el)).catch(() => {}) : Promise.resolve();
};
export const inFullscreen = () => Boolean(document.fullscreenElement || document.webkitFullscreenElement);
export const fullscreenSupported = () => Boolean(document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen);

/** Tiled diagonal watermark with the student's name + phone, as a CSS background (an SVG data URI). */
export function watermarkStyle(text) {
  const esc = String(text).replace(/[<>&"']/g, "");
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='320' height='180'><text x='160' y='90' fill='rgba(49,56,81,0.13)' font-size='17' font-family='sans-serif' text-anchor='middle' transform='rotate(-24 160 90)'>${esc}</text></svg>`;
  return { backgroundImage: `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")` };
}

/** The browser's Back button must not walk a student out of the exam: park an extra history entry and put it
 *  back whenever it is popped, telling the page so it can say why. Returns a stop function. */
export function trapBack(onBlocked) {
  const park = () => window.history.pushState({ examLock: true }, "", window.location.href);
  park();
  const onPop = () => {
    park();
    onBlocked();
  };
  window.addEventListener("popstate", onPop);
  return () => window.removeEventListener("popstate", onPop);
}

export const leaveFullscreen = () => {
  const fn = document.exitFullscreen || document.webkitExitFullscreen;
  if (document.fullscreenElement || document.webkitFullscreenElement) {
    try {
      return Promise.resolve(fn?.call(document)).catch(() => {});
    } catch {
      /* ignore */
    }
  }
  return Promise.resolve();
};
