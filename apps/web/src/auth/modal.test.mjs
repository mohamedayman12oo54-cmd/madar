// Locks the shared <Modal> layout contract that every form in the dashboard
// depends on: a sticky header, ONE scrollable body, an optional sticky footer,
// and a scroll-locked page behind it. These are the exact properties that were
// missing when large forms (Add Student, Add/Edit Content, ...) ran off the
// bottom of the screen and could not be scrolled.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", {
  url: "http://localhost:5173/app",
  pretendToBeVisual: true,
});
const w = dom.window;
for (const k of [
  "window",
  "document",
  "localStorage",
  "sessionStorage",
  "HTMLElement",
  "Element",
  "Node",
  "MutationObserver",
  "getComputedStyle",
  "requestAnimationFrame",
  "cancelAnimationFrame",
  "CustomEvent",
  "Event",
  "KeyboardEvent",
]) {
  Object.defineProperty(globalThis, k, {
    value: k === "window" ? w : w[k],
    configurable: true,
    writable: true,
  });
}
Object.defineProperty(globalThis, "navigator", { value: w.navigator, configurable: true });
for (const k of Object.getOwnPropertyNames(w)) {
  if (!(k in globalThis) && /^[A-Z]/.test(k))
    Object.defineProperty(globalThis, k, { value: w[k], configurable: true, writable: true });
}
w.matchMedia =
  w.matchMedia ||
  (() => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  }));
globalThis.matchMedia = w.matchMedia;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { createServer } = await import("vite");
const vite = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "error",
  optimizeDeps: { noDiscovery: true },
});
const { Modal, Field, TextInput, Btn } = await vite.ssrLoadModule("/src/auth/ui.jsx");

function mount(el) {
  const host = w.document.createElement("div");
  w.document.body.appendChild(host);
  const root = createRoot(host);
  act(() => root.render(el));
  return { host, root, unmount: () => act(() => root.unmount()) };
}

test("header, scrollable body and footer are distinct regions", () => {
  const { unmount } = mount(
    React.createElement(
      Modal,
      {
        title: "إضافة طالب",
        text: "وصف",
        size: "lg",
        onClose() {},
        footer: React.createElement("button", null, "حفظ"),
      },
      React.createElement("form", { className: "dash-form" }, "fields")
    )
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
  const { unmount } = mount(
    React.createElement(
      Modal,
      {
        title: "t",
        onClose: () => {
          closed += 1;
        },
      },
      "x"
    )
  );
  act(() => {
    w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape" }));
  });
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

// ---------------------------------------------------------------------------
// Keyboard & screen-reader behaviour (WCAG 2.1.2 / 2.4.3 / 3.3.2 / 4.1.2)
// ---------------------------------------------------------------------------
const key = (name, extra = {}) =>
  act(() => {
    w.document.activeElement.dispatchEvent(
      new w.KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true, ...extra })
    );
  });

test("opening moves focus into the dialog, closing hands it back to what opened it", () => {
  const opener = w.document.createElement("button");
  opener.textContent = "open";
  w.document.body.appendChild(opener);
  opener.focus();
  const { unmount } = mount(React.createElement(Modal, { title: "t", onClose() {} }, "x"));
  const panel = w.document.querySelector(".modal");
  assert.ok(panel.contains(w.document.activeElement), "focus is inside the dialog");
  unmount();
  assert.ok(w.document.activeElement === opener, "focus returns to the opener");
  opener.remove();
});

test("a parent re-render with a new onClose does not steal focus from a field being typed in", () => {
  const host = w.document.createElement("div");
  w.document.body.appendChild(host);
  const root = createRoot(host);
  const view = (n) =>
    React.createElement(
      Modal,
      { title: "t", onClose: () => n }, // a NEW function identity on every render, like inline handlers
      React.createElement("input", { id: "typing", defaultValue: "" })
    );
  act(() => root.render(view(1)));
  const input = w.document.getElementById("typing");
  input.focus();
  assert.ok(w.document.activeElement === input);
  act(() => root.render(view(2)));
  act(() => root.render(view(3)));
  assert.ok(w.document.activeElement === input, "typing focus survives parent re-renders");
  act(() => root.unmount());
  host.remove();
});

test("Tab and Shift+Tab stay inside the dialog", () => {
  const { unmount } = mount(
    React.createElement(
      Modal,
      { title: "t", onClose() {}, footer: React.createElement("button", { id: "last" }, "حفظ") },
      React.createElement("input", { id: "first" })
    )
  );
  const first = w.document.getElementById("first");
  const last = w.document.getElementById("last");
  last.focus();
  key("Tab");
  assert.ok(w.document.querySelector(".modal").contains(w.document.activeElement), "forward Tab wraps inside");
  assert.ok(w.document.activeElement !== last, "focus moved off the last control");
  first.focus();
  key("Tab", { shiftKey: true });
  assert.ok(w.document.querySelector(".modal").contains(w.document.activeElement), "Shift+Tab wraps inside");
  unmount();
});

test("Escape closes only the top-most of two stacked dialogs", () => {
  const closed = [];
  const a = mount(React.createElement(Modal, { title: "a", onClose: () => closed.push("a") }, "x"));
  const b = mount(React.createElement(Modal, { title: "b", onClose: () => closed.push("b") }, "y"));
  act(() => {
    w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape" }));
  });
  assert.deepEqual(closed, ["b"], "only the dialog on top reacts");
  b.unmount();
  a.unmount();
});

test("Field ties its label, hint and error to the control for screen readers", () => {
  const { unmount } = mount(
    React.createElement(
      Field,
      { label: "الاسم", hint: "اسم كامل", error: "مطلوب" },
      React.createElement(TextInput, { value: "", onChange() {} })
    )
  );
  const label = w.document.querySelector(".field label");
  const input = w.document.querySelector(".field input");
  assert.ok(input.id, "control gets an id");
  assert.equal(label.getAttribute("for"), input.id, "label points at the control");
  const described = w.document.getElementById(input.getAttribute("aria-describedby"));
  assert.ok(described && described.textContent.includes("مطلوب"), "error text is the accessible description");
  assert.equal(input.getAttribute("aria-invalid"), "true");
  unmount();
});

test("a loading button can never be re-enabled by an explicit disabled={false}", () => {
  const { unmount } = mount(React.createElement(Btn, { loading: true, disabled: false }, "حفظ"));
  assert.equal(w.document.querySelector("button").disabled, true);
  unmount();
});

test.after(() => vite.close());
