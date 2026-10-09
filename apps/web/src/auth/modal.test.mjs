// Locks the shared <Modal> layout contract that every form in the dashboard
// depends on: a sticky header, ONE scrollable body, an optional sticky footer,
// and a scroll-locked page behind it. These are the exact properties that were
// missing when large forms (Add Student, Add/Edit Content, ...) ran off the
// bottom of the screen and could not be scrolled.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", {
  url: "http://localhost:5173/app", pretendToBeVisual: true,
});
const w = dom.window;
for (const k of ["window", "document", "localStorage", "sessionStorage", "HTMLElement", "Element", "Node",
  "MutationObserver", "getComputedStyle", "requestAnimationFrame", "cancelAnimationFrame",
  "CustomEvent", "Event", "KeyboardEvent"]) {
  Object.defineProperty(globalThis, k, { value: k === "window" ? w : w[k], configurable: true, writable: true });
}
Object.defineProperty(globalThis, "navigator", { value: w.navigator, configurable: true });
for (const k of Object.getOwnPropertyNames(w)) {
  if (!(k in globalThis) && /^[A-Z]/.test(k)) Object.defineProperty(globalThis, k, { value: w[k], configurable: true, writable: true });
}
w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
globalThis.matchMedia = w.matchMedia;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { createServer } = await import("vite");
const vite = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error", optimizeDeps: { noDiscovery: true } });
const { Modal } = await vite.ssrLoadModule("/src/auth/ui.jsx");

function mount(el) {
  const host = w.document.createElement("div");
  w.document.body.appendChild(host);
  const root = createRoot(host);
  act(() => root.render(el));
  return { host, root, unmount: () => act(() => root.unmount()) };
}

test("header, scrollable body and footer are distinct regions", () => {
  const { unmount } = mount(
    React.createElement(Modal, { title: "إضافة طالب", text: "وصف", size: "lg", onClose() {},
      footer: React.createElement("button", null, "حفظ") },
      React.createElement("form", { className: "dash-form" }, "fields"))
  );
  const panel = w.document.querySelector(".modal");
  assert.ok(panel, "panel rendered");
  assert.ok(panel.classList.contains("modal-lg"), "size class applied");
  assert.ok(panel.querySelector(".modal-head"), "sticky header region exists");
  assert.equal(panel.querySelectorAll(".ma").length, 1, "exactly ONE scroll container");
  assert.ok(panel.querySelector(".modal-foot"), "sticky footer region exists");
  // The form must live in the body, the actions in the footer — that is what
  // keeps the buttons reachable without scrolling to the end of a long form.
  assert.ok(panel.querySelector(".ma .dash-form"), "form is inside the scroll body");
  assert.ok(!panel.querySelector(".ma .modal-foot"), "footer is NOT inside the scroll body");
  unmount();
});

test("dialog is accessible and labelled by its title", () => {
  const { unmount } = mount(React.createElement(Modal, { title: "عنوان", onClose() {} }, "x"));
  const panel = w.document.querySelector(".modal");
  assert.equal(panel.getAttribute("role"), "dialog");
  assert.equal(panel.getAttribute("aria-modal"), "true");
  const id = panel.getAttribute("aria-labelledby");
  assert.ok(id && w.document.getElementById(id), "aria-labelledby points at the title node");
  unmount();
});

test("page behind the modal is scroll-locked, and restored on close", () => {
  w.document.body.style.overflow = "";
  const { unmount } = mount(React.createElement(Modal, { title: "t", onClose() {} }, "x"));
  assert.equal(w.document.body.style.overflow, "hidden", "background locked while open");
  unmount();
  assert.notEqual(w.document.body.style.overflow, "hidden", "lock released on close");
});

test("stacked modals only unlock once the last one closes", () => {
  w.document.body.style.overflow = "";
  const a = mount(React.createElement(Modal, { title: "a", onClose() {} }, "x"));
  const b = mount(React.createElement(Modal, { title: "b", onClose() {} }, "y"));
  assert.equal(w.document.body.style.overflow, "hidden");
  b.unmount();
  assert.equal(w.document.body.style.overflow, "hidden", "still locked: one modal remains");
  a.unmount();
  assert.notEqual(w.document.body.style.overflow, "hidden", "released after the last one");
});

test("Escape closes the dialog", () => {
  let closed = 0;
  const { unmount } = mount(React.createElement(Modal, { title: "t", onClose: () => { closed += 1; } }, "x"));
  act(() => { w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape" })); });
  assert.equal(closed, 1, "Escape triggered onClose");
  unmount();
});

test("omitting footer keeps old call sites working (no empty footer node)", () => {
  const { unmount } = mount(React.createElement(Modal, { title: "t", onClose() {} }, "body only"));
  const panel = w.document.querySelector(".modal");
  assert.equal(panel.querySelector(".modal-foot"), null, "no footer region when none passed");
  assert.equal(panel.querySelectorAll(".ma").length, 1);
  unmount();
});

test.after(() => vite.close());
