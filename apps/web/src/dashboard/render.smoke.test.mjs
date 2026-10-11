// Render smoke test: mounts the REAL router + providers + every dashboard page
// in jsdom, against a mocked API, and fails on any render/effect crash
// (undefined variable, bad import, wrong prop shape...). A production build
// cannot catch these — they only show up as a blank page in the browser.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", { url: "http://localhost:5173/app", pretendToBeVisual: true });
const w = dom.window;
for (const k of ["window", "document", "localStorage", "sessionStorage", "HTMLElement", "Element", "Node", "MutationObserver", "getComputedStyle", "requestAnimationFrame", "cancelAnimationFrame", "CustomEvent", "Event", "KeyboardEvent"]) {
  Object.defineProperty(globalThis, k, { value: k === "window" ? w : w[k], configurable: true, writable: true });
}
Object.defineProperty(globalThis, "navigator", { value: w.navigator, configurable: true });
// Expose the rest of the browser surface (SVGElement, HTMLInputElement, ...) that libraries probe for.
for (const k of Object.getOwnPropertyNames(w)) {
  if (!(k in globalThis) && /^[A-Z]/.test(k)) Object.defineProperty(globalThis, k, { value: w[k], configurable: true, writable: true });
}
w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
globalThis.matchMedia = w.matchMedia;
globalThis.IntersectionObserver = globalThis.IntersectionObserver || class { observe() {} unobserve() {} disconnect() {} };
w.IntersectionObserver = globalThis.IntersectionObserver;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const NOW = new Date().toISOString();
const MONTH = NOW.slice(0, 7);
const ENROLLMENT = { id: 1, student: { id: 5, name: "أحمد", phone: "201001234567" }, grade: { id: 1, name: "أول", fee_amount: "100.00" }, groups: [{ id: 1, name: "G1" }], academic_year: "2026 / 2027", is_active: true, parent_name: "ولي", parent_phone: "201001234568", can_edit_phone: true, created_at: NOW };
const SESSION = { id: 1, group: { id: 1, name: "G1", grade_id: 1 }, scheduled_at: NOW, status: "open", reopened_count: 0 };
const TEACHER = { id: 1, role: "teacher", name: "مدرّس", email: "t@example.com", phone: "201001234567" };
const STUDENT = { id: 5, role: "student", name: "أحمد", email: null, phone: "201001234567" };
let ME = TEACHER;
const ROUTES = {
  "/auth/me/": () => ME,
  "/environments/context/": { id: 1, name: "بيئة", initials: "ب", role: "owner" },
  "/environments/current/": { id: 1, name: "بيئة", subject_stage: "رياضيات", academic_year: "2026 / 2027", created_at: NOW },
  "/environments/overview/": { environment: { name: "بيئة", academic_year: "2026 / 2027" }, students: { active: 2, inactive: 1 }, structure: { grades: 1, groups: 1 },
    sessions: { today: [{ id: 1, group: "G1", scheduled_at: NOW, status: "open" }], open: 1, upcoming: [{ id: 2, group: "G1", scheduled_at: NOW, status: "planned" }] },
    payments: { month: MONTH, paid: 1, students: 2, expected_total: "200.00", collected_total: "100.00", outstanding_total: "100.00" }, notifications: { pending: 1, failed: 1 } },
  "/academics/grades/": { count: 1, results: [{ id: 1, name: "أول", fee_amount: "100.00", order: 0 }] },
  "/academics/groups/": { count: 1, results: [{ id: 1, name: "G1", grade_id: 1, student_count: 2 }] },
  "/academics/enrollments/": { count: 1, next: null, previous: null, results: [ENROLLMENT] },
  "/scheduling/sessions/": { count: 3, results: [
    SESSION,
    { id: 2, group: { id: 1, name: "G1", grade_id: 1 },
      scheduled_at: new Date(Date.now() + 2 * 864e5).toISOString(), status: "planned", reopened_count: 0 },
    { id: 3, group: { id: 2, name: "G2", grade_id: 1 },
      scheduled_at: new Date(Date.now() - 864e5).toISOString(), status: "closed", reopened_count: 1 },
  ] },
  "/scheduling/sessions/1/roster/": { session: SESSION, students: [{ enrollment_id: 1, name: "أحمد", attendance: null, recitation: null }, { enrollment_id: 2, name: "سارة", attendance: "present", recitation: "studied", carried_from: { session_id: 9, scheduled_at: NOW, group: "G2" } }],
    guests: [{ enrollment_id: 7, name: "ضيف", attendance: "present", recitation: null, applied: false, home_session: { id: 5, scheduled_at: NOW, group: "G2", status: "planned" } }], counts: {} },
  "/scheduling/sessions/1/guest-candidates/": { results: [{ enrollment_id: 8, name: "زائر جديد", grade: "أول", groups: ["G2"], upcoming: [{ id: 5, scheduled_at: NOW, group: "G2", status: "planned" }] }] },
  "/scheduling/sessions/1/guests/": { enrollment_id: 8, name: "زائر جديد", attendance: null, recitation: null, applied: false, home_session: null },
  "/scheduling/sessions/1/": {},
  "/scheduling/schedules/": { count: 0, results: [] },
  "/financials/monthly/": { month: MONTH, rows: [{ enrollment_id: 1, name: "أحمد", grade: "أول", status: "unpaid", amount: "100.00", paid_at: null, note: "" }], summary: { students: 1, paid: 0, unpaid: 1, expected_total: "100.00", collected_total: "0.00", outstanding_total: "100.00" } },
  "/evaluation/monthly/": { month: MONTH, rows: [{ enrollment_id: 1, name: "أحمد", grade: "أول", rating: { value: 3, published: false }, state: "good", evidence: { present: 2, absent: 1, studied: 1, not_studied: 0 }, recommendation: null }] },
  "/content/": { count: 3, results: [
    // published upload
    { id: 1, title: "درس منشور", description: "", source: "upload", original_filename: "a.mp4", file_size: 1024,
      video: null, targets: { grades: [{ id: 1, name: "أول" }], groups: [], students: [] },
      published: true, published_at: NOW, created_at: NOW },
    // draft WITH a file but no targets
    { id: 2, title: "مسودة بلا مستهدفين", description: "", source: "upload", original_filename: "b.mp4", file_size: 1024,
      video: null, targets: { grades: [], groups: [], students: [] },
      published: false, published_at: null, created_at: NOW },
    // draft with NO file yet
    { id: 3, title: "مسودة بلا فيديو", description: "", source: "external",
      video: null, targets: { grades: [{ id: 1, name: "أول" }], groups: [], students: [] },
      published: false, published_at: null, created_at: NOW },
  ] },
  "/notifications/": { count: 1, next: null, previous: null, results: [{ id: 1, type: "absent", type_label: "غياب", title: "t", body: "b", student: { id: 5, name: "أحمد" }, delivery_status: "failed", created_at: NOW }, { id: 2, type: "new_video", type_label: "فيديو جديد", title: "فيديو جديد", body: "", student: { id: 5, name: "أحمد" }, content_item: { id: 1, title: "درس الخلية", grades: ["أول"], groups: ["G1"] }, delivery_status: "sent", created_at: NOW }] },
  "/notifications/summary/": { pending: 1, sent: 2, failed: 1 },
  "/ai/operations/": { count: 0, results: [] },
  // ---- student area ----
  "/student/overview/": { environment: { name: "بيئة" }, student: { badge_code: "WK38G4", name: "أحمد" }, grade: "أول", groups: ["G1"],
    this_month: { month: MONTH, payment: "paid", state: "good", rating: 4, attendance: { present: 3, absent: 1 }, recitation: { studied: 2, not_studied: 1 } },
    unread_notifications: 2, latest_videos: [{ id: 1, title: "درس الخلية", description: "d", video: { provider: "youtube", embed_url: "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" }, can_quiz: true }] },
  "/student/attendance/": { summary: { present: 1, absent: 1 }, results: [{ id: 1, date: NOW, group: "G1", status: "present" }] },
  "/student/recitation/": { summary: { studied: 1, not_studied: 0 }, results: [{ id: 1, date: NOW, group: "G1", status: "studied" }] },
  "/student/payments/": { results: [{ month: MONTH, status: "paid", receipt: { student_name: "أحمد", grade: "أول", groups: ["G1"], teacher_environment: "بيئة", month: MONTH, amount: "100.00", paid_at: NOW, reference: "MDR-1-202610", note: "" } }] },
  "/student/evaluation/": { results: [{ month: "2026-10", state: "good", rating: 4 }], notes: [{ id: 1, body: "ملاحظة من المعلّم", created_at: NOW, updated_at: NOW }] },
  "/student/videos/1/": { id: 1, title: "درس الخلية", description: "وصف طويل للدرس", source: "external", video: { provider: "youtube", embed_url: "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" }, can_quiz: true, progress: null },
  "/student/videos/": { results: [{ id: 1, title: "درس الخلية", description: "وصف طويل للدرس", video: { provider: "youtube", embed_url: "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" }, can_quiz: true }] },
  "/student/notifications/": { results: [{ id: 1, type: "absent", type_label: "غياب", title: "تم تسجيل غيابك", body: "b", created_at: NOW, read: false }] },
  "/student/quizzes/": { results: [{ id: 1, title: "درس الخلية", created_at: NOW, questions: 2, score: null, total: null }, { id: 2, title: "درس 2", created_at: NOW, questions: 2, score: 1, total: 2 }] },
  "/student/quizzes/1/": { id: 1, title: "درس الخلية", submitted: false, questions: [{ q: "أكمل: _____ هي الوحدة", options: ["الخلية", "النواة"] }, { q: "س2", options: ["أ", "ب", "ج"] }] },
  "/student/quizzes/2/": { id: 2, title: "درس 2", submitted: true, score: 1, total: 2, questions: [{ q: "س1", options: ["أ", "ب"], answer_index: 0, chosen: 1, explanation: "ش" }, { q: "س2", options: ["أ", "ب"], answer_index: 1, chosen: 1, explanation: "" }] },
  "/scheduling/scan/resolve/": { enrollment_id: 1, name: "طالب", grade: "أول", is_active: true,
    session_id: 1, attendance: null, recitation: null, month: "2026-10", fee_amount: "150.00",
    payment_status: "unpaid" },
  "/scheduling/sessions/bulk/": { created: 1, skipped: [], results: [] },
  "/notifications/broadcasts/": { results: [{ id: 1, title: "رسالة", body: "نص", recipient_count: 2, grades: ["أول"], groups: ["G1"], created_at: NOW }] },
  "/parent/overview/": { student: { name: "ابن", grade: "أول", teacher_environment: "بيئة" },
    attendance: { present: 2, absent: 1, total: 3, recent: [{ date: NOW, status: "present" }, { date: NOW, status: "absent" }] },
    recitation: { studied: 1, not_studied: 1, total: 2, recent: [{ date: NOW, status: "studied" }] },
    payments: { this_month: { month: MONTH, status: "paid", amount: "200.00" }, history: [{ month: MONTH, status: "paid", amount: "200.00", paid_at: NOW }] },
    evaluation: [{ month: MONTH, state: "good", state_label: "جيد", rating: 4 }],
    notifications: [{ id: 1, type: "absent", type_label: "غياب", title: "تم تسجيل الغياب", body: "b", created_at: NOW }] },
  "/student/assistant/": { count: 1, results: [{ id: 9, kind: "assistant", status: "completed",
    prompt: "ما هي الخلية؟", result: "إجابة", error: "", created_at: NOW, completed_at: NOW,
    sources: [{ id: 1, title: "الخلية", topic: "أحياء", version: 2 }] }] },
};
globalThis.fetch = async (url) => {
  const path = new URL(String(url), "http://x").pathname.replace(/^\/api\/v1/, "");
  return new Response(JSON.stringify(typeof ROUTES[path] === "function" ? ROUTES[path]() : (ROUTES[path] ?? {})), { status: 200, headers: { "content-type": "application/json" } });
};
localStorage.setItem("madar.tokens", JSON.stringify({ access: "a", refresh: "r" }));
localStorage.setItem("madar.activeEnvironment", "1");

const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { MemoryRouter } = await import("react-router-dom");
const { createServer } = await import("vite");
const vite = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error", optimizeDeps: { noDiscovery: true } });
const load = (p) => vite.ssrLoadModule(p);
const { SessionProvider } = await load("/src/state/session.jsx");
const { EnvironmentProvider } = await load("/src/state/environment.jsx");
const AppRoutes = (await load("/src/dashboard/AppRoutes.jsx")).default;
const StudentRoutes = (await load("/src/student/StudentRoutes.jsx")).default;
const ParentPortal = (await load("/src/parent/ParentPortal.jsx")).default;

const STUDENT_PAGES = ["/learn", "/learn/records", "/learn/videos", "/learn/videos/1", "/learn/quizzes", "/learn/quizzes/1", "/learn/quizzes/2", "/learn/assistant", "/learn/notifications", "/learn/settings"];
const PAGES = ["/app", "/app/students", "/app/groups", "/app/sessions", "/app/attendance", "/app/attendance?session=1", "/app/scan", "/app/evaluation", "/app/financials", "/app/content", "/app/notifications", "/app/settings"];
const tick = (ms = 40) => new Promise((r) => setTimeout(r, ms));

for (const [path, Routes_, who] of [...PAGES.map((p) => [p, AppRoutes, TEACHER]), ...STUDENT_PAGES.map((p) => [p, StudentRoutes, STUDENT])]) {
  test(`${who.role} page renders without crashing: ${path}`, async () => {
    ME = who;
    const errors = [];
    const origError = console.error;
    console.error = (...a) => errors.push(a.map(String).join(" "));
    const onErr = (e) => errors.push(String(e.error || e.message));
    w.addEventListener("error", onErr);
    const container = w.document.createElement("div");
    w.document.body.appendChild(container);
    const root = createRoot(container);
    try {
      await act(async () => {
        root.render(React.createElement(MemoryRouter, { initialEntries: [path] },
          React.createElement(SessionProvider, null, React.createElement(EnvironmentProvider, null, React.createElement(Routes_)))));
      });
      await act(async () => { await tick(120); });
      await act(async () => { await tick(60); });
      assert.deepEqual(errors, [], `console/runtime errors on ${path}:\n${errors.join("\n")}`);
      assert.ok(container.textContent.trim().length > 20, `page ${path} rendered blank`);
      assert.ok(container.querySelector("nav, aside, header, .dash-main, main"), `layout missing on ${path}`);
    } finally {
      await act(async () => { root.unmount(); });
      console.error = origError;
      w.removeEventListener("error", onErr);
      container.remove();
    }
  });
}

test("sessions: the add dialog plans one session per picked group through the custom date picker", async () => {
  ME = TEACHER;
  const calls = [];
  const origFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), init }); return origFetch(url, init); };
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  const click = (el) => act(async () => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true })); await tick(20); });
  try {
    await act(async () => {
      root.render(React.createElement(MemoryRouter, { initialEntries: ["/app/sessions"] },
        React.createElement(SessionProvider, null, React.createElement(EnvironmentProvider, null, React.createElement(AppRoutes)))));
    });
    await act(async () => { await tick(150); });
    const addBtn = [...container.querySelectorAll("button")].find((b) => b.textContent.includes("جلسة إضافية"));
    assert.ok(addBtn, "add-session button missing");
    await click(addBtn);

    assert.ok(w.document.querySelector(".pick-chips"), "group chips missing");
    await click(w.document.querySelector(".pick-all"));              // every group of the grade
    const submit = () => [...w.document.querySelectorAll(".modal button[type=submit]")][0];
    assert.equal(submit().disabled, false);

    await click(w.document.querySelector(".dtp-trigger"));           // open the custom picker
    assert.ok(w.document.querySelector(".dtp-sheet"), "picker did not open");
    assert.equal(w.document.querySelector("input[type=datetime-local]"), null, "native datetime input still used");
    await click(w.document.querySelectorAll(".dtp-day")[9]);
    await act(async () => { w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); await tick(20); });
    assert.equal(w.document.querySelector(".dtp-sheet"), null, "Esc should close the picker");
    assert.ok(w.document.querySelector(".modal"), "Esc must not also close the dialog");

    await click(submit());
    await act(async () => { await tick(60); });
    const post = calls.find((c) => c.url.includes("/scheduling/sessions/bulk/"));
    assert.ok(post, "bulk create was not called");
    const body = JSON.parse(post.init.body);
    assert.equal(body.grade_id, 1);
    assert.deepEqual(body.group_ids, [1]);
    assert.match(body.scheduled_at, /^\d{4}-\d{2}-\d{2}T/);
  } finally {
    globalThis.fetch = origFetch;
    await act(async () => { root.unmount(); });
    container.remove();
  }
});
async function mount(path, element) {
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(React.createElement(MemoryRouter, { initialEntries: [path] },
      React.createElement(SessionProvider, null, React.createElement(EnvironmentProvider, null, element))));
  });
  await act(async () => { await tick(150); });
  return { container, root, done: async () => { await act(async () => { root.unmount(); }); container.remove(); } };
}
const clickEl = (el) => act(async () => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true })); await tick(20); });

test("financials: the month filter is a custom picker, never the native <input type=month>", async () => {
  ME = TEACHER;
  const m = await mount("/app/financials", React.createElement(AppRoutes));
  try {
    assert.equal(m.container.querySelector("input[type=month]"), null, "native month input still used");
    const trigger = m.container.querySelector(".dtp-trigger.month-inp");
    assert.ok(trigger, "month picker trigger missing");
    assert.ok(!/Invalid|undefined|NaN/.test(trigger.textContent), "month label is broken: " + trigger.textContent);
    await clickEl(trigger);
    assert.ok(w.document.querySelector(".dtp-sheet .dtp-months"), "month grid did not open");
    assert.equal(w.document.querySelectorAll(".dtp-months button").length, 12);
    await clickEl(w.document.querySelectorAll(".dtp-months button:not(:disabled)")[0]);
    assert.equal(w.document.querySelector(".dtp-sheet"), null, "picking a month should close the picker");
  } finally { await m.done(); }
});

test("groups: the weekly-slot time is a custom picker, never the native <input type=time>", async () => {
  ME = TEACHER;
  const m = await mount("/app/groups", React.createElement(AppRoutes));
  try {
    const btn = [...m.container.querySelectorAll("button")].find((b) => b.textContent.includes("المواعيد"));
    assert.ok(btn, "schedules button missing");
    await clickEl(btn);
    assert.ok(w.document.querySelector(".modal"), "schedule dialog did not open");
    assert.equal(w.document.querySelector("input[type=time]"), null, "native time input still used");
    const trigger = w.document.querySelector(".modal .dtp-trigger");
    assert.ok(trigger, "time picker trigger missing");
    await clickEl(trigger);
    assert.equal(w.document.querySelectorAll(".dtp-sheet .dtp-chips button").length, 24, "12 hours + 12 minute chips");
  } finally { await m.done(); }
});

test("every dialog reserves its close-button room on the inline-END edge (RTL-safe)", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("../auth/auth.css", import.meta.url), "utf8");
  const head = css.slice(css.indexOf(".modal-head{"), css.indexOf("}", css.indexOf(".modal-head{")));
  assert.match(head, /padding-inline:\s*26px 62px/, "modal header must use logical padding");
  assert.doesNotMatch(head, /padding:\s*\d+px \d+px \d+px \d+px/, "physical 4-value padding puts the room on the wrong side in RTL");
});

test("guardian portal renders one child's read-only follow-up and never offers a write", async () => {
  sessionStorage.setItem("madar.parent.session", JSON.stringify({
    children: [{ token: "t1", student_name: "ابن", grade: "أول" }], active: 0, expires_at: Date.now() + 60000 }));
  const m = await mount("/parent", React.createElement(ParentPortal));
  try {
    const text = m.container.textContent;
    assert.match(text, /متابعة ابن/);
    assert.match(text, /المدفوعات/);
    assert.doesNotMatch(text, /Invalid|undefined|NaN/);
    assert.equal(m.container.querySelectorAll("input, textarea, form").length, 0, "guardian portal must be read-only");
  } finally { sessionStorage.removeItem("madar.parent.session"); await m.done(); }
});

test("guardian portal with no session sends the visitor to the guardian login", async () => {
  sessionStorage.removeItem("madar.parent.session");
  const { Routes, Route } = await import("react-router-dom");
  const m = await mount("/parent", React.createElement(Routes, null,
    React.createElement(Route, { path: "/parent", element: React.createElement(ParentPortal) }),
    React.createElement(Route, { path: "/auth/parent", element: React.createElement("div", null, "LOGIN-SCREEN") })));
  try { assert.match(m.container.textContent, /LOGIN-SCREEN/); } finally { await m.done(); }
});


test("attendance: a guest from another group is added with a target session; its note and carried marks show", async () => {
  ME = TEACHER;
  const calls = [];
  const origFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), init }); return origFetch(url, init); };
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  const click = (el) => act(async () => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true })); await tick(20); });
  try {
    await act(async () => {
      root.render(React.createElement(MemoryRouter, { initialEntries: ["/app/attendance?session=1"] },
        React.createElement(SessionProvider, null, React.createElement(EnvironmentProvider, null, React.createElement(AppRoutes)))));
    });
    await act(async () => { await tick(150); });
    assert.match(container.textContent, /ضيوف من مجموعات أخرى/);
    assert.match(container.textContent, /سيُسجَّل تلقائيًا في جلسة مجموعته/);
    assert.match(container.textContent, /مُرحَّل من زيارة G2/);

    const addBtn = [...container.querySelectorAll("button")].find((b) => b.textContent.includes("إضافة ضيف"));
    await click(addBtn);
    await act(async () => { await tick(60); });
    assert.match(w.document.body.textContent, /زائر جديد/);
    const confirm = [...w.document.querySelectorAll(".modal button")].find((b) => b.textContent.trim() === "إضافة");
    await click(confirm);
    await act(async () => { await tick(60); });
    const post = calls.find((c) => c.url.includes("/scheduling/sessions/1/guests/") && c.init?.method === "POST");
    assert.ok(post, "guest was not added");
    assert.deepEqual(JSON.parse(post.init.body), { enrollment_id: 8, home_session_id: 5 });
  } finally {
    globalThis.fetch = origFetch;
    await act(async () => { root.unmount(); });
    container.remove();
  }
});

test("sessions: delete asks for confirmation, then calls DELETE", async () => {
  ME = TEACHER;
  const calls = [];
  const origFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), init }); return origFetch(url, init); };
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  const click = (el) => act(async () => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true })); await tick(20); });
  try {
    await act(async () => {
      root.render(React.createElement(MemoryRouter, { initialEntries: ["/app/sessions"] },
        React.createElement(SessionProvider, null, React.createElement(EnvironmentProvider, null, React.createElement(AppRoutes)))));
    });
    await act(async () => { await tick(150); });
    const del = container.querySelector(".cal-session .mini-btn.danger");
    assert.ok(del, "delete button missing on the session card");
    await click(del);
    assert.ok(w.document.querySelector(".modal"), "confirmation did not open");
    assert.equal(calls.some((c) => c.init?.method === "DELETE"), false, "must not delete before confirming");
    const yes = [...w.document.querySelectorAll(".modal button")].find((b) => b.textContent.includes("حذف الجلسة"));
    await click(yes);
    await act(async () => { await tick(60); });
    assert.ok(calls.find((c) => c.init?.method === "DELETE" && /\/scheduling\/sessions\/\d+\/$/.test(new URL(c.url, "http://x").pathname)), "DELETE was not sent");
  } finally {
    globalThis.fetch = origFetch;
    await act(async () => { root.unmount(); });
    container.remove();
  }
});
test.after(async () => { await vite.close(); });
