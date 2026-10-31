import test from "node:test";
import assert from "node:assert/strict";
import { parseSummary, MAX_SUMMARY_CHARS } from "./summary.js";

test("headings, paragraphs and lists are recognised", () => {
  const blocks = parseSummary("# الدرس\nمقدمة\nسطر ثانٍ\n\n## نقاط\n- أ\n- ب\n* ج\n\n1. خطوة\n2) خطوة أخرى");
  assert.deepEqual(blocks, [
    { type: "h", level: 1, text: "الدرس" },
    { type: "p", text: "مقدمة\nسطر ثانٍ" },
    { type: "h", level: 2, text: "نقاط" },
    { type: "ul", items: ["أ", "ب", "ج"] },
    { type: "ol", items: ["خطوة", "خطوة أخرى"] },
  ]);
});

test("deep headings fold into level 2 and CRLF is handled", () => {
  assert.deepEqual(parseSummary("#### صغير\r\nنص"), [
    { type: "h", level: 2, text: "صغير" },
    { type: "p", text: "نص" },
  ]);
});

test("markup is kept as inert text, never interpreted", () => {
  const html = '<img src=x onerror="alert(1)"><script>alert(1)</script>';
  assert.deepEqual(parseSummary(html), [{ type: "p", text: html }]);
});

test("empty and non-string input produce no blocks", () => {
  assert.deepEqual(parseSummary(""), []);
  assert.deepEqual(parseSummary(null), []);
  assert.deepEqual(parseSummary("   \n \n"), []);
});

test("the cap matches the server's", () => {
  assert.equal(MAX_SUMMARY_CHARS, 20000);
});
