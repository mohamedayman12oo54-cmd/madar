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
      // a PDF (published) and a summary (draft) so the other sections render too
      {
        id: 11,
        kind: "pdf",
        title: "ملف PDF منشور",
        description: "",
        source: "upload",
        original_filename: "notes.pdf",
        file_size: 2048,
        has_document: true,
        has_body: false,
        video: null,
        targets: { grades: [{ id: 1, name: "أول" }], groups: [], students: [] },
        published: true,
        published_at: NOW,
        created_at: NOW,
      },
      {
        id: 12,
        kind: "summary",
        title: "ملخص مسودة",
        description: "",
        source: "external",
        has_document: false,
        has_body: true,
        video: null,
        targets: { grades: [], groups: [], students: [] },
        published: false,
        published_at: null,
        created_at: NOW,
      },
      // published upload
      {
        id: 1,
        kind: "video",
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
  // ---- exams (teacher: /exams/…, student: /student/exams/…) ----
  "/exams/": {
    results: [
      {
        id: 1, title: "امتحان الباب الأول", description: "", duration_minutes: 30, shuffle_questions: true,
        shuffle_choices: true, allow_back: false, max_violations: 3, reveal_answers: false, opens_at: null,
        closes_at: inDays(2), published_at: NOW, created_at: NOW, grade_ids: [1], group_ids: [], enrollment_ids: [],
        question_count: 2, attempt_count: 1, questions: [],
      },
      {
        id: 2, title: "امتحان مسودة", description: "", duration_minutes: 20, shuffle_questions: true,
        shuffle_choices: true, allow_back: false, max_violations: 3, reveal_answers: false, opens_at: null,
        closes_at: null, published_at: null, created_at: NOW, grade_ids: [1], group_ids: [], enrollment_ids: [],
        question_count: 3, attempt_count: 0, questions: [],
      },
    ],
  },
  "/exams/2/publish/": { id: 2, title: "امتحان مسودة", notified: 2, published_at: NOW },
  "/exams/1/results/": {
    exam_id: 1, title: "امتحان الباب الأول", average_percent: 66.7, finished: 2, total: 3,
    results: [
      {
        enrollment_id: 1, name: "أحمد", phone: "201001234567", status: "finished", score: 2, max_score: 3,
        percent: 66.7, end_reason: "submitted", violations: 2, submitted_at: NOW, best_attempt: 1,
        attempt_count: 1, reopened: false, can_reopen: true,
        violation_log: [{ type: "blur", at: NOW }, { type: "copy", at: NOW }],
        attempts: [{
          number: 1, status: "finished", score: 2, max_score: 3, percent: 66.7, end_reason: "submitted", violations: 2,
          violation_log: [{ type: "blur", at: NOW }, { type: "copy", at: NOW }], started_at: NOW, submitted_at: NOW,
        }],
      },
      {
        enrollment_id: 3, name: "منى", phone: "201001234569", status: "finished", score: 3, max_score: 3,
        percent: 100, end_reason: "submitted", violations: 0, submitted_at: NOW, best_attempt: 2,
        attempt_count: 2, reopened: false, can_reopen: true, violation_log: [],
        attempts: [
          { number: 1, status: "finished", score: 0, max_score: 3, percent: 0, end_reason: "violations", violations: 3,
            violation_log: [{ type: "hidden", at: NOW }], started_at: NOW, submitted_at: NOW },
          { number: 2, status: "finished", score: 3, max_score: 3, percent: 100, end_reason: "submitted", violations: 0,
            violation_log: [], started_at: NOW, submitted_at: NOW },
        ],
      },
      { enrollment_id: 2, name: "سارة", phone: "201001234568", status: "not_started", attempt_count: 0, attempts: [], reopened: false, can_reopen: false },
    ],
  },
  "/exams/1/reopen/": { enrollment_id: 1, reopened: true, already: false },
  "/student/exams/": {
    results: [
      {
        id: 1, title: "امتحان الباب الأول", description: "", duration_minutes: 30, question_count: 2,
        opens_at: NOW, closes_at: inDays(2), state: "open", max_violations: 3, allow_back: false,
        attempts: 0, can_retake: false, reopened: false,
      },
      {
        id: 2, title: "امتحان الباب الثاني", description: "", duration_minutes: 20, question_count: 4,
        opens_at: NOW, closes_at: null, state: "finished", max_violations: 3, allow_back: true,
        attempts: 2, can_retake: true, reopened: true, score: 3, max_score: 4, percent: 75,
      },
    ],
  },
  "/student/exams/1/start/": () => ({
    attempt_id: 1, number: 1, started_at: NOW, deadline_at: new Date(Date.now() + 30 * 60000).toISOString(), total: 2,
    current_index: 0, violations: 0, max_violations: 3, warnings_left: 3, allow_back: false, title: "امتحان الباب الأول",
    finished: false, end_reason: "",
  }),
  "/student/exams/1/question/0/": () => ({
    question_id: 1, index: 0, total: 2, text: "ما عاصمة مصر؟", points: 1, chosen_choice_id: null,
    choices: [{ id: 11, text: "القاهرة" }, { id: 12, text: "الإسكندرية" }],
    attempt_id: 1, number: 1, deadline_at: new Date(Date.now() + 30 * 60000).toISOString(), started_at: NOW, current_index: 0,
    violations: 0, max_violations: 3, warnings_left: 3, allow_back: false, title: "امتحان الباب الأول", finished: false, end_reason: "",
  }),
  "/student/exams/1/question/1/": () => ({
    question_id: 2, index: 1, total: 2, text: "كم يساوي ٢ + ٢؟", points: 2, chosen_choice_id: null,
    choices: [{ id: 21, text: "٣" }, { id: 22, text: "٤" }],
    attempt_id: 1, number: 1, deadline_at: new Date(Date.now() + 30 * 60000).toISOString(), started_at: NOW, current_index: 1,
    violations: 0, max_violations: 3, warnings_left: 3, allow_back: false, title: "امتحان الباب الأول", finished: false, end_reason: "",
  }),
  "/student/exams/1/answer/": { attempt_id: 1, finished: false },
  "/student/exams/1/violation/": (init) => ({
    attempt_id: 1, number: 1, violations: 1, max_violations: 3, warnings_left: 2, finished: false, end_reason: "",
    counted: true, last_violation: JSON.parse(init?.body || "{}").type || "blur",
  }),
  "/student/exams/1/submit/": { attempt_id: 1, finished: true, end_reason: "submitted" },
  "/student/exams/1/result/": {
    title: "امتحان الباب الأول", attempt_number: 1, score: 2, max_score: 3, percent: 66.7, end_reason: "submitted",
    violations: 1, attempts: 1, can_retake: false, best_score: 2, best_percent: 66.7, is_best: true,
  },
  "/student/exams/2/result/": {
    title: "امتحان الباب الثاني", attempt_number: 2, score: 2, max_score: 4, percent: 50, end_reason: "submitted",
    violations: 0, attempts: 2, can_retake: true, best_score: 3, best_percent: 75, is_best: false,
  },
  "/student/exams/2/question/0/": () => ({
    question_id: 7, index: 0, total: 4, text: "سؤال المحاولة الجديدة", points: 1, chosen_choice_id: null,
    choices: [{ id: 71, text: "أ" }, { id: 72, text: "ب" }],
    attempt_id: 5, number: 3, deadline_at: new Date(Date.now() + 20 * 60000).toISOString(), started_at: NOW, current_index: 0,
    violations: 0, max_violations: 3, warnings_left: 3, allow_back: true, title: "امتحان الباب الثاني", finished: false, end_reason: "",
  }),
  "/student/exams/2/start/": () => ({
    attempt_id: 5, number: 3, started_at: NOW, deadline_at: new Date(Date.now() + 20 * 60000).toISOString(), total: 4,
    current_index: 0, violations: 0, max_violations: 3, warnings_left: 3, allow_back: true, title: "امتحان الباب الثاني",
    finished: false, end_reason: "",
  }),
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
  "/student/materials/1/": {
    id: 1,
    kind: "summary",
    title: "ملخص الدرس",
    description: "وصف",
    body: "# عنوان\n- نقطة\n<script>alert(1)</script>",
    published_at: NOW,
  },
  "/student/materials/": {
    results: [
      { id: 1, kind: "summary", title: "ملخص الدرس", description: "", published_at: NOW },
      { id: 2, kind: "pdf", title: "ملف الدرس", description: "", original_filename: "a.pdf", file_size: 10, published_at: NOW },
    ],
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
      {
        id: 2, type: "new_exam", type_label: "امتحان جديد", title: "امتحان جديد", body: "تم نشر امتحان: الفصل الثالث",
        created_at: NOW, read: false, target: { kind: "exam", id: 1 },
      },
      {
        id: 3, type: "new_material", type_label: "ملف أو ملخص جديد", title: "ملخص جديد", body: "تمت إضافة: ملخص الدرس",
        created_at: NOW, read: true, target: { kind: "material", id: 1 },
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
globalThis.fetch = async (url, init) => {
  const path = new URL(String(url), "http://x").pathname.replace(/^\/api\/v1/, "");
  return new Response(
    JSON.stringify(typeof ROUTES[path] === "function" ? ROUTES[path](init) : (ROUTES[path] ?? {})),
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
  "/learn/materials/1",
  "/learn/exams/1",
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


// ----- teacher: PDF files + summaries & notes ---------------------------------------------------------
// The shared mock ignores query strings, so wrap it: `/content/?kind=…` returns only that kind, like the server.
const kindAwareContent = () => {
  const orig = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    const u = new URL(String(url), "http://x");
    if (u.pathname.endsWith("/content/") && (!init || !init.method || init.method === "GET")) {
      const kind = u.searchParams.get("kind");
      const rows = ROUTES["/content/"].results.filter((r) => (r.kind || "video") === (kind || r.kind || "video"));
      return new Response(JSON.stringify({ results: rows }), { status: 200, headers: { "content-type": "application/json" } });
    }
    return orig(url, init);
  };
  return { calls, restore: () => (globalThis.fetch = orig) };
};
const openTab = async (m, name) => {
  const tab = [...m.container.querySelectorAll("[role=tab]")].find((b) => b.textContent.includes(name));
  assert.ok(tab, `tab ${name}`);
  await clickEl(tab);
  await act(async () => {
    await tick(120);
  });
};
const typeInto = (el, value) =>
  act(async () => {
    const proto = el.tagName === "TEXTAREA" ? w.HTMLTextAreaElement.prototype : w.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new w.Event("input", { bubbles: true }));
    await tick(10);
  });

test("content hub (teacher): four sections, and each lists only its own kind", async () => {
  ME = TEACHER;
  const net = kindAwareContent();
  const m = await mount("/app/content", React.createElement(AppRoutes));
  try {
    const names = [...m.container.querySelectorAll("[role=tab]")].map((b) => b.textContent.trim());
    assert.deepEqual(names, ["الفيديوهات", "ملفات PDF", "الملخصات والملاحظات", "الامتحانات"]);
    assert.doesNotMatch(m.container.textContent, /ملف PDF منشور|ملخص مسودة/, "videos tab shows videos only");
    await openTab(m, "ملفات PDF");
    let text = m.container.textContent;
    assert.match(text, /ملف PDF منشور/);
    assert.match(text, /notes\.pdf/);
    assert.match(text, /٢ كيلوبايت/, "small files are shown in KB, not 0.00 MB");
    assert.doesNotMatch(text, /ملخص مسودة|درس منشور/);
    await openTab(m, "الملخصات");
    text = m.container.textContent;
    assert.match(text, /ملخص مسودة/);
    assert.doesNotMatch(text, /ملف PDF منشور|درس منشور/);
    assert.ok(net.calls.some((c) => c.url.includes("kind=pdf")) && net.calls.some((c) => c.url.includes("kind=summary")));
    assert.doesNotMatch(text, /undefined|NaN|Invalid/);
  } finally {
    net.restore();
    await m.done();
  }
});

test("content hub (teacher): a draft summary says what is still missing before it can be published", async () => {
  ME = TEACHER;
  const net = kindAwareContent();
  const m = await mount("/app/content", React.createElement(AppRoutes));
  try {
    await openTab(m, "الملخصات");
    assert.match(m.container.textContent, /حدّد الصف أو المجموعة/, "text is written, audience missing");
    assert.ok(buttonWith(m.container, "نشر"), "publish button on the draft");
  } finally {
    net.restore();
    await m.done();
  }
});

test("content hub (teacher): the summary form refuses an empty title or text and sends nothing", async () => {
  ME = TEACHER;
  const net = kindAwareContent();
  const m = await mount("/app/content", React.createElement(AppRoutes));
  try {
    await openTab(m, "الملخصات");
    await clickEl(buttonWith(m.container, "كتابة ملخص"));
    const modal = w.document.querySelector("[role=dialog]") || w.document.body;
    assert.ok(modal.querySelector("textarea"), "a text area for the summary");
    assert.match(modal.textContent, /«# عنوان»/, "formatting help is shown");
    await clickEl(buttonWith(modal, "حفظ"));
    assert.match(modal.textContent, /اكتب عنوانًا/);
    assert.match(modal.textContent, /اكتب نص الملخص/);
    assert.ok(!net.calls.some((c) => c.init?.method === "POST"), "nothing is posted");
  } finally {
    net.restore();
    await m.done();
  }
});

test("content hub (teacher): saving a summary posts its kind, title and text", async () => {
  ME = TEACHER;
  const net = kindAwareContent();
  const m = await mount("/app/content", React.createElement(AppRoutes));
  try {
    await openTab(m, "الملخصات");
    await clickEl(buttonWith(m.container, "كتابة ملخص"));
    const modal = w.document.querySelector("[role=dialog]") || w.document.body;
    await typeInto(modal.querySelector("input.inp"), "ملخص الباب الأول");
    await typeInto(modal.querySelector("textarea"), "# عنوان\n- نقطة");
    await clickEl(buttonWith(modal, "حفظ"));
    await act(async () => {
      await tick(100);
    });
    const post = net.calls.find((c) => c.init?.method === "POST" && /\/content\/$/.test(new URL(c.url, "http://x").pathname));
    assert.ok(post, "the item was created");
    const body = JSON.parse(post.init.body);
    assert.equal(body.kind, "summary");
    assert.equal(body.title, "ملخص الباب الأول");
    assert.equal(body.body, "# عنوان\n- نقطة");
  } finally {
    net.restore();
    await m.done();
  }
});

test("content hub (teacher): the PDF form takes a file with a size limit and validates the title", async () => {
  ME = TEACHER;
  const net = kindAwareContent();
  const m = await mount("/app/content", React.createElement(AppRoutes));
  try {
    await openTab(m, "ملفات PDF");
    await clickEl(buttonWith(m.container, "رفع ملف PDF"));
    const modal = w.document.querySelector("[role=dialog]") || w.document.body;
    const input = modal.querySelector("input[type=file]");
    assert.ok(input, "a file picker");
    assert.match(input.getAttribute("accept"), /pdf/);
    assert.match(modal.textContent, /٥٠ ميجابايت/, "the limit is stated");
    await clickEl(buttonWith(modal, "حفظ"));
    assert.match(modal.textContent, /اكتب عنوانًا/);
    assert.ok(!net.calls.some((c) => c.init?.method === "POST"));
  } finally {
    net.restore();
    await m.done();
  }
});

// ----- student: PDF files + summaries ----------------------------------------------------------------
test("student content: PDFs and summaries are cards with a type label, size, and one clear action", async () => {
  ME = STUDENT;
  const m = await mount("/learn/videos", React.createElement(StudentRoutes));
  try {
    const names = [...m.container.querySelectorAll("[role=tab]")].map((b) => b.textContent.trim());
    assert.deepEqual(names, ["فيديوهات", "ملفات PDF", "ملخصات وملاحظات", "امتحانات"]);
    await openTab(m, "ملفات PDF");
    const pdf = m.container.querySelector(".mat-card.is-pdf");
    assert.ok(pdf, "a PDF card");
    assert.match(pdf.textContent, /ملف الدرس/);
    assert.match(pdf.textContent, /ملف PDF/);
    assert.match(pdf.textContent, /فتح الملف/);
    await openTab(m, "ملخصات");
    const sum = m.container.querySelector(".mat-card.is-summary");
    assert.ok(sum, "a summary card");
    const go = sum.querySelector("a[href='/learn/materials/1']");
    assert.ok(go, "links to the reading page");
    assert.match(go.textContent, /قراءة الملخص/);
    assert.doesNotMatch(m.container.textContent, /undefined|NaN|Invalid/);
  } finally {
    await m.done();
  }
});

test("student content: the summary reader shows the date, renders text only, and can enlarge the font", async () => {
  ME = STUDENT;
  const m = await mount("/learn/materials/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(150);
    });
    const reader = m.container.querySelector(".summary-reader");
    assert.ok(reader);
    assert.match(reader.textContent, /نُشر في/);
    assert.equal(reader.querySelector("script"), null);
    assert.ok(!reader.classList.contains("is-big"));
    await clickEl(buttonWith(reader, "تكبير الخط"));
    assert.ok(m.container.querySelector(".summary-reader").classList.contains("is-big"));
    assert.ok(buttonWith(m.container, "تصغير الخط"), "the toggle flips");
  } finally {
    await m.done();
  }
});

// ----- summaries -----------------------------------------------------------------------------------
test("student summary: /learn/materials/:id opens the reading page and renders the text without executing markup", async () => {
  ME = STUDENT;
  const m = await mount("/learn/materials/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(120);
    });
    const text = m.container.textContent;
    assert.match(text, /ملخص الدرس/);
    assert.match(text, /عنوان/);
    assert.equal(m.container.querySelector("script"), null, "stored markup is shown as text, never parsed");
    assert.doesNotMatch(text, /undefined|NaN/);
  } finally {
    await m.done();
  }
});

// ----- exams ---------------------------------------------------------------------------------------
const recordFetch = () => {
  const calls = [];
  const orig = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return orig(url, init);
  };
  return { calls, restore: () => (globalThis.fetch = orig) };
};
const openExamsTab = async (m) => {
  const tab = [...m.container.querySelectorAll("[role=tab]")].find((b) => b.textContent.includes("امتحانات"));
  assert.ok(tab, "an exams tab exists");
  await clickEl(tab);
  await act(async () => {
    await tick(120);
  });
};
const startExam = async (m) => {
  await clickEl(buttonWith(m.container, "ابدأ الامتحان"));
  await act(async () => {
    await tick(150);
  });
};

test("exams (teacher): the exams tab lists each exam with its status and counts", async () => {
  ME = TEACHER;
  const m = await mount("/app/content", React.createElement(AppRoutes));
  try {
    await openExamsTab(m);
    const text = m.container.textContent;
    assert.match(text, /امتحان الباب الأول/);
    assert.match(text, /2 سؤال • 30 دقيقة • 1 محاولة/);
    assert.match(text, /منشور/);
    assert.match(text, /مسودة/);
    assert.doesNotMatch(text, /undefined|NaN|Invalid/);
    // a published exam that has attempts cannot be edited; a draft can be published
    assert.ok(buttonWith(m.container, "النتائج"), "results button on the published exam");
    assert.ok(buttonWith(m.container, "نشر"), "publish button on the draft");
  } finally {
    await m.done();
  }
});

test("exams (teacher): publishing a draft posts to the publish endpoint and reports how many were notified", async () => {
  ME = TEACHER;
  const rec = recordFetch();
  const m = await mount("/app/content", React.createElement(AppRoutes));
  try {
    await openExamsTab(m);
    await clickEl(buttonWith(m.container, "نشر"));
    await act(async () => {
      await tick(120);
    });
    assert.ok(rec.calls.some((c) => c.url.includes("/exams/2/publish/") && c.init.method === "POST"));
    assert.match(m.container.textContent, /تم نشر الامتحان وإشعار 2 طالب/);
  } finally {
    rec.restore();
    await m.done();
  }
});

test("exams (teacher): the builder offers multiple-choice and true/false questions with one marked correct choice", async () => {
  ME = TEACHER;
  const m = await mount("/app/content", React.createElement(AppRoutes));
  try {
    await openExamsTab(m);
    await clickEl(buttonWith(m.container, "امتحان جديد"));
    const modal = w.document.querySelector("[role=dialog]") || w.document.body;
    assert.match(modal.textContent, /إعدادات منع الغش/);
    const groups = () => modal.querySelectorAll("[role=radiogroup]");
    assert.equal(groups().length, 1, "one starter question");
    assert.equal(groups()[0].querySelectorAll("[role=radio]").length, 4, "four choices by default");
    assert.equal(groups()[0].querySelectorAll("[role=radio][aria-checked=true]").length, 1, "exactly one correct choice");
    await clickEl(buttonWith(modal, "سؤال صح / خطأ"));
    assert.equal(groups().length, 2);
    assert.equal(groups()[1].querySelectorAll("[role=radio]").length, 2, "true/false has two choices");
    // saving an empty paper is refused with a message, nothing is posted
    const rec = recordFetch();
    await clickEl(buttonWith(modal, "حفظ"));
    assert.match(modal.textContent, /اكتب نص السؤال 1/);
    assert.ok(!rec.calls.some((c) => c.init?.method === "POST"), "nothing is sent for an invalid paper");
    rec.restore();
  } finally {
    await m.done();
  }
});

test("exams (teacher): results show the best score, every attempt and the violation log", async () => {
  ME = TEACHER;
  const m = await mount("/app/content", React.createElement(AppRoutes));
  try {
    await openExamsTab(m);
    await clickEl(buttonWith(m.container, "النتائج"));
    await act(async () => {
      await tick(120);
    });
    const text = () => w.document.body.textContent;
    assert.match(text(), /أنهى ٢ من ٣/);
    assert.match(text(), /المتوسط ٦٦٫٧٪/);
    assert.match(text(), /٢\/٣ \(٦٦٫٧٪\)/, "a student's score is shown with its percentage");
    assert.match(text(), /٣\/٣ \(١٠٠٪\)/, "a student with two attempts shows the BEST one");
    assert.match(text(), /أعلى محاولة/, "the page says which attempt counts");
    assert.match(text(), /لم يبدأ/);
    assert.doesNotMatch(text(), /ترك الصفحة/, "the log is collapsed at first");
    const attemptsBtn = (n) => [...w.document.querySelectorAll("table button")].find((b) => b.textContent.trim() === n);
    await clickEl(attemptsBtn("١"));
    assert.match(text(), /ترك الصفحة/);
    assert.match(text(), /محاولة نسخ/);
    await clickEl(attemptsBtn("٢"));
    assert.match(text(), /المحاولة ٢/);
    assert.match(text(), /أُغلق بسبب مخالفات/, "the first attempt of the second student was closed for violations");
    assert.doesNotMatch(text(), /undefined|NaN|Invalid/);
  } finally {
    await m.done();
  }
});

test("exams (teacher): re-opening an exam for a student asks first, posts that student, and says what happens", async () => {
  ME = TEACHER;
  const rec = recordFetch();
  const m = await mount("/app/content", React.createElement(AppRoutes));
  try {
    await openExamsTab(m);
    await clickEl(buttonWith(m.container, "النتائج"));
    await act(async () => {
      await tick(120);
    });
    const reopenButtons = () => [...w.document.querySelectorAll("table button")].filter((b) => b.textContent.includes("إعادة فتح"));
    assert.equal(reopenButtons().length, 2, "offered for each finished student, not for the one who has not started");
    await clickEl(reopenButtons()[0]);
    assert.match(w.document.body.textContent, /أعلى درجة بين محاولاته/, "the teacher is told the best score counts");
    assert.ok(!rec.calls.some((c) => c.url.includes("/reopen/")), "nothing is sent before confirming");
    await clickEl([...w.document.querySelectorAll("button")].find((b) => b.textContent.trim() === "إعادة الفتح"));
    await act(async () => {
      await tick(120);
    });
    const call = rec.calls.find((c) => c.url.includes("/exams/1/reopen/"));
    assert.ok(call && call.init.method === "POST");
    assert.deepEqual(JSON.parse(call.init.body), { enrollment_id: 1 });
    assert.match(w.document.body.textContent, /أُعيد فتح الامتحان لـ أحمد/);
  } finally {
    rec.restore();
    await m.done();
  }
});

test("exams (student): the list shows the best percentage, and a re-opened exam offers a new attempt", async () => {
  ME = STUDENT;
  const m = await mount("/learn/videos", React.createElement(StudentRoutes));
  try {
    await openExamsTab(m);
    const text = m.container.textContent;
    assert.ok(m.container.querySelector("a[href='/learn/exams/1']"), "a link to the open exam");
    assert.match(text, /امتحان الباب الأول/);
    assert.match(text, /٢ سؤال/);
    assert.match(text, /٣٠ دقيقة/);
    assert.match(text, /ابدأ الامتحان/);
    assert.match(text, /٧٥٪/, "the finished exam shows its percentage");
    assert.match(text, /أعلى نتيجة/, "with two attempts it says the best one counts");
    assert.match(text, /أعاد المعلّم فتح الامتحان لك/);
    assert.ok(m.container.querySelector("a[href='/learn/exams/2?retake=1']"), "a way to start the new attempt");
    assert.doesNotMatch(text, /undefined|NaN/);
  } finally {
    await m.done();
  }
});

test("exams (student): the exam is a focus screen — no app header, no tabs, no links away", async () => {
  ME = STUDENT;
  const m = await mount("/learn/exams/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(100);
    });
    await startExam(m);
    assert.equal(m.container.querySelector(".stu-tabs, .stu-top"), null, "the app shell is not around the exam");
    assert.equal(m.container.querySelectorAll("a[href]").length, 0, "nothing to tap that leads away while running");
  } finally {
    await m.done();
  }
});

test("exams (student): no question is requested before pressing start, then one question at a time with no answer key", async () => {
  ME = STUDENT;
  const rec = recordFetch();
  const m = await mount("/learn/exams/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(100);
    });
    assert.match(m.container.textContent, /ابدأ الامتحان/);
    assert.match(m.container.textContent, /مخالفة|مخالفات/);
    assert.match(m.container.textContent, /٣ تحذيرات/, "the intro says how many warnings there are");
    assert.ok(!rec.calls.some((c) => c.url.includes("/start/") || c.url.includes("/question/")), "nothing before start");
    await startExam(m);
    const asked = rec.calls.filter((c) => c.url.includes("/question/")).map((c) => c.url);
    assert.equal(asked.length, 1, "only the first question was requested");
    assert.match(asked[0], /\/question\/0\//);
    assert.match(m.container.textContent, /ما عاصمة مصر/);
    assert.equal(m.container.querySelectorAll("[role=radio]").length, 2);
    assert.ok(m.container.querySelector("[role=timer]").textContent.match(/[٠-٩]{2}:[٠-٩]{2}/));
    assert.doesNotMatch(JSON.stringify(rec.calls.map((c) => c.init?.body || "")), /is_correct/);
  } finally {
    rec.restore();
    await m.done();
  }
});

test("exams (student): the exam shows progress as a percentage and the warning budget", async () => {
  ME = STUDENT;
  const m = await mount("/learn/exams/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(100);
    });
    await startExam(m);
    const text = m.container.textContent;
    assert.match(text, /السؤال ١ من ٢/);
    assert.match(text, /٠٪ مكتمل/);
    const bar = m.container.querySelector("[role=progressbar]");
    assert.equal(bar.getAttribute("aria-valuenow"), "0");
    assert.ok(m.container.querySelector("[aria-label='التحذيرات ٠ من ٣']"), "the strikes indicator shows 0 of 3");
    await clickEl(m.container.querySelector("[role=radio]"));
    await clickEl(buttonWith(m.container, "التالي"));
    await act(async () => {
      await tick(150);
    });
    assert.match(m.container.textContent, /٥٠٪ مكتمل/, "half way after the first question");
    assert.equal(m.container.querySelector("[role=progressbar]").getAttribute("aria-valuenow"), "50");
  } finally {
    await m.done();
  }
});

const afterGrace = () =>
  act(async () => {
    await tick(1650); // the guard ignores the first moments after entering the exam (full-screen shake)
  });

test("exams (student): copy, paste, the context menu and Ctrl+P are blocked, reported and warned about in full screen", async () => {
  ME = STUDENT;
  const rec = recordFetch();
  const m = await mount("/learn/exams/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(100);
    });
    await startExam(m);
    await afterGrace();
    const fire = async (ev) => {
      await act(async () => {
        w.document.dispatchEvent(ev);
        await tick(30);
      });
      return ev.defaultPrevented;
    };
    assert.equal(await fire(new w.Event("copy", { bubbles: true, cancelable: true })), true);
    assert.equal(await fire(new w.Event("paste", { bubbles: true, cancelable: true })), true);
    assert.equal(await fire(new w.Event("contextmenu", { bubbles: true, cancelable: true })), true);
    assert.equal(
      await fire(new w.KeyboardEvent("keydown", { key: "p", code: "KeyP", ctrlKey: true, bubbles: true, cancelable: true })),
      true,
      "Ctrl+P is blocked"
    );
    assert.equal(
      await fire(new w.KeyboardEvent("keydown", { key: "ArrowLeft", code: "ArrowLeft", bubbles: true, cancelable: true })),
      false,
      "ordinary keys still work"
    );
    const kinds = rec.calls.filter((c) => c.url.includes("/violation/")).map((c) => JSON.parse(c.init.body).type);
    for (const k of ["copy", "paste", "contextmenu", "shortcut"]) assert.ok(kinds.includes(k), k);
    const dialog = m.container.querySelector("[role=alertdialog]");
    assert.ok(dialog, "a full-screen warning is shown");
    assert.match(dialog.textContent, /المخالفة ١ من ٣/);
    assert.match(dialog.textContent, /تبقّى لك تحذيران/, "it says how many warnings are left");
    assert.match(dialog.textContent, /الوقت لا يتوقف/);
    // it cannot be skipped by clicking around: only its button dismisses it, and the exam continues
    await clickEl(buttonWith(dialog, "فهمت، أكمل الامتحان"));
    assert.equal(m.container.querySelector("[role=alertdialog]"), null);
    assert.match(m.container.textContent, /ما عاصمة مصر/);
  } finally {
    rec.restore();
    await m.done();
  }
});

test("exams (student): leaving the window is reported, and the warning names what the student did", async () => {
  ME = STUDENT;
  const rec = recordFetch();
  const m = await mount("/learn/exams/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(100);
    });
    await startExam(m);
    await afterGrace();
    await act(async () => {
      w.dispatchEvent(new w.Event("blur"));
      await tick(80);
    });
    assert.ok(rec.calls.some((c) => c.url.includes("/violation/") && JSON.parse(c.init.body).type === "blur"));
    assert.match(m.container.querySelector("[role=alertdialog]").textContent, /غادرت نافذة الامتحان/);
  } finally {
    rec.restore();
    await m.done();
  }
});

test("exams (student): events right after entering the exam are not counted against the student", async () => {
  ME = STUDENT;
  const rec = recordFetch();
  const m = await mount("/learn/exams/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(100);
    });
    await startExam(m);
    await act(async () => {
      w.dispatchEvent(new w.Event("blur"));
      await tick(60);
    });
    assert.ok(!rec.calls.some((c) => c.url.includes("/violation/")), "full-screen entry noise is ignored");
  } finally {
    rec.restore();
    await m.done();
  }
});

test("exams (student): the Back button cannot leave the exam", async () => {
  ME = STUDENT;
  const m = await mount("/learn/exams/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(100);
    });
    await startExam(m);
    const before = w.history.length;
    await act(async () => {
      w.dispatchEvent(new w.PopStateEvent("popstate"));
      await tick(40);
    });
    assert.ok(w.history.length >= before, "the history entry is put back");
    assert.match(m.container.textContent, /لا يمكن الرجوع أثناء الامتحان/);
    assert.match(m.container.textContent, /ما عاصمة مصر/, "still in the exam");
  } finally {
    await m.done();
  }
});

test("exams (student): 'submit now' asks first, then submits", async () => {
  ME = STUDENT;
  const rec = recordFetch();
  const m = await mount("/learn/exams/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(100);
    });
    await startExam(m);
    await clickEl(buttonWith(m.container, "تسليم الآن"));
    assert.match(m.container.querySelector("[role=alertdialog]").textContent, /تسليم الامتحان الآن؟/);
    assert.ok(!rec.calls.some((c) => c.url.includes("/submit/")), "not submitted until confirmed");
    await clickEl(buttonWith(m.container, "متابعة الامتحان"));
    assert.equal(m.container.querySelector("[role=alertdialog]"), null);
    await clickEl(buttonWith(m.container, "تسليم الآن"));
    await clickEl(buttonWith(m.container, "نعم، سلّم"));
    await act(async () => {
      await tick(200);
    });
    assert.ok(rec.calls.some((c) => c.url.includes("/submit/") && c.init.method === "POST"));
  } finally {
    rec.restore();
    await m.done();
  }
});

test("exams (student): an answer is saved on Next, and the last question submits and shows the result as a percentage", async () => {
  ME = STUDENT;
  const rec = recordFetch();
  const m = await mount("/learn/exams/1", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(100);
    });
    await startExam(m);
    await clickEl(m.container.querySelector("[role=radio]"));
    await clickEl(buttonWith(m.container, "التالي"));
    await act(async () => {
      await tick(150);
    });
    const put = rec.calls.find((c) => c.url.includes("/answer/"));
    assert.ok(put, "the answer was saved");
    assert.deepEqual(JSON.parse(put.init.body), { question_id: 1, choice_id: 11 });
    assert.match(m.container.textContent, /كم يساوي/, "the next question is shown");
    assert.ok(!rec.calls.some((c) => c.url.includes("/submit/")), "not submitted before the last question");
    await clickEl(m.container.querySelectorAll("[role=radio]")[1]);
    await clickEl(buttonWith(m.container, "إنهاء وتسليم"));
    await act(async () => {
      await tick(250);
    });
    assert.ok(rec.calls.some((c) => c.url.includes("/submit/") && c.init.method === "POST"));
    const text = m.container.textContent;
    assert.match(text, /٢ من ٣ درجة/, "the score is shown");
    assert.match(text, /٦٦٫٧٪/, "and the percentage");
    assert.match(text, /جيد/, "with a plain verdict");
    assert.ok(m.container.querySelector("[aria-label='نتيجتك ٦٦٫٧٪']"), "as a ring");
    assert.equal(m.container.querySelector("[role=timer]"), null, "the exam view is gone");
  } finally {
    rec.restore();
    await m.done();
  }
});

test("exams (student): after a re-open the result offers a new attempt and says the best score counts", async () => {
  ME = STUDENT;
  const rec = recordFetch();
  const m = await mount("/learn/exams/2", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(200);
    });
    const text = () => m.container.textContent;
    assert.match(text(), /٥٠٪/, "this attempt");
    assert.match(text(), /المحسوبة لك أعلى درجة: ٧٥٪ من محاولة سابقة/);
    assert.match(text(), /أتاح لك معلمك محاولة أخرى/);
    await clickEl(buttonWith(m.container, "ابدأ محاولة جديدة"));
    assert.match(text(), /تُحتسب لك أعلى درجة/, "the intro repeats the rule");
    await clickEl(buttonWith(m.container, "ابدأ المحاولة الجديدة"));
    await act(async () => {
      await tick(150);
    });
    const start = rec.calls.find((c) => c.url.includes("/exams/2/start/"));
    assert.ok(start, "the new attempt was started");
    assert.deepEqual(JSON.parse(start.init.body), { retake: true });
    assert.match(text(), /المحاولة ٣/, "the running exam says which attempt this is");
    assert.match(text(), /سؤال المحاولة الجديدة/);
  } finally {
    rec.restore();
    await m.done();
  }
});

test("notifications (student): an exam notification is badged as an exam and opens the exam", async () => {
  ME = STUDENT;
  const m = await mount("/learn/notifications", React.createElement(StudentRoutes));
  try {
    await act(async () => {
      await tick(120);
    });
    const text = m.container.textContent;
    assert.match(text, /امتحان جديد/);
    assert.doesNotMatch(text, /فيديو جديد/, "an exam is never called a video");
    assert.ok(m.container.querySelector("a[href='/learn/exams/1']"), "opens the exam");
    assert.ok(m.container.querySelector("a[href='/learn/materials/1']"), "a file or summary opens its page");
    assert.ok(m.container.querySelector(".chip-s.is-exam"));
  } finally {
    await m.done();
  }
});
