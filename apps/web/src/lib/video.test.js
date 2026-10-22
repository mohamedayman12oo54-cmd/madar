import test from "node:test";
import assert from "node:assert/strict";
import { extractVideoId } from "./video.js";

test("youtube links and bare ids", () => {
  const id = "dQw4w9WgXcQ";
  for (const input of [
    id,
    `https://www.youtube.com/watch?v=${id}`,
    `https://youtu.be/${id}?t=5`,
    `youtube.com/embed/${id}`,
    `https://m.youtube.com/shorts/${id}`,
  ])
    assert.equal(extractVideoId("youtube", input), id, input);
});

test("look-alike hosts and other schemes are rejected", () => {
  const id = "dQw4w9WgXcQ";
  for (const input of [
    `https://youtube.com.evil.example/watch?v=${id}`,
    `https://evil.example/?v=${id}`,
    `javascript:alert(1)//${id}`,
    `ftp://youtu.be/${id}`,
    "https://www.youtube.com/watch?v=short",
    "",
  ])
    assert.equal(extractVideoId("youtube", input), "", input);
});

test("vimeo links and wrong-provider input", () => {
  assert.equal(extractVideoId("vimeo", "https://vimeo.com/123456789"), "123456789");
  assert.equal(extractVideoId("vimeo", "https://player.vimeo.com/video/123456789"), "123456789");
  assert.equal(extractVideoId("vimeo", "https://vimeo.evil.example/123456789"), "");
  assert.equal(extractVideoId("youtube", "https://vimeo.com/123456789"), "");
  assert.equal(extractVideoId("none", "anything"), "");
});
