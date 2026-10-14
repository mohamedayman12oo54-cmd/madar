// Student activation UI: choose SMS or email, give the student code, enter the
// OTP, create a password, then land on the LOGIN page (never auto-signed-in).
// Runs the real screens + router in jsdom against a recording fake API.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:5173/auth/student/claim", pretendToBeVisual: true });
const w = dom.window;
for (const k of ["window", "document", "localStorage", "sessionStorage", "HTMLElement", "Element", "Node", "MutationObserver",
  "getComputedStyle", "requestAnimationFrame", "cancelAnimationFrame", "CustomEvent", "Event", "KeyboardEvent"]) {
  Object.defineProperty(globalThis, k, { value: k === "window" ? w : w[k], configurable: true, writable: true });
}
Object.defineProperty(globalThis, "navigator", { value: w.navigator, configurable: true });
for (const k of Object.getOwnPropertyNames(w)) {
  if (!(k in globalThis) && /^[A-Z]/.test(k)) Object.defineProperty(globalThis, k, { value: w[k], configurable: true, writable: true });
}
w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
globalThis.matchMedia = w.matchMedia;
globalThis.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const calls = [];
let claimReply = () => ({ status: 200, body: { pending_id: "p-1", channel: "email", target_masked: "ah•••@gmail.com", message: "ok" } });
globalThis.fetch = async (url, init = {}) => {
  const path = new URL(String(url)).pathname.replace(/^\/api\/v1/, "");
  const body = init.body ? JSON.parse(init.body) : undefined;
  calls.push({ path, body });
  let r = { status: 200, body: {} };
  if (path === "/auth/teacher/signup/") r = { status: 200, body: { pending_id: "t-1", channel: body.otp_channel, target_masked: body.otp_channel === "email" ? "te•••@gmail.com" : "••••••••1234" } };
  else if (path === "/auth/student/claim/") r = claimReply(body);
  else if (path === "/auth/otp/student-claim/verify/") r = { status: 200, body: { pending_id: "p-1", verified: true } };
  else if (path === "/auth/student/claim/activate/") r = { status: 201, body: { message: "ok", phone_hint: "••••••4567" } };
  return new Response(JSON.stringify(r.body), { status: r.status, headers: { "content-type": "application/json" } });
};

const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { MemoryRouter, Routes, Route } = await import("react-router-dom");
const { createServer } = await import("vite");
const vite = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error", optimizeDeps: { noDiscovery: true } });
const { StudentClaim, StudentLogin } = await vite.ssrLoadModule("/src/auth/screens/StudentAuth.jsx");
const { TeacherSignup } = await vite.ssrLoadModule("/src/auth/screens/TeacherAuth.jsx");
const { SessionProvider } = await vite.ssrLoadModule("/src/state/session.jsx");
const { EnvironmentProvider } = await vite.ssrLoadModule("/src/state/environment.jsx");

const tick = (ms = 30) => new Promise((r) => setTimeout(r, ms));
const $ = (sel) => w.document.querySelector(sel);
const text = () => w.document.body.textContent;
const setter = Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, "value").set;
async function type(el, value) {
  await act(async () => { setter.call(el, value); el.dispatchEvent(new w.Event("input", { bubbles: true })); });
}
async function click(el) { await act(async () => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); await tick(); }); }
const button = (label) => [...w.document.querySelectorAll("button")].find((b) => b.textContent.includes(label));
const radio = (label) => [...w.document.querySelectorAll('[role="radio"]')].find((b) => b.textContent.includes(label));

async function mount() {
  w.document.body.innerHTML = "<div id='root'></div>";
  const root = createRoot($("#root"));
  await act(async () => {
    root.render(React.createElement(MemoryRouter, { initialEntries: ["/auth/student/claim"] },
      React.createElement(SessionProvider, null, React.createElement(EnvironmentProvider, null,
        React.createElement(Routes, null,
          React.createElement(Route, { path: "/auth/student/claim", element: React.createElement(StudentClaim) }),
          React.createElement(Route, { path: "/auth/student", element: React.createElement(StudentLogin) }))))));
    await tick();
  });
  return root;
}

test("offers exactly two verification options and swaps the contact field", async () => {
  const root = await mount();
  assert.equal(w.document.querySelectorAll('[role="radio"]').length, 2);
  assert.equal(radio("SMS").getAttribute("aria-checked"), "true", "SMS is the default");
  assert.ok($('input[type="tel"]'), "phone field shown for SMS");
  assert.ok(!$('input[type="email"]'));
  await click(radio("Gmail"));
  assert.ok($('input[type="email"]'), "email field shown for email");
  assert.ok(!$('input[type="tel"]'));
  assert.ok($(".code-inp"), "the student code is asked for in BOTH cases");
  await act(async () => root.unmount());
});

test("the student code is mandatory: nothing is sent without it", async () => {
  calls.length = 0;
  const root = await mount();
  await click(radio("Gmail"));
  await type($('input[type="email"]'), "ahmed@gmail.com");
  await click(button("إرسال رمز التحقق"));
  assert.equal(calls.filter((c) => c.path === "/auth/student/claim/").length, 0);
  assert.match(text(), /كود الطالب/);
  await act(async () => root.unmount());
});

test("email path: request -> OTP -> password -> login page, with no session issued", async () => {
  calls.length = 0;
  localStorage.clear();
  const root = await mount();
  await click(radio("Gmail"));
  await type($('input[type="email"]'), "ahmed@gmail.com");
  await type($(".code-inp"), "k7m2qx");
  await click(button("إرسال رمز التحقق"));
  const req = calls.find((c) => c.path === "/auth/student/claim/");
  assert.deepEqual(req.body, { channel: "email", student_code: "K7M2QX", email: "ahmed@gmail.com" });
  assert.match(text(), /ah•••@gmail\.com/, "shows the masked destination");

  await type($(".otp input"), "123456");
  await click(button("تأكيد"));
  assert.deepEqual(calls.find((c) => c.path === "/auth/otp/student-claim/verify/").body, { pending_id: "p-1", code: "123456" });

  const [pw, pw2] = w.document.querySelectorAll('input[type="password"]');
  await type(pw, "Str0ng!Pass1"); await type(pw2, "Str0ng!Pass1");
  await click(button("تفعيل حسابي"));
  assert.match(text(), /تم تفعيل حسابك بنجاح/);
  assert.match(text(), /4567/, "tells an email-activated student which phone to log in with");

  await click(button("تسجيل الدخول"));
  assert.match(text(), /تسجيل دخول الطالب/, "now on the login page");
  assert.match(text(), /تم تفعيل حسابك/);
  assert.equal(localStorage.getItem("madar.tokens"), null, "activation must not sign the student in");
  await act(async () => root.unmount());
});

test("phone path sends the phone + code; a wrong code shows the server message and stays put", async () => {
  calls.length = 0;
  claimReply = () => ({ status: 400, body: { detail: "لم نتمكن من التحقق من بياناتك.", code: "not_found" } });
  const root = await mount();
  await type($('input[type="tel"]'), "1001234567");
  await type($(".code-inp"), "AAAAAA");
  await click(button("إرسال رمز التحقق"));
  const req = calls.find((c) => c.path === "/auth/student/claim/");
  assert.equal(req.body.channel, "phone");
  assert.equal(req.body.student_code, "AAAAAA");
  assert.match(req.body.phone, /^\+201001234567$/);
  assert.match(text(), /لم نتمكن من التحقق/);
  assert.ok($(".code-inp"), "still on the entry screen so the typo can be fixed");
  await act(async () => root.unmount());
});

test("teacher signup lets the teacher pick where the OTP goes (default SMS, or email)", async () => {
  calls.length = 0;
  w.document.body.innerHTML = "<div id='root'></div>";
  const root = createRoot($("#root"));
  await act(async () => {
    root.render(React.createElement(MemoryRouter, { initialEntries: ["/auth/teacher/signup"] },
      React.createElement(SessionProvider, null, React.createElement(EnvironmentProvider, null,
        React.createElement(Routes, null, React.createElement(Route, { path: "/auth/teacher/signup", element: React.createElement(TeacherSignup) }))))));
    await tick();
  });
  assert.equal(w.document.querySelectorAll('[role="radio"]').length, 2);
  assert.equal(radio("SMS").getAttribute("aria-checked"), "true");
  const [name, email] = w.document.querySelectorAll("input.inp:not([type=password]):not([type=tel])");
  await type(name, "أحمد المعلم"); await type(email, "teach@gmail.com");
  await type($('input[type="tel"]'), "1001234567");
  const [pw, pw2] = w.document.querySelectorAll('input[type="password"]');
  await type(pw, "Str0ng!Pass1"); await type(pw2, "Str0ng!Pass1");
  await click(radio("Gmail"));
  await click(button("متابعة"));
  const req = calls.find((c) => c.path === "/auth/teacher/signup/");
  assert.equal(req.body.otp_channel, "email");
  assert.match(text(), /te•••@gmail\.com/, "OTP screen names the email it was sent to");
  await act(async () => root.unmount());
});

test.after(async () => { await vite.close(); });
