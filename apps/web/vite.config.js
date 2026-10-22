import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Content-Security-Policy for the PRODUCTION build only (the dev server needs inline scripts for
// React Fast Refresh, so it is served without one). It is injected as a <meta> tag at build time:
//   * script-src 'self'      — no inline script, no eval, no third-party script. This is the control
//                              that turns an XSS bug into a non-event, so it is never loosened.
//   * object-src 'none'      — no plugins.
//   * frame-src              — only the two video hosts the app embeds (also enforced in lib/video.js).
//   * connect-src / media-src — this origin plus the API origin taken from VITE_API_URL (API calls,
//                              resumable uploads and signed video playback come from there).
//   * style-src              — 'unsafe-inline' is limited to STYLES (React/framer-motion write style
//                              attributes); it never applies to scripts.
// `frame-ancestors` cannot be set from a <meta> tag; it is sent as a response header (public/_headers
// and deploy/security-headers.conf).
function contentSecurityPolicy(apiUrl) {
  let apiOrigin = "";
  try {
    apiOrigin = new URL(apiUrl).origin;
  } catch {
    /* an invalid VITE_API_URL is rejected at runtime by lib/api.js */
  }
  const self = (extra) => ["'self'", extra].filter(Boolean).join(" ");
  return [
    "default-src 'self'",
    "script-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    `connect-src ${self(apiOrigin)}`,
    `media-src ${self(apiOrigin)} blob:`,
    "img-src 'self' data: blob:",
    "font-src 'self' https://fonts.gstatic.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "frame-src https://www.youtube-nocookie.com https://player.vimeo.com",
    "worker-src 'self'",
    "manifest-src 'self'",
    "upgrade-insecure-requests",
  ].join("; ");
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [
      react(),
      {
        name: "madar-csp",
        apply: "build",
        transformIndexHtml(html) {
          const tag = `<meta http-equiv="Content-Security-Policy" content="${contentSecurityPolicy(env.VITE_API_URL)}" />`;
          return html.replace("<head>", `<head>\n    ${tag}`);
        },
      },
    ],
    build: {
      // Source maps would publish the original source (and any comment in it) to every visitor.
      sourcemap: false,
    },
  };
});
