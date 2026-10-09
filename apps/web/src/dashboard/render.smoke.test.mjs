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
  "/scheduling/sessions/1/roster/": { session: SESSION, students: [{ enrollment_id: 1, name: "أحمد", attendance: null, recitation: null }, { enrollment_id: 2, name: "سارة", attendance: "present", recitation: "studied" }], counts: {} },
  "/scheduling/schedules/": { count: 0, results: [] },
  "/financials/monthly/": { month: MONTH, rows: [{ enrollment_id: 1, name: "أحمد", grade: "أول", status: "unpaid", amount: "100.00", paid_at: null, note: "" }], summary: { students: 1, paid: 0, unpaid: 1, expected_total: "100.00", collected_total: "0.00", outstanding_total: "100.00" } },
  "/evaluation/monthly/": { month: MONTH, rows: [{ enrollment_id: 1, name: "أحمد", grade: "أول", rating: { value: 3, published: false }, state: "good", evidence: { present: 2, absent: 1, studied: 1, not_studied: 0 }, recommendation: null }] },
  "/content/": { count: 1, results: [{ id: 1, title: "درس", description: "", video: { provider: "youtube", embed_url: "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" }, targets: { grades: [{ id: 1, name: "أول" }], groups: [], students: [] }, published: false, published_at: null, created_at: NOW }] },
  "/notifications/": { count: 1, next: null, previous: null, results: [{ id: 1, type: "absent", type_label: "غياب", title: "t", body: "b", student: { id: 5, name: "أحمد" }, delivery_status: "failed", created_at: NOW }] },
  "/notifications/summary/": { pending: 1, sent: 2, failed: 1 },
  "/ai/operations/": { count: 0, results: [] },
  // ---- student area ----
  "/student/overview/": { environment: { name: "بيئة" }, student: { name: "أحمد" }, grade: "أول", groups: ["G1"],
    this_month: { month: MONTH, payment: "paid", state: "good", rating: 4, attendance: { present: 3, absent: 1 }, recitation: { studied: 2, not_studied: 1 } },
    unread_notifications: 2, latest_videos: [{ id: 1, title: "درس الخلية", description: "d", video: { provider: "youtube", embed_url: "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" }, can_quiz: true }] },
  "/student/attendance/": { summary: { present: 1, absent: 1 }, results: [{ id: 1, date: NOW, group: "G1", status: "present" }] },
  "/student/recitation/": { summary: { studied: 1, not_studied: 0 }, results: [{ id: 1, date: NOW, group: "G1", status: "studied" }] },
  "/student/payments/": { results: [{ month: MONTH, status: "unpaid" }] },
  "/student/evaluation/": { results: [{ month: MONTH, state: "at_risk", rating: 3 }] },
  "/student/videos/": { results: [{ id: 1, title: "درس الخلية", description: "وصف طويل للدرس", video: { provider: "youtube", embed_url: "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" }, can_quiz: true }] },
  "/student/notifications/": { results: [{ id: 1, type: "absent", type_label: "غياب", title: "تم تسجيل غيابك", body: "b", created_at: NOW, read: false }] },
  "/student/quizzes/": { results: [{ id: 1, title: "درس الخلية", created_at: NOW, questions: 2, score: null, total: null }, { id: 2, title: "درس 2", created_at: NOW, questions: 2, score: 1, total: 2 }] },
  "/student/quizzes/1/": { id: 1, title: "درس الخلية", submitted: false, questions: [{ q: "أكمل: _____ هي الوحدة", options: ["الخلية", "النواة"] }, { q: "س2", options: ["أ", "ب", "ج"] }] },
  "/student/quizzes/2/": { id: 2, title: "درس 2", submitted: true, score: 1, total: 2, questions: [{ q: "س1", options: ["أ", "ب"], answer_index: 0, chosen: 1, explanation: "ش" }, { q: "س2", options: ["أ", "ب"], answer_index: 1, chosen: 1, explanation: "" }] },
  "/scheduling/scan/resolve/": { enrollment_id: 1, name: "طالب", grade: "أول", is_active: true,
    session_id: 1, attendance: null, recitation: null, month: "2026-10", fee_amount: "150.00",
    payment_status: "unpaid" },
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

const STUDENT_PAGES = ["/learn", "/learn/records", "/learn/videos", "/learn/quizzes", "/learn/quizzes/1", "/learn/quizzes/2", "/learn/assistant", "/learn/notifications", "/learn/settings"];
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
test.after(async () => { await vite.close(); });
