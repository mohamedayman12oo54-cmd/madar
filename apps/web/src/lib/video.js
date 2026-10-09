// Accepts what a teacher actually pastes (a full link OR a bare id) and returns
// ONLY the bare id the API wants. The hostname is checked against an allowlist
// with the URL parser (never a substring test), so a look-alike link such as
// https://youtube.com.evil.example/watch?v=… is rejected, not "extracted".
const YT_ID = /^[A-Za-z0-9_-]{11}$/;
const VIMEO_ID = /^[0-9]{6,12}$/;
const YT_HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com", "youtu.be"]);
const VIMEO_HOSTS = new Set(["vimeo.com", "www.vimeo.com", "player.vimeo.com"]);

export function extractVideoId(provider, input) {
  const text = String(input ?? "").trim();
  if (!text) return "";
  const idRe = provider === "youtube" ? YT_ID : provider === "vimeo" ? VIMEO_ID : null;
  if (!idRe) return "";
  if (idRe.test(text)) return text;
  let url;
  try { url = new URL(text.includes("://") ? text : `https://${text}`); } catch { return ""; }
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
