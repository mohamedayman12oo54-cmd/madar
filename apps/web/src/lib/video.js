// Accepts what a teacher actually pastes (a full link OR a bare id) and returns
// ONLY the bare id the API wants. The hostname is checked against an allowlist
// with the URL parser (never a substring test), so a look-alike link such as
// https://youtube.com.evil.example/watch?v=… is rejected, not "extracted".
const YT_ID = /^[A-Za-z0-9_-]{11}$/;
const VIMEO_ID = /^[0-9]{6,12}$/;
const YT_HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "youtube-nocookie.com",
  "www.youtube-nocookie.com",
  "youtu.be",
]);
const VIMEO_HOSTS = new Set(["vimeo.com", "www.vimeo.com", "player.vimeo.com"]);

export function extractVideoId(provider, input) {
  const text = String(input ?? "").trim();
  if (!text) return "";
  const idRe = provider === "youtube" ? YT_ID : provider === "vimeo" ? VIMEO_ID : null;
  if (!idRe) return "";
  if (idRe.test(text)) return text;
  let url;
  try {
    url = new URL(text.includes("://") ? text : `https://${text}`);
  } catch {
    return "";
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return "";
  const host = url.hostname.toLowerCase();
  const parts = url.pathname.split("/").filter(Boolean);
  let candidate = "";
  if (provider === "youtube" && YT_HOSTS.has(host)) {
    if (host === "youtu.be") candidate = parts[0] || "";
    else if (parts[0] === "watch") candidate = url.searchParams.get("v") || "";
    else if (["embed", "shorts", "live", "v"].includes(parts[0])) candidate = parts[1] || "";
  } else if (provider === "vimeo" && VIMEO_HOSTS.has(host)) {
    candidate = parts.find((p) => /^\d+$/.test(p)) || "";
  }
  return idRe.test(candidate) ? candidate : "";
}

// ---------------------------------------------------------------------------
// Embed allow-list. The server builds the embed URL, but the browser must not
// trust that blindly: a frame's source is only ever set to one of the two exact
// embed endpoints below (https, default port, no credentials, no extra path or
// query). Anything else — another host, a look-alike, `javascript:`, `data:` —
// returns null and the caller shows an error instead of a frame. The Content
// Security Policy (`frame-src`) enforces the same two hosts a second time.
const YT_EMBED_PATH = /^\/embed\/[A-Za-z0-9_-]{11}$/;
const VIMEO_EMBED_PATH = /^\/video\/[0-9]{6,12}$/;

export function safeEmbedUrl(input) {
  if (typeof input !== "string" || input.length === 0 || input.length > 300) return null;
  let url;
  try {
    url = new URL(input);
  } catch {
    return null;
  }
  if (url.protocol !== "https:") return null;
  if (url.username || url.password || url.port) return null;
  if (url.search || url.hash) return null;
  const host = url.hostname.toLowerCase();
  if (host === "www.youtube-nocookie.com" && YT_EMBED_PATH.test(url.pathname)) return url.href;
  if (host === "player.vimeo.com" && VIMEO_EMBED_PATH.test(url.pathname)) return url.href;
  return null;
}
