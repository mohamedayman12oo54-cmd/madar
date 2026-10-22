// Render smoke test: mounts the REAL router + providers + every dashboard page
// in jsdom, against a mocked API, and fails on any render/effect crash
// (undefined variable, bad import, wrong prop shape...). A production build
// cannot catch these — they only show up as a blank page in the browser.
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
// Expose the rest of the browser surface (SVGElement, HTMLInputElement, ...) that libraries probe for.
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
globalThis.IntersectionObserver =
  globalThis.IntersectionObserver ||
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
w.IntersectionObserver = globalThis.IntersectionObserver;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const NOW = new Date().toISOString();
const MONTH = NOW.slice(0, 7);
const ENROLLMENT = {
  id: 1,
  student: { id: 5, name: "أحمد", phone: "201001234567" },
  grade: { id: 1, name: "أول", fee_amount: "100.00" },
  groups: [{ id: 1, name: "G1" }],
  academic_year: "2026 / 2027",
  is_active: true,
  parent_name: "ولي",
  parent_phone: "201001234568",
  can_edit_phone: true,
  created_at: NOW,
};
const SESSION = {
  id: 1,
  group: { id: 1, name: "G1", grade_id: 1 },
  scheduled_at: NOW,
  status: "open",
  reopened_count: 0,
};
const TEACHER = {
  id: 1,
  role: "teacher",
  name: "مدرّس",
  email: "t@example.com",
  phone: "201001234567",
};
const STUDENT = { id: 5, role: "student", name: "أحمد", email: null, phone: "201001234567" };
let ME = TEACHER;
const inDays = (d) => new Date(Date.now() + d * 864e5).toISOString();
const trialSub = (daysLeft) => ({
  plan_key: null,
  trial_end: inDays(daysLeft),
  current_period_end: null,
  cancel_at_period_end: false,
  pending_checkout: null,
  entitlement: {
    access_granted: true,
    basis: "trial",
    reason_code: "trial_active",
    capabilities: [],
    student_cap: 250,
  },
});
const paidSub = (extra = {}) => ({
  plan_key: "plan_2",
  trial_end: null,
  current_period_end: inDays(12),
  cancel_at_period_end: false,
  pending_checkout: null,
  entitlement: {
    access_granted: true,
    basis: "paid_active",
    reason_code: "paid_active",
    capabilities: [],
    student_cap: 800,
  },
  ...extra,
});
let SUB = trialSub(10);
let CHECKOUT_RESPONSE = { session_url: "https://payments.kashier.io/session/abc", attempt_id: 7 };
let RETURN_STATUS = { attempt_id: 7, status: "pending" };
const ROUTES = {
  "/auth/me/": () => ME,
  "/environments/context/": { id: 1, name: "بيئة", initials: "ب", role: "owner" },
  "/environments/current/": {
    id: 1,
    name: "بيئة",
    subject_stage: "رياضيات",
    academic_year: "2026 / 2027",
    created_at: NOW,
  },
  "/environments/overview/": {
    environment: { name: "بيئة", academic_year: "2026 / 2027" },
    students: { active: 2, inactive: 1 },
    structure: { grades: 1, groups: 1 },
    sessions: {
      today: [{ id: 1, group: "G1", scheduled_at: NOW, status: "open" }],
      open: 1,
      upcoming: [{ id: 2, group: "G1", scheduled_at: NOW, status: "planned" }],
    },
    payments: {
      month: MONTH,
      paid: 1,
      students: 2,
      expected_total: "200.00",
      collected_total: "100.00",
      outstanding_total: "100.00",
    },
    notifications: { pending: 1, failed: 1 },
  },
  "/academics/grades/": {
    count: 1,
    results: [{ id: 1, name: "أول", fee_amount: "100.00", order: 0 }],
  },
  "/academics/groups/": {
    count: 1,
    results: [{ id: 1, name: "G1", grade_id: 1, student_count: 2 }],
  },
  "/academics/enrollments/": { count: 1, next: null, previous: null, results: [ENROLLMENT] },
  "/scheduling/sessions/": {
    count: 3,
    results: [
      SESSION,
      {
        id: 2,
        group: { id: 1, name: "G1", grade_id: 1 },
        scheduled_at: new Date(Date.now() + 2 * 864e5).toISOString(),
        status: "planned",
        reopened_count: 0,
      },
      {
        id: 3,
        group: { id: 2, name: "G2", grade_id: 1 },
        scheduled_at: new Date(Date.now() - 864e5).toISOString(),
        status: "closed",
        reopened_count: 1,
      },
    ],
  },
  "/scheduling/sessions/1/checkin/": () => ({
    link: { token: "tok123", code: "123456", expires_at: inDays(0.1), checked_in_count: 3 },
  }),
  "/scheduling/checkin/tok123/": {
    environment: "بيئة",
    group: "G1",
    scheduled_at: NOW,
  },
  "/scheduling/sessions/1/roster/": {
    session: SESSION,
    students: [
      { enrollment_id: 1, name: "أحمد", attendance: null, recitation: null },
      {
        enrollment_id: 2,
        name: "سارة",
        attendance: "present",
        recitation: "studied",
        carried_from: { session_id: 9, scheduled_at: NOW, group: "G2" },
      },
    ],
    guests: [
      {
        enrollment_id: 7,
        name: "ضيف",
        attendance: "present",
        recitation: null,
        applied: false,
        home_session: { id: 5, scheduled_at: NOW, group: "G2", status: "planned" },
      },
    ],
    counts: {},
  },
  "/scheduling/sessions/1/guest-candidates/": {
    results: [
      {
        enrollment_id: 8,
        name: "زائر جديد",
        grade: "أول",
        groups: ["G2"],
        upcoming: [{ id: 5, scheduled_at: NOW, group: "G2", status: "planned" }],
      },
    ],
  },
  "/scheduling/sessions/1/guests/": {
    enrollment_id: 8,
    name: "زائر جديد",
    attendance: null,
    recitation: null,
    applied: false,
    home_session: null,
  },
  "/scheduling/sessions/1/": {},
  "/scheduling/schedules/": { count: 0, results: [] },
  "/financials/monthly/": {
    month: MONTH,
    rows: [
      {
        enrollment_id: 1,
        name: "أحمد",
        grade: "أول",
        status: "unpaid",
        amount: "100.00",
        paid_at: null,
        note: "",
      },
    ],
    summary: {
      students: 1,
      paid: 0,
      unpaid: 1,
      expected_total: "100.00",
      collected_total: "0.00",
      outstanding_total: "100.00",
    },
  },
  "/evaluation/monthly/": {
    month: MONTH,
    rows: [
      {
        enrollment_id: 1,
        name: "أحمد",
        grade: "أول",
        rating: { value: 3, published: false },
        state: "good",
        evidence: { present: 2, absent: 1, studied: 1, not_studied: 0 },
        recommendation: null,
      },
    ],
  },
  "/content/": {
    count: 3,
    results: [
      // published upload
      {
        id: 1,
        title: "درس منشور",
        description: "",
        source: "upload",
        original_filename: "a.mp4",
        file_size: 1024,
        video: null,
        targets: { grades: [{ id: 1, name: "أول" }], groups: [], students: [] },
        published: true,
        published_at: NOW,
        created_at: NOW,
      },
      // draft WITH a file but no targets
      {
        id: 2,
        title: "مسودة بلا مستهدفين",
        description: "",
        source: "upload",
        original_filename: "b.mp4",
        file_size: 1024,
        video: null,
        targets: { grades: [], groups: [], students: [] },
        published: false,
        published_at: null,
        created_at: NOW,
      },
      // draft with NO file yet
      {
        id: 3,
        title: "مسودة بلا فيديو",
        description: "",
        source: "external",
        video: null,
        targets: { grades: [{ id: 1, name: "أول" }], groups: [], students: [] },
        published: false,
        published_at: null,
        created_at: NOW,
      },
    ],
  },
  "/notifications/": {
    count: 1,
    next: null,
    previous: null,
    results: [
      {
        id: 1,
        type: "absent",
        type_label: "غياب",
        title: "t",
        body: "b",
        student: { id: 5, name: "أحمد" },
        delivery_status: "failed",
        created_at: NOW,
      },
      {
        id: 2,
        type: "new_video",
        type_label: "فيديو جديد",
        title: "فيديو جديد",
        body: "",
        student: { id: 5, name: "أحمد" },
        content_item: { id: 1, title: "درس الخلية", grades: ["أول"], groups: ["G1"] },
        delivery_status: "sent",
        created_at: NOW,
      },
    ],
  },
  "/notifications/summary/": { pending: 1, sent: 2, failed: 1 },
  "/ai/operations/": { count: 0, results: [] },
  // ---- billing ----
  "/billing/plans/": {
    count: 3,
    results: [
      {
        key: "plan_1",
        name: "الباقة الأولى",
        price_minor_units: 100000,
        currency: "EGP",
        max_students: 400,
      },
      {
        key: "plan_2",
        name: "الباقة الثانية",
        price_minor_units: 150000,
        currency: "EGP",
        max_students: 800,
      },
      {
        key: "plan_3",
        name: "الباقة الثالثة",
        price_minor_units: 200000,
        currency: "EGP",
        max_students: null,
      },
    ],
  },
  "/billing/subscription/": () => SUB,
  "/billing/history/": {
    count: 1,
    next: null,
    previous: null,
    results: [
      {
        id: 1,
        status: "succeeded",
        amount_minor_units: 150000,
        currency: "EGP",
        created_at: NOW,
        period_start: NOW,
        period_end: NOW,
      },
    ],
  },
  "/billing/checkout/": () => CHECKOUT_RESPONSE,
  "/billing/checkout/return/": () => RETURN_STATUS,
  "/billing/subscription/cancel/": {
    cancel_at_period_end: true,
    renewal_already_in_progress: false,
    renewal_attempt_status: null,
  },
  // ---- student area ----
  "/student/overview/": {
    environment: { name: "بيئة" },
    student: { badge_code: "WK38G4", name: "أحمد" },
    grade: "أول",
    groups: ["G1"],
    this_month: {
      month: MONTH,
      payment: "paid",
      state: "good",
      rating: 4,
      attendance: { present: 3, absent: 1 },
      recitation: { studied: 2, not_studied: 1 },
    },
    unread_notifications: 2,
    latest_videos: [
      {
        id: 1,
        title: "درس الخلية",
        description: "d",
        video: {
          provider: "youtube",
          embed_url: "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        },
        can_quiz: true,
      },
    ],
  },
  "/student/attendance/": {
    summary: { present: 1, absent: 1 },
    results: [{ id: 1, date: NOW, group: "G1", status: "present" }],
  },
  "/student/recitation/": {
    summary: { studied: 1, not_studied: 0 },
    results: [{ id: 1, date: NOW, group: "G1", status: "studied" }],
  },
  "/student/payments/": {
    results: [
      {
        month: MONTH,
        status: "paid",
        receipt: {
          student_name: "أحمد",
          grade: "أول",
          groups: ["G1"],
          teacher_environment: "بيئة",
          month: MONTH,
          amount: "100.00",
          paid_at: NOW,
          reference: "MDR-1-202610",
          note: "",
        },
      },
    ],
  },
  "/student/evaluation/": {
    results: [{ month: "2026-10", state: "good", rating: 4 }],
    notes: [{ id: 1, body: "ملاحظة من المعلّم", created_at: NOW, updated_at: NOW }],
  },
  "/student/videos/1/": {
    id: 1,
    title: "درس الخلية",
    description: "وصف طويل للدرس",
    source: "external",
    video: { provider: "youtube", embed_url: "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" },
    can_quiz: true,
    progress: null,
  },
  "/student/videos/": {
    results: [
      {
        id: 1,
        title: "درس الخلية",
        description: "وصف طويل للدرس",
        video: {
          provider: "youtube",
          embed_url: "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        },
        can_quiz: true,
      },
    ],
  },
  "/student/notifications/": {
    results: [
      {
        id: 1,
        type: "absent",
        type_label: "غياب",
        title: "تم تسجيل غيابك",
        body: "b",
        created_at: NOW,
        read: false,
      },
    ],
  },
  "/student/quizzes/": {
    results: [
      { id: 1, title: "درس الخلية", created_at: NOW, questions: 2, score: null, total: null },
      { id: 2, title: "درس 2", created_at: NOW, questions: 2, score: 1, total: 2 },
    ],
  },
  "/student/quizzes/1/": {
    id: 1,
    title: "درس الخلية",
    submitted: false,
    questions: [
      { q: "أكمل: _____ هي الوحدة", options: ["الخلية", "النواة"] },
      { q: "س2", options: ["أ", "ب", "ج"] },
    ],
  },
  "/student/quizzes/2/": {
    id: 2,
    title: "درس 2",
    submitted: true,
    score: 1,
    total: 2,
    questions: [
      { q: "س1", options: ["أ", "ب"], answer_index: 0, chosen: 1, explanation: "ش" },
      { q: "س2", options: ["أ", "ب"], answer_index: 1, chosen: 1, explanation: "" },
    ],
  },
  "/scheduling/scan/resolve/": {
    enrollment_id: 1,
    name: "طالب",
    grade: "أول",
    is_active: true,
    session_id: 1,
    attendance: null,
    recitation: null,
    month: "2026-10",
    fee_amount: "150.00",
    payment_status: "unpaid",
  },
  "/scheduling/sessions/bulk/": { created: 1, skipped: [], results: [] },
  "/notifications/broadcasts/": {
    results: [
      {
        id: 1,
        title: "رسالة",
        body: "نص",
        recipient_count: 2,
        grades: ["أول"],
        groups: ["G1"],
        created_at: NOW,
      },
    ],
  },
  "/parent/overview/": {
    student: { name: "ابن", grade: "أول", teacher_environment: "بيئة" },
    attendance: {
      present: 2,
      absent: 1,
      total: 3,
      recent: [
        { date: NOW, status: "present" },
        { date: NOW, status: "absent" },
      ],
    },
    recitation: {
      studied: 1,
      not_studied: 1,
      total: 2,
      recent: [{ date: NOW, status: "studied" }],
    },
    payments: {
      this_month: { month: MONTH, status: "paid", amount: "200.00" },
      history: [{ month: MONTH, status: "paid", amount: "200.00", paid_at: NOW }],
    },
    evaluation: [{ month: MONTH, state: "good", state_label: "جيد", rating: 4 }],
    notifications: [
      {
        id: 1,
        type: "absent",
        type_label: "غياب",
        title: "تم تسجيل الغياب",
        body: "b",
        created_at: NOW,
      },
    ],
  },
  "/student/assistant/": {
    count: 1,
    results: [
      {
        id: 9,
        kind: "assistant",
        status: "completed",
        prompt: "ما هي الخلية؟",
        result: "إجابة",
        error: "",
        created_at: NOW,
        completed_at: NOW,
        sources: [{ id: 1, title: "الخلية", topic: "أحياء", version: 2 }],
      },
    ],
  },
};
globalThis.fetch = async (url) => {
  const path = new URL(String(url), "http://x").pathname.replace(/^\/api\/v1/, "");
  return new Response(
    JSON.stringify(typeof ROUTES[path] === "function" ? ROUTES[path]() : (ROUTES[path] ?? {})),
    { status: 200, headers: { "content-type": "application/json" } }
  );
};
localStorage.setItem("madar.tokens", JSON.stringify({ access: "a", refresh: "r" }));
localStorage.setItem("madar.activeEnvironment", "1");

const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { MemoryRouter } = await import("react-router-dom");
const { createServer } = await import("vite");
const vite = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "error",
  optimizeDeps: { noDiscovery: true },
});
const load = (p) => vite.ssrLoadModule(p);
const { SessionProvider } = await load("/src/state/session.jsx");
const { EnvironmentProvider } = await load("/src/state/environment.jsx");
const AppRoutes = (await load("/src/dashboard/AppRoutes.jsx")).default;
const StudentRoutes = (await load("/src/student/StudentRoutes.jsx")).default;
const ParentPortal = (await load("/src/parent/ParentPortal.jsx")).default;

const STUDENT_PAGES = [
  "/learn",
  "/learn/records",
  "/learn/videos",
  "/learn/videos/1",
  "/learn/quizzes",
  "/learn/quizzes/1",
  "/learn/quizzes/2",
  "/learn/assistant",
  "/learn/notifications",
  "/learn/settings",
];
const PAGES = [
  "/app",
  "/app/students",
  "/app/groups",
  "/app/sessions",
  "/app/attendance",
  "/app/attendance?session=1",
  "/app/scan",
  "/app/evaluation",
  "/app/financials",
  "/app/content",
  "/app/notifications",
  "/app/billing",
  "/app/settings",
];
const tick = (ms = 40) => new Promise((r) => setTimeout(r, ms));

for (const [path, Routes_, who] of [
  ...PAGES.map((p) => [p, AppRoutes, TEACHER]),
  ...STUDENT_PAGES.map((p) => [p, StudentRoutes, STUDENT]),
]) {
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
        root.render(
          React.createElement(
            MemoryRouter,
            { initialEntries: [path] },
            React.createElement(
              SessionProvider,
              null,
              React.createElement(EnvironmentProvider, null, React.createElement(Routes_))
            )
          )
        );
      });
      await act(async () => {
        await tick(120);
      });
      await act(async () => {
        await tick(60);
      });
      assert.deepEqual(errors, [], `console/runtime errors on ${path}:\n${errors.join("\n")}`);
      assert.ok(container.textContent.trim().length > 20, `page ${path} rendered blank`);
      assert.ok(
        container.querySelector("nav, aside, header, .dash-main, main"),
        `layout missing on ${path}`
      );
    } finally {
      await act(async () => {
        root.unmount();
      });
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
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return origFetch(url, init);
  };
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  const click = (el) =>
    act(async () => {
      el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
      await tick(20);
    });
  try {
    await act(async () => {
      root.render(
        React.createElement(
          MemoryRouter,
          { initialEntries: ["/app/sessions"] },
          React.createElement(
            SessionProvider,
            null,
            React.createElement(EnvironmentProvider, null, React.createElement(AppRoutes))
          )
        )
      );
    });
    await act(async () => {
      await tick(150);
    });
    const addBtn = [...container.querySelectorAll("button")].find((b) =>
      b.textContent.includes("جلسة إضافية")
    );
    assert.ok(addBtn, "add-session button missing");
    await click(addBtn);

    assert.ok(w.document.querySelector(".pick-chips"), "group chips missing");
    await click(w.document.querySelector(".pick-all")); // every group of the grade
    const submit = () => [...w.document.querySelectorAll(".modal button[type=submit]")][0];
    assert.equal(submit().disabled, false);

    await click(w.document.querySelector(".dtp-trigger")); // open the custom picker
    assert.ok(w.document.querySelector(".dtp-sheet"), "picker did not open");
    assert.equal(
      w.document.querySelector("input[type=datetime-local]"),
      null,
      "native datetime input still used"
    );
    await click(w.document.querySelectorAll(".dtp-day")[9]);
    await act(async () => {
      w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      await tick(20);
    });
    assert.equal(w.document.querySelector(".dtp-sheet"), null, "Esc should close the picker");
    assert.ok(w.document.querySelector(".modal"), "Esc must not also close the dialog");

    await click(submit());
    await act(async () => {
      await tick(60);
    });
    const post = calls.find((c) => c.url.includes("/scheduling/sessions/bulk/"));
    assert.ok(post, "bulk create was not called");
    const body = JSON.parse(post.init.body);
    assert.equal(body.grade_id, 1);
    assert.deepEqual(body.group_ids, [1]);
    assert.match(body.scheduled_at, /^\d{4}-\d{2}-\d{2}T/);
  } finally {
    globalThis.fetch = origFetch;
    await act(async () => {
      root.unmount();
    });
    container.remove();
  }
});
async function mount(path, element) {
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      React.createElement(
        MemoryRouter,
        { initialEntries: [path] },
        React.createElement(
          SessionProvider,
          null,
          React.createElement(EnvironmentProvider, null, element)
        )
      )
    );
  });
  await act(async () => {
    await tick(150);
  });
  return {
    container,
    root,
    done: async () => {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    },
  };
}
const clickEl = (el) =>
  act(async () => {
    el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
    await tick(20);
  });

test("financials: the month filter is a custom picker, never the native <input type=month>", async () => {
  ME = TEACHER;
  const m = await mount("/app/financials", React.createElement(AppRoutes));
  try {
    assert.equal(
      m.container.querySelector("input[type=month]"),
      null,
      "native month input still used"
    );
    const trigger = m.container.querySelector(".dtp-trigger.month-inp");
    assert.ok(trigger, "month picker trigger missing");
    assert.ok(
      !/Invalid|undefined|NaN/.test(trigger.textContent),
      "month label is broken: " + trigger.textContent
    );
    await clickEl(trigger);
    assert.ok(w.document.querySelector(".dtp-sheet .dtp-months"), "month grid did not open");
    assert.equal(w.document.querySelectorAll(".dtp-months button").length, 12);
    await clickEl(w.document.querySelectorAll(".dtp-months button:not(:disabled)")[0]);
    assert.equal(
      w.document.querySelector(".dtp-sheet"),
      null,
      "picking a month should close the picker"
    );
  } finally {
    await m.done();
  }
});

test("groups: the weekly-slot time is a custom picker, never the native <input type=time>", async () => {
  ME = TEACHER;
  const m = await mount("/app/groups", React.createElement(AppRoutes));
  try {
    const btn = [...m.container.querySelectorAll("button")].find((b) =>
      b.textContent.includes("المواعيد")
    );
    assert.ok(btn, "schedules button missing");
    await clickEl(btn);
    assert.ok(w.document.querySelector(".modal"), "schedule dialog did not open");
    assert.equal(
      w.document.querySelector("input[type=time]"),
      null,
      "native time input still used"
    );
    const trigger = w.document.querySelector(".modal .dtp-trigger");
    assert.ok(trigger, "time picker trigger missing");
    await clickEl(trigger);
    assert.equal(
      w.document.querySelectorAll(".dtp-sheet .dtp-chips button").length,
      24,
      "12 hours + 12 minute chips"
    );
  } finally {
    await m.done();
  }
});

test("every dialog reserves its close-button room on the inline-END edge (RTL-safe)", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("../auth/auth.css", import.meta.url), "utf8");
  // Formatting-agnostic: find the `.modal-head { ... }` rule however it is laid out.
  const head = css.match(/\.modal-head\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(head, /padding-inline:\s*26px 62px/, "modal header must use logical padding");
  assert.doesNotMatch(
    head,
    /padding:\s*\d+px \d+px \d+px \d+px/,
    "physical 4-value padding puts the room on the wrong side in RTL"
  );
});

test("guardian portal renders one child's read-only follow-up and never offers a write", async () => {
  sessionStorage.setItem(
    "madar.parent.session",
    JSON.stringify({
      children: [{ token: "t1", student_name: "ابن", grade: "أول" }],
      active: 0,
      expires_at: Date.now() + 60000,
    })
  );
  const m = await mount("/parent", React.createElement(ParentPortal));
  try {
    const text = m.container.textContent;
    assert.match(text, /متابعة ابن/);
    assert.match(text, /المدفوعات/);
    assert.doesNotMatch(text, /Invalid|undefined|NaN/);
    assert.equal(
      m.container.querySelectorAll("input, textarea, form").length,
      0,
      "guardian portal must be read-only"
    );
  } finally {
    sessionStorage.removeItem("madar.parent.session");
    await m.done();
  }
});

test("guardian portal with no session sends the visitor to the guardian login", async () => {
  sessionStorage.removeItem("madar.parent.session");
  const { Routes, Route } = await import("react-router-dom");
  const m = await mount(
    "/parent",
    React.createElement(
      Routes,
      null,
      React.createElement(Route, { path: "/parent", element: React.createElement(ParentPortal) }),
      React.createElement(Route, {
        path: "/auth/parent",
        element: React.createElement("div", null, "LOGIN-SCREEN"),
      })
    )
  );
  try {
    assert.match(m.container.textContent, /LOGIN-SCREEN/);
  } finally {
    await m.done();
  }
});

test("attendance: a guest from another group is added with a target session; its note and carried marks show", async () => {
  ME = TEACHER;
  const calls = [];
  const origFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return origFetch(url, init);
  };
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  const click = (el) =>
    act(async () => {
      el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
      await tick(20);
    });
  try {
    await act(async () => {
      root.render(
        React.createElement(
          MemoryRouter,
          { initialEntries: ["/app/attendance?session=1"] },
          React.createElement(
            SessionProvider,
            null,
            React.createElement(EnvironmentProvider, null, React.createElement(AppRoutes))
          )
        )
      );
    });
    await act(async () => {
      await tick(150);
    });
    assert.match(container.textContent, /ضيوف من مجموعات أخرى/);
    assert.match(container.textContent, /سيُسجَّل تلقائيًا في جلسة مجموعته/);
    assert.match(container.textContent, /مُرحَّل من زيارة G2/);

    const addBtn = [...container.querySelectorAll("button")].find((b) =>
      b.textContent.includes("إضافة ضيف")
    );
    await click(addBtn);
    await act(async () => {
      await tick(60);
    });
    assert.match(w.document.body.textContent, /زائر جديد/);
    const confirm = [...w.document.querySelectorAll(".modal button")].find(
      (b) => b.textContent.trim() === "إضافة"
    );
    await click(confirm);
    await act(async () => {
      await tick(60);
    });
    const post = calls.find(
      (c) => c.url.includes("/scheduling/sessions/1/guests/") && c.init?.method === "POST"
    );
    assert.ok(post, "guest was not added");
    assert.deepEqual(JSON.parse(post.init.body), { enrollment_id: 8, home_session_id: 5 });
  } finally {
    globalThis.fetch = origFetch;
    await act(async () => {
      root.unmount();
    });
    container.remove();
  }
});

test("sessions: delete asks for confirmation, then calls DELETE", async () => {
  ME = TEACHER;
  const calls = [];
  const origFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return origFetch(url, init);
  };
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  const click = (el) =>
    act(async () => {
      el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
      await tick(20);
    });
  try {
    await act(async () => {
      root.render(
        React.createElement(
          MemoryRouter,
          { initialEntries: ["/app/sessions"] },
          React.createElement(
            SessionProvider,
            null,
            React.createElement(EnvironmentProvider, null, React.createElement(AppRoutes))
          )
        )
      );
    });
    await act(async () => {
      await tick(150);
    });
    const del = container.querySelector(".cal-session .mini-btn.danger");
    assert.ok(del, "delete button missing on the session card");
    await click(del);
    assert.ok(w.document.querySelector(".modal"), "confirmation did not open");
    assert.equal(
      calls.some((c) => c.init?.method === "DELETE"),
      false,
      "must not delete before confirming"
    );
    const yes = [...w.document.querySelectorAll(".modal button")].find((b) =>
      b.textContent.includes("حذف الجلسة")
    );
    await click(yes);
    await act(async () => {
      await tick(60);
    });
    assert.ok(
      calls.find(
        (c) =>
          c.init?.method === "DELETE" &&
          /\/scheduling\/sessions\/\d+\/$/.test(new URL(c.url, "http://x").pathname)
      ),
      "DELETE was not sent"
    );
  } finally {
    globalThis.fetch = origFetch;
    await act(async () => {
      root.unmount();
    });
    container.remove();
  }
});
test.after(async () => {
  await vite.close();
});

// ---------------------------------------------------------------- billing behaviour
const BillingPage = (await load("/src/dashboard/BillingPage.jsx")).default;
async function mountBilling(
  path,
  element = React.createElement(BillingPage, { redirect: (u) => REDIRECTS.push(u) })
) {
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(React.createElement(MemoryRouter, { initialEntries: [path] }, element));
  });
  await act(async () => {
    await tick(120);
  });
  return {
    container,
    unmount: async () => {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    },
  };
}
const REDIRECTS = [];
const buttonWith = (c, text) =>
  [...c.querySelectorAll("button")].find((b) => b.textContent.includes(text));
const press = (el) =>
  act(async () => {
    el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
    await tick(60);
  });

test("billing: the trial shows its remaining days and the plan ladder with server prices and caps", async () => {
  ME = TEACHER;
  SUB = trialSub(5);
  const { container, unmount } = await mountBilling("/app/billing");
  try {
    const text = container.textContent;
    assert.match(text, /أنت في الفترة التجريبية/);
    assert.ok(container.querySelector(".bl-ring-fg"), "depleting ring");
    assert.equal(container.querySelectorAll(".bl-timer b").length, 3, "days:hours:minutes timer");
    assert.equal(container.querySelector(".bl-days-n").textContent, "٥");
    assert.match(text, /١٬٠٠٠ ج\.م/);
    assert.match(text, /١٬٥٠٠ ج\.م/);
    assert.match(text, /٢٬٠٠٠ ج\.م/);
    assert.match(text, /بدون حد/);
    assert.equal(container.querySelectorAll(".bl-plan").length, 3);
    assert.ok(buttonWith(container, "اشترك في الباقة الأولى"));
    assert.match(text, /لا نخزّن رقم بطاقتك/);
  } finally {
    await unmount();
  }
});

test("billing: choosing a plan sends ONLY the plan key and redirects to the trusted payment page", async () => {
  ME = TEACHER;
  SUB = trialSub(10);
  REDIRECTS.length = 0;
  const calls = [];
  const orig = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return orig(url, init);
  };
  const { container, unmount } = await mountBilling("/app/billing");
  try {
    await press(buttonWith(container, "اشترك في الباقة الثانية"));
    const post = calls.find(
      (c) => c.url.includes("/billing/checkout/") && c.init?.method === "POST"
    );
    assert.ok(post, "checkout was not called");
    assert.deepEqual(JSON.parse(post.init.body), { plan_key: "plan_2" }); // no amount, no environment id
    assert.deepEqual(REDIRECTS, ["https://payments.kashier.io/session/abc"]);
  } finally {
    globalThis.fetch = orig;
    await unmount();
  }
});

test("billing: a checkout URL on an untrusted host is never followed", async () => {
  ME = TEACHER;
  SUB = trialSub(10);
  REDIRECTS.length = 0;
  for (const evil of [
    "https://evil.example.com/pay",
    "http://payments.kashier.io/x",
    "javascript:alert(1)",
  ]) {
    CHECKOUT_RESPONSE = { session_url: evil, attempt_id: 7 };
    const { container, unmount } = await mountBilling("/app/billing");
    try {
      await press(buttonWith(container, "اشترك في الباقة الأولى"));
      assert.deepEqual(REDIRECTS, [], `followed ${evil}`);
      assert.match(container.textContent, /لم يُسحب أي مبلغ/);
    } finally {
      await unmount();
    }
  }
  CHECKOUT_RESPONSE = { session_url: "https://payments.kashier.io/session/abc", attempt_id: 7 };
});

test("billing: coming back from the payment page with ?status=success does NOT show success while the server says pending", async () => {
  ME = TEACHER;
  SUB = trialSub(10);
  RETURN_STATUS = { attempt_id: 7, status: "pending" };
  const { container, unmount } = await mountBilling(
    "/app/billing?attempt_id=7&status=success&paid=true"
  );
  try {
    assert.match(container.textContent, /بانتظار تأكيد الدفع/);
    assert.doesNotMatch(container.textContent, /تم الدفع وتفعيل اشتراكك/);
  } finally {
    await unmount();
  }
});

test("billing: success is shown only once the server reports the attempt succeeded, and a failure says nothing was charged", async () => {
  ME = TEACHER;
  SUB = trialSub(10);
  RETURN_STATUS = { attempt_id: 7, status: "succeeded" };
  let page = await mountBilling("/app/billing?attempt_id=7");
  try {
    assert.match(page.container.textContent, /تم الدفع وتفعيل اشتراكك/);
  } finally {
    await page.unmount();
  }
  RETURN_STATUS = { attempt_id: 7, status: "failed" };
  page = await mountBilling("/app/billing?attempt_id=7");
  try {
    assert.match(page.container.textContent, /لم يُسحب أي مبلغ/);
  } finally {
    await page.unmount();
    RETURN_STATUS = { attempt_id: 7, status: "pending" };
  }
});

test("billing: an active subscription disables every plan button and offers cancel; cancelling asks first", async () => {
  ME = TEACHER;
  SUB = paidSub();
  const calls = [];
  const orig = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return orig(url, init);
  };
  const { container, unmount } = await mountBilling("/app/billing");
  try {
    assert.match(container.textContent, /باقتك الحالية: الباقة الثانية/);
    assert.ok(container.querySelector(".bl-ring-fg"), "depleting ring");
    assert.equal(buttonWith(container, "باقتك الحالية").disabled, true);
    assert.equal(buttonWith(container, "اشترك في الباقة الأولى").disabled, true);
    assert.equal(buttonWith(container, "اشترك في الباقة الثالثة").disabled, true);
    await press(buttonWith(container, "إلغاء التجديد التلقائي"));
    assert.equal(
      calls.some((c) => c.url.includes("/cancel/")),
      false,
      "must confirm before cancelling"
    );
    await press(buttonWith(w.document.body, "نعم، ألغِ التجديد"));
    assert.ok(
      calls.find(
        (c) => c.url.includes("/billing/subscription/cancel/") && c.init?.method === "POST"
      )
    );
  } finally {
    globalThis.fetch = orig;
    await unmount();
  }
});

test("billing: a checkout in progress for another plan blocks switching but can be resumed", async () => {
  ME = TEACHER;
  SUB = {
    ...trialSub(10),
    pending_checkout: { attempt_id: 7, status: "initiated", plan_key: "plan_2" },
  };
  const { container, unmount } = await mountBilling("/app/billing");
  try {
    assert.ok(buttonWith(container, "أكمل الدفع"), "same plan can be resumed");
    assert.equal(buttonWith(container, "اشترك في الباقة الأولى").disabled, true);
    assert.equal(buttonWith(container, "اشترك في الباقة الثالثة").disabled, true);
  } finally {
    await unmount();
  }
});

test("billing: an expired trial explains that data is kept and plans are purchasable", async () => {
  ME = TEACHER;
  SUB = {
    plan_key: null,
    trial_end: inDays(-2),
    current_period_end: null,
    cancel_at_period_end: false,
    pending_checkout: null,
    entitlement: {
      access_granted: false,
      basis: "none",
      reason_code: "trial_expired",
      capabilities: [],
      student_cap: null,
    },
  };
  const { container, unmount } = await mountBilling("/app/billing");
  try {
    assert.match(container.textContent, /انتهت الفترة التجريبية/);
    assert.match(container.textContent, /بياناتك محفوظة/);
    assert.equal(buttonWith(container, "اشترك في الباقة الأولى").disabled, false);
  } finally {
    await unmount();
    SUB = trialSub(10);
  }
});

test("billing: the dashboard shows a strip only when action is needed, and never on the billing page itself", async () => {
  ME = TEACHER;
  SUB = trialSub(2);
  let page = await mountBilling(
    "/app",
    React.createElement(
      SessionProvider,
      null,
      React.createElement(EnvironmentProvider, null, React.createElement(AppRoutes))
    )
  );
  try {
    assert.ok(page.container.querySelector(".bl-strip"), "expected a trial-ending strip");
  } finally {
    await page.unmount();
  }
  SUB = trialSub(12);
  page = await mountBilling(
    "/app",
    React.createElement(
      SessionProvider,
      null,
      React.createElement(EnvironmentProvider, null, React.createElement(AppRoutes))
    )
  );
  try {
    assert.equal(page.container.querySelector(".bl-strip"), null, "no strip with 12 days left");
  } finally {
    await page.unmount();
  }
  SUB = trialSub(2);
  page = await mountBilling(
    "/app/billing",
    React.createElement(
      SessionProvider,
      null,
      React.createElement(EnvironmentProvider, null, React.createElement(AppRoutes))
    )
  );
  try {
    assert.equal(
      page.container.querySelector(".bl-strip"),
      null,
      "no duplicate strip on the billing page"
    );
  } finally {
    await page.unmount();
    SUB = trialSub(10);
  }
});

test("billing: a load failure shows an explanation, not a blank page", async () => {
  ME = TEACHER;
  const orig = globalThis.fetch;
  globalThis.fetch = async (url, init) =>
    String(url).includes("/billing/")
      ? new Response(JSON.stringify({ detail: "x", code: "server_error" }), { status: 500 })
      : orig(url, init);
  const { container, unmount } = await mountBilling("/app/billing");
  try {
    assert.match(container.textContent, /تعذّر/);
  } finally {
    globalThis.fetch = orig;
    await unmount();
  }
});

test("scanner: the self check-in panel shows the QR, the announced code and the live count", async () => {
  ME = TEACHER;
  const m = await mount("/app/scan", React.createElement(AppRoutes));
  try {
    const select = m.container.querySelector("select.inp");
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, "value").set;
      setter.call(select, "1");
      select.dispatchEvent(new w.Event("change", { bubbles: true }));
      await tick(250);
    });
    const text = m.container.textContent;
    assert.match(text, /تسجيل الحضور بالرمز/);
    assert.match(text, /123 456/, "the teacher must see the code to announce");
    assert.match(text, /سجّل حضوره:\s*3/);
    const img = m.container.querySelector(".ck-qr img");
    assert.ok(img, "a QR image is rendered");
    assert.match(img.getAttribute("src"), /^data:image\/svg\+xml/);
    assert.doesNotMatch(text, /undefined|NaN|Invalid/);
  } finally {
    await m.done();
  }
});

test("public check-in page: phone + 6-digit code form, no account data, attendance only", async () => {
  ME = TEACHER;
  const { Routes, Route } = await import("react-router-dom");
  const { CheckinPage } = await load("/src/auth/screens/Checkin.jsx");
  const m = await mount(
    "/checkin/tok123",
    React.createElement(
      Routes,
      null,
      React.createElement(Route, { path: "/checkin/:token", element: React.createElement(CheckinPage) })
    )
  );
  try {
    const text = m.container.textContent;
    assert.match(text, /تسجيل الحضور/);
    assert.match(text, /G1/);
    assert.equal(m.container.querySelectorAll("input[type=tel]").length, 1, "one phone field");
    assert.equal(m.container.querySelectorAll(".otp input").length, 6, "six code boxes");
    assert.match(text, /تسجّل حضورك فقط/);
    assert.doesNotMatch(text, /undefined|NaN|Invalid/);
  } finally {
    await m.done();
  }
});
