// The QR badge is generated locally from the student's opaque code. The library returns an SVG string;
// instead of injecting it as raw HTML into the DOM (an XSS sink), we render it through an
// <img data:image/svg+xml>, where scripts and event handlers never execute, and we additionally refuse
// anything that is not a plain, script-free SVG.
const FORBIDDEN = /<\s*(script|foreignObject|iframe|object|embed|style|link|image|use|a)\b|\son[a-z]+\s*=|javascript:|data:text|<!entity|<!doctype/i;

export function qrImageSrc(svg) {
  if (typeof svg !== "string" || svg.length === 0 || svg.length > 200_000) return null;
  const text = svg.trim();
  if (!/^<svg[\s>]/i.test(text) || !/<\/svg>\s*$/i.test(text)) return null;
  if (FORBIDDEN.test(text)) return null;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`;
}
