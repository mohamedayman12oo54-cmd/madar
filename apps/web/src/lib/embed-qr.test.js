import test from "node:test";
import assert from "node:assert/strict";
import { safeEmbedUrl } from "./video.js";
import { qrImageSrc } from "./qr.js";

test("safeEmbedUrl allows only the real embed endpoints of the two video hosts", () => {
  assert.equal(safeEmbedUrl("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"), "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ");
  assert.equal(safeEmbedUrl("https://player.vimeo.com/video/123456789"), "https://player.vimeo.com/video/123456789");
  for (const bad of [
    "http://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", "https://evil.com/embed/dQw4w9WgXcQ",
    "https://www.youtube-nocookie.com.evil.com/embed/dQw4w9WgXcQ", "https://www.youtube-nocookie.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube-nocookie.com/embed/short", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ/../../x",
    "https://user:pw@www.youtube-nocookie.com/embed/dQw4w9WgXcQ", "https://www.youtube-nocookie.com:8443/embed/dQw4w9WgXcQ",
    "https://player.vimeo.com/video/abc", "javascript:alert(1)", "data:text/html,<script>1</script>", "", null, undefined,
    "http://localhost:5173/app", "https://localhost/embed/dQw4w9WgXcQ",
  ]) assert.equal(safeEmbedUrl(bad), null, String(bad));
});

test("qrImageSrc turns a plain QR svg into an inert data URL and refuses anything active", () => {
  const ok = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3 3"><path d="M0 0h1v1H0z"/></svg>';
  assert.match(qrImageSrc(ok), /^data:image\/svg\+xml;charset=utf-8,/);
  for (const bad of [
    '<svg><script>alert(1)</script></svg>', '<svg onload="alert(1)"></svg>', '<svg><foreignObject><div/></foreignObject></svg>',
    '<svg><a href="javascript:alert(1)"/></svg>', '<img src=x onerror=alert(1)>', '<svg></svg><script>1</script>',
    '<svg><style>@import url(//evil)</style></svg>', "", null, undefined, 42, "x".repeat(300000),
  ]) assert.equal(qrImageSrc(bad), null, String(bad).slice(0, 40));
});
