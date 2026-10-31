// Thin wrappers over the Fullscreen API. iPhone Safari has none, so the exam page treats full screen as
// required only where the browser can provide it (it still watches focus and tab visibility everywhere).
export const fullscreenSupported = () =>
  typeof document !== "undefined" &&
  Boolean(document.documentElement?.requestFullscreen) &&
  document.fullscreenEnabled !== false;
export const isFullscreen = () => Boolean(document.fullscreenElement);
export const enterFullscreen = () =>
  document.documentElement.requestFullscreen({ navigationUI: "hide" });
export const exitFullscreen = () =>
  document.fullscreenElement ? document.exitFullscreen().catch(() => {}) : Promise.resolve();
