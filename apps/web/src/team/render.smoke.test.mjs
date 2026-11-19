// Render smoke test for the Control Center: mounts the REAL router + providers + every /team page (and the
// customers' support page) in jsdom against a mocked API shaped like the backend's responses, and fails on any
// render / effect crash or React error. A production build cannot catch these: they surface as a blank page.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", { url: "http://localhost:5173/team", pretendToBeVisual: true });
const w = dom.window;
for (const k of ["window", "document", "localStorage", "sessionStorage", "HTMLElement", "Element", "Node", "MutationObserver", "getComputedStyle", "requestAnimationFrame", "cancelAnimationFrame", "CustomEvent", "Event", "KeyboardEvent"]) {
  Object.defineProperty(globalThis, k, { value: k === "window" ? w : w[k], configurable: true, writable: true });
}
Object.defineProperty(globalThis, "navigator", { value: w.navigator, configurable: true });
for (const k of Object.getOwnPropertyNames(w)) {
  if (!(k in globalThis) && /^[A-Z]/.test(k)) Object.defineProperty(globalThis, k, { value: w[k], configurable: true, writable: true });
}
w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
globalThis.matchMedia = w.matchMedia;
globalThis.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
w.IntersectionObserver = globalThis.IntersectionObserver;
// real Chromium returns a Promise here, which is exactly what crashed an effect that returned it
w.HTMLElement.prototype.scrollIntoView = function () { return Promise.resolve(); };
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const NOW = new Date().toISOString();
const day = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);
const series = (v = 2) => [4, 3, 2, 1, 0].map((n) => ({ date: day(n), value: v + n }));
const page = (results, extra = {}) => ({ count: results.length, page: 1, page_size: 20, pages: 1, results, ...extra });
const ALL = ["overview.view", "users.view", "users.edit", "users.suspend", "teachers.view", "students.view", "parents.view", "environments.view", "environments.manage", "team.view", "team.manage", "roles.view", "roles.manage", "tickets.view", "tickets.create", "tickets.reply", "tickets.assign", "tickets.priority", "tickets.resolve", "tickets.categories", "support.analytics", "finance.view", "ai.view", "notifications.view", "notifications.manage", "reports.view", "audit.view", "system.view", "settings.view", "settings.manage", "knowledge.manage"];
let PERMS = ALL;

const USER = { id: 7, name: "أحمد", email: "a@example.com", phone: "201001234567", role: "teacher", status: "active", is_active: true, is_verified: true, date_joined: NOW, last_activity: NOW, environments: [{ id: 1, name: "بيئة" }], environment: { id: 1, name: "بيئة" }, student_count: 3, group_count: 1, enrollments: [], active_enrollments: 0 };
const TICKET_ROW = { id: 5, number: "MDR-000005", subject: "مشكلة", kind: "ticket", status: "open", priority: "high", category: { id: 1, name: "الحساب" }, requester: { id: 7, name: "أحمد", kind: "teacher" }, assignee: null, response_status: "awaiting_team", overdue: false, due_at: NOW, created_at: NOW, updated_at: NOW, reopen_count: 0 };
const TICKET = { ...TICKET_ROW, description: "وصف", source: "customer", first_response_at: null, resolved_at: null, closed_at: null, rating: null, rating_comment: "",
  messages: [{ id: 1, kind: "customer", author: "أحمد", author_id: 7, body: "مرحبا", created_at: NOW, attachments: [{ id: 1, name: "a.png", content_type: "image/png", size: 2048 }] }, { id: 2, kind: "internal", author: "موظف", author_id: 9, body: "سري", created_at: NOW, attachments: [] }],
  history: [{ id: 1, kind: "created", text: "أُنشئت التذكرة", actor: "أحمد", from: "", to: "", at: NOW }, { id: 2, kind: "status", text: "تغيّرت الحالة", actor: "موظف", from: "open", to: "in_progress", at: NOW }],
  customer: { name: "أحمد", kind: "teacher", email: "a@example.com", phone: "201001234567", environment: { id: 1, name: "بيئة" }, user_id: 7, account_status: "active", open_tickets: 1, total_tickets: 3 },
  allowed_statuses: ["in_progress", "waiting_for_user", "resolved", "closed"] };
const ATTEMPT = { id: 1, transaction_id: "ord_1", environment: { id: 1, name: "بيئة" }, owner: "أحمد", plan: "شهري", amount: 150, currency: "EGP", provider: "Kashier", kind: "checkout", status: "failed", status_label: "فاشلة", reference: "r1", provider_transaction_id: "", created_at: NOW, updated_at: NOW, tickets: [{ id: 5, number: "MDR-000005", status: "open" }] };
const OP = { id: 3, kind: "quiz_generation", kind_label: "توليد اختبار", status: "failed", status_label: "فشلت", user: { id: 7, name: "أحمد", role: "student" }, environment: { id: 1, name: "بيئة" }, created_at: NOW, duration_seconds: 80, slow: true, failure_category: "provider_timeout", error: "تعذّر" };
const REPORT = (key) => ({ key, title: "تقرير", range: "30d", from: NOW, to: NOW, columns: [{ key: "date", label: "التاريخ" }, { key: "created", label: "العدد" }], rows: series().map((p) => ({ date: p.date, created: p.value, teachers: 1, students: 2, total: 3 })), totals: { new: 3, all: 9, active: 5, suspended: 1, pending: 3 }, breakdowns: [{ title: "حسب", columns: [{ key: "name", label: "الاسم" }, { key: "count", label: "العدد" }], rows: [{ name: "أ", count: 2 }] }], detail: { title: "تفصيل", columns: [{ key: "name", label: "الاسم" }, { key: "at", label: "الوقت" }], rows: [{ name: "x", at: NOW }] } });
const JOB = (name, status = "ok") => ({ name, label: name, expected_every_minutes: 15, status, last_run: status === "never" ? null : { at: NOW, status: "ok", duration_ms: 20, processed: 3, failed_items: 0, error: "" }, runs_24h: 2, failed_runs_24h: 0, last_error: null });

const ROUTES = {
  "/auth/me/": { id: 1, role: "team", name: "فريق", email: null, phone: null },
  "/control/me/": () => ({ id: 1, name: "فريق", role: "super_admin", role_name: "مدير عام", permissions: PERMS }),
  "/control/feed/": { activity: [], attention: [{ key: "unassigned_tickets", severity: "medium", count: 2, link: "/team/support/unassigned" }] },
  "/control/search/": { users: [{ id: 7, name: "أحمد", role: "teacher", link: "/team/users/7" }], tickets: [], environments: [] },
  "/control/overview/": {
    range: "30d", kpis: [{ key: "total_users", value: 9, link: "/team/users", period: { current: 3, previous: 1, change_pct: 200 } }, { key: "unassigned_tickets", value: 2, link: "/team/support/unassigned", tone: "warn" }, { key: "ai_failed", value: 1, link: "/team/ai?status=failed", tone: "bad", period: { current: 1, previous: 0, change_pct: 100 } }],
    charts: { user_growth: series(), daily_activity: { attendance: series(), notifications: series(), ai: series(), tickets: series() }, teacher_registrations: series(), student_registrations: series(), ticket_trends: { created: series(), resolved: series() }, ticket_resolution: [{ status: "open", count: 2 }], ai: { success: series(), failed: series(0) }, finance: { succeeded: series(), failed: series(0) } },
    attention: [{ key: "critical_complaints", severity: "high", count: 1, link: "/team/support/complaints", samples: [{ label: "MDR-000005 · x", link: "/team/support/tickets/5" }] }],
    activity: [{ kind: "ticket", text: "تذكرة جديدة", at: NOW, link: "/team/support/tickets/5" }],
  },
  "/control/users/": page([USER]), "/control/teachers/": page([USER]), "/control/students/": page([{ ...USER, role: "student", enrollments: [{ environment_id: 1, teacher: "م", grade: "أول", is_active: true }], active_enrollments: 1 }]),
  "/control/users/7/": { ...USER, last_login: NOW, open_tickets: 1, total_tickets: 2, notifications_count: 4, ai_operations_count: 1, teacher: { environment: { id: 1, name: "بيئة", subject_stage: "رياضيات", academic_year: "2026", created_at: NOW }, students_active: 3, students_total: 4, groups: 1, schedules: 2, sessions_30d: 5, attendance_records_30d: 9, evaluations_30d: 1 } },
  "/control/users/7/activity/": [{ kind: "ticket", text: "تذكرة", at: NOW, ticket_id: 5 }], "/control/users/7/tickets/": [TICKET_ROW], "/control/users/7/notifications/": [{ id: 1, title: "إشعار", type_label: "غياب", delivery_status: "sent", created_at: NOW, read_at: null }],
  "/control/users/7/history/": [{ id: 1, actor: "فريق", action: "user.update", entity_type: "user", entity_id: "7", entity_label: "أحمد", before: { name: "أ" }, after: { name: "ب" }, note: "", created_at: NOW }],
  "/control/parents/": page([{ phone: "201055500001", name: "ولي", children: 1, environments: ["بيئة"], unread_messages: 1, has_access_issues: true }]),
  "/control/parents/201055500001/": { phone: "201055500001", name: "ولي", children: [{ enrollment_id: 1, student: "ط", environment: "بيئة", teacher: "م", grade: "أول", enrollment_active: true, student_claimed: false, access_ready: false, issues: ["الطالب لم يفعّل حسابه بعد"] }], messages: [{ id: 1, kind: "warning", title: "غياب", body: "غاب", automatic: true, student: "ط", sent_by: "النظام", read_at: null, created_at: NOW }], replies: [], tickets: [] },
  "/control/team/": [{ id: 2, name: "موظف", username: "a@madar", email: null, is_active: true, role: "support_agent", role_name: "موظف دعم", permission_count: 7, last_login: NOW, date_joined: NOW, assigned_active: 2, resolved: 3 }],
  "/control/team/2/": { id: 2, name: "موظف", username: "a@madar", email: null, is_active: true, role: "support_agent", role_name: "موظف دعم", permission_count: 7, last_login: NOW, date_joined: NOW, assigned_active: 2, resolved: 3, permissions: ["tickets.view"], extra_permissions: [], revoked_permissions: [] },
  "/control/team/2/tickets/": [TICKET_ROW], "/control/team/2/activity/": [],
  "/control/roles/": [{ id: 1, key: "super_admin", name: "مدير عام", description: "", permissions: ALL, is_system: true, members: 1, locked: true }, { id: 2, key: "support_agent", name: "موظف دعم", description: "د", permissions: ["tickets.view"], is_system: true, members: 1, locked: false }],
  "/control/permissions/": [{ key: "support", label: "الدعم", permissions: [{ key: "tickets.view", label: "عرض التذاكر" }] }],
  "/control/environments/": page([{ id: 1, name: "بيئة", subject_stage: "رياضيات", academic_year: "2026", owner: { id: 7, name: "أحمد", is_active: true }, student_count: 3, group_count: 1, created_at: NOW, status: "active" }]),
  "/control/environments/1/": { id: 1, name: "بيئة", subject_stage: "رياضيات", academic_year: "2026", created_at: NOW, owner: { id: 7, name: "أحمد", email: "a@example.com", phone: "2010", is_active: true }, counts: { students_active: 3, students_total: 4, groups: 1, grades: 1, sessions_30d: 5 }, grades: [{ id: 1, name: "أول", students: 3 }], groups: [{ id: 1, name: "G", grade: "أول", students: 3 }], schedules: [{ group: "G", weekday: "السبت", start: "18:00", end: null }], attendance_30d: { present: 5, absent: 1 }, evaluations_30d: { good: 2 }, recent_activity: [{ kind: "session", text: "جلسة", at: NOW }], subscription: { state: "active", plan: "شهري", period_end: NOW }, tickets: [{ id: 5, number: "MDR-000005", subject: "م", status: "open", priority: "high" }], students: [{ id: 9, name: "طالب", grade: "أول", is_active: true }] },
  "/control/support/overview/": { range: "30d", total: 9, open: 3, in_progress: 2, waiting_for_user: 1, resolved: 2, closed: 1, unassigned: 2, high_priority: 1, overdue: 1, avg_first_response_hours: 1.5, avg_resolution_hours: 30 },
  "/control/support/agents/": [{ id: 2, name: "موظف", role: "موظف دعم", active: 2, resolved: 3, overloaded: false }],
  "/control/support/categories/": [{ id: 1, name: "الحساب", description: "", order: 0, is_active: true, tickets: 2 }],
  "/control/support/tickets/": page([TICKET_ROW]), "/control/support/tickets/5/": TICKET,
  "/control/support/analytics/": { range: "30d", volume: { created: series(), resolved: series() }, by_category: [{ name: "الحساب", count: 2 }], by_priority: [{ priority: "high", count: 1 }], by_status: [], created: 4, resolved: 2, resolution_rate: 50, avg_response_hours: 1, avg_resolution_hours: 20, reopened: 1, reopen_rate: 50, common_complaints: [{ name: "الحساب", count: 1 }], agents: [{ id: 2, name: "موظف", assigned: 3, resolved: 2, avg_rating: 4.5, avg_response_hours: 1 }], workload: [{ id: 2, name: "موظف", active: 2, resolved: 3, overloaded: false }], satisfaction: { count: 2, average: 4, distribution: { 1: 0, 2: 1, 3: 0, 4: 0, 5: 1 }, low_rating_feedback: [{ ticket: "MDR-000001", rating: 2, comment: "بطيء", category: "الحساب" }] } },
  "/control/finance/overview/": { range: "30d", total: 5, succeeded: 3, failed: 1, pending: 1, unknown: 0, subscriptions: { active: 2, trial: 1, past_due: 0, canceled: 0, expired: 1 }, revenue: { period: [{ currency: "EGP", amount: 450 }], all_time: [{ currency: "EGP", amount: 900 }] }, charts: { succeeded: series(), failed: series(0), revenue: series(100) } },
  "/control/finance/transactions/": page([ATTEMPT]),
  "/control/finance/subscriptions/": page([{ id: 1, environment: { id: 1, name: "بيئة" }, owner: "أحمد", plan: "شهري", plan_key: "monthly", state: "active", state_label: "نشط", trial_ends_at: null, period_start: NOW, period_end: NOW, cancel_at_period_end: false, renewal: "auto" }]),
  "/control/finance/plans/": [{ id: 1, key: "monthly", name: "شهري", price: 150, currency: "EGP", period_days: 30, max_students: null, is_active: true, active_subscriptions: 2 }],
  "/control/finance/issues/": { window_days: 7, failed: [ATTEMPT], needs_reconciliation: [], pending_too_long: [], verification: [{ id: 1, event_type: "pay", transaction_status: "FAILED", signature_valid: false, processing_status: "failed_to_apply", attempts: 2, error: "x", environment: "بيئة", received_at: NOW }] },
  "/control/ai/overview/": { range: "30d", total: 5, completed: 3, failed: 2, pending: 0, success_rate: 60, failure_rate: 40, avg_seconds: 4.2, slow_count: 1, by_kind: [{ kind: "quiz_generation", label: "توليد اختبار", count: 5 }], failure_categories: [{ category: "provider_timeout", count: 2 }], repeated_failures: [{ user_id: 7, name: "أحمد", count: 3 }], charts: { success: series(), failed: series(0) }, provider: "stub" },
  "/control/ai/operations/": page([OP]),
  "/control/ai/operations/3/": { ...OP, timeline: [{ key: "created", at: NOW }, { key: "started", at: NOW }, { key: "ended", at: NOW }], timings_ms: { content_check: 100, generation: 900, total: 1000 }, context: { has_student: true, has_content: true, prompt_chars: 40, result_chars: 0, month: null }, metadata: { validation: "failed", usage: { total_tokens: 4 } }, started_at: NOW, completed_at: NOW },
  "/control/notifications/overview/": { range: "30d", total: 6, sent: 4, pending: 1, failed: 1, read: 2, by_type: [{ type: "absent", label: "غياب", count: 3 }], push: { configured: false, subscribed_devices: 2, subscribed_users: 2 }, platform_notices: 1, charts: { sent: series(), failed: series(0) } },
  "/control/notifications/": page([{ id: 1, type: "absent", type_label: "غياب", title: "غاب", recipient: { id: 9, name: "طالب", role: "student" }, environment: { id: 1, name: "بيئة" }, status: "sent", status_label: "x", error: "", created_at: NOW, sent_at: NOW, confirmed_read: false }]),
  "/control/notifications/platform/": page([{ id: 1, title: "إعلان", body: "", url: "/", audience: "teachers", audience_label: "كل المعلّمين", environment: null, sent_by: "فريق", recipients: 3, created_at: NOW, queued: 0, sent: 2, failed: 0, no_device: 1 }]),
  "/control/notifications/templates/": [{ id: 1, name: "قالب", title: "عنوان", body: "", is_active: true }],
  "/control/reports/": [{ key: "users", title: "تقرير المستخدمين" }, { key: "tickets", title: "تقرير التذاكر" }],
  "/control/reports/users/": REPORT("users"), "/control/reports/tickets/": REPORT("tickets"),
  "/control/audit/": page([{ id: 1, actor: "فريق", actor_id: 1, action: "user.suspend", entity_type: "user", entity_id: "7", entity_label: "أحمد", before: { status: "active" }, after: { status: "suspended" }, note: "سبب", ip_address: "1.1.1.1", created_at: NOW }], { filters: { actions: ["user.suspend"], entity_types: ["user"], actors: [{ id: 1, name: "فريق" }] } }),
  "/control/system/health/": { checked_at: NOW, overall: "degraded", problems: ["jobs"], api: { ok: true }, database: { ok: true, latency_ms: 3 }, cache: { ok: true }, notifications: { pending: 1, oldest_pending_at: NOW, backlog: false, failed_24h: 0, push_configured: false, dispatch_mode: "thread" }, ai: { pending: 0, oldest_pending_at: null, processing: 0, stuck_processing: 0, failed_24h: 1, provider: "stub", worker_mode: "thread" }, jobs: [JOB("process_notifications", "failed"), JOB("process_ai_operations", "never")], recent_errors: { jobs: [{ name: "process_notifications", at: NOW, error: "boom" }], ai: [{ id: 3, kind: "quiz_generation", at: NOW, error: "x" }], notifications: [] }, housekeeping: { pending_auth_rows: 2 } },
  "/control/system/jobs/": page([{ id: 1, name: "process_notifications", label: "معالجة الإشعارات", status: "ok", started_at: NOW, duration_ms: 12, processed: 3, failed_items: 0, error: "" }], { summary: [JOB("process_notifications")] }),
  "/control/settings/": { editable: [{ key: "sla.critical_hours", group: "ticket_workflow", group_label: "سير", label: "مهلة", description: "د", value: 4, default: 4, min: 1, max: 720 }, { key: "ai.slow_seconds", group: "monitoring", group_label: "م", label: "بطيء", description: "د", value: 60, default: 60, min: 1, max: 3600 }], readonly: [{ key: "session.access_minutes", group: "session", label: "مدة", description: "د", value: 30, unit: "دقيقة" }] },
  "/knowledge/documents/": { count: 0, results: [] },
  "/control/customer/categories/": [{ id: 1, name: "الحساب" }],
  "/control/customer/tickets/": [{ id: 5, number: "MDR-000005", subject: "مشكلة", kind: "ticket", status: "resolved", category: "الحساب", created_at: NOW, updated_at: NOW, response_status: "done" }],
  "/control/customer/tickets/5/": { id: 5, number: "MDR-000005", subject: "مشكلة", kind: "ticket", status: "resolved", category: "الحساب", created_at: NOW, updated_at: NOW, response_status: "done", description: "د", rating: null, rating_comment: "", messages: [{ id: 1, kind: "customer", author: "أنا", author_id: 7, body: "مرحبا", created_at: NOW, attachments: [] }, { id: 2, kind: "agent", author: "ف", author_id: 9, body: "تم", created_at: NOW, attachments: [] }], can_reply: true, can_rate: true },
};
const seen = [];
globalThis.fetch = async (url, init) => {
  const path = new URL(String(url), "http://x").pathname.replace(/^\/api\/v1/, "");
  seen.push(path);
  const v = ROUTES[path];
  if (v === undefined) return new Response(JSON.stringify({ detail: "not mocked" }), { status: 404, headers: { "content-type": "application/json" } });
  return new Response(JSON.stringify(typeof v === "function" ? v(init) : v), { status: 200, headers: { "content-type": "application/json" } });
};
localStorage.setItem("madar.tokens", JSON.stringify({ access: "a", refresh: "r" }));

const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { createServer } = await import("vite");
const vite = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error", optimizeDeps: { noDiscovery: true },
  // React Router 7 ships dual CJS/ESM: bundle it through Vite so the test harness sees the ESM build
  ssr: { noExternal: ["react-router", "react-router-dom"], resolve: { conditions: ["module-sync", "import", "module", "node", "default"] } } });
// the router must come from the SAME module graph as the app (two copies = two contexts)
const { MemoryRouter, Routes, Route } = await vite.ssrLoadModule("react-router-dom");
const load = (p) => vite.ssrLoadModule(p);
const { SessionProvider } = await load("/src/state/session.jsx");
const { EnvironmentProvider } = await load("/src/state/environment.jsx");
const TeamRoutes = (await load("/src/team/TeamRoutes.jsx")).default;
const SupportPage = (await load("/src/support/SupportPage.jsx")).default;
const tick = (ms = 60) => new Promise((r) => setTimeout(r, ms));

async function mount(path, element) {
  const errors = [];
  const origError = console.error;
  console.error = (...a) => errors.push(a.map(String).join(" "));
  const onErr = (e) => errors.push(String(e.error || e.message));
  w.addEventListener("error", onErr);
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(React.createElement(MemoryRouter, { initialEntries: [path] }, React.createElement(SessionProvider, null, React.createElement(EnvironmentProvider, null, element))));
  });
  for (let i = 0; i < 4; i++) await act(async () => { await tick(80); });
  const html = container.innerHTML;
  const text = container.textContent;
  await act(async () => { root.unmount(); });
  container.remove();
  console.error = origError;
  w.removeEventListener("error", onErr);
  return { html, text, errors: errors.filter((e) => !/not wrapped in act|Warning: An update to/.test(e)) };
}

const PAGES = [
  ["/team", "لوحة", "إجمالي المستخدمين"], ["/team/users", "كل المستخدمين", "أحمد"], ["/team/users/7", "أحمد", "نظرة عامة"], ["/team/teachers", "المعلّمون", "أحمد"], ["/team/students", "الطلاب", "أحمد"],
  ["/team/parents", "أولياء الأمور", "201055500001"], ["/team/parents/201055500001", "ولي أمر", "الطالب لم يفعّل"], ["/team/members", "أعضاء الفريق", "موظف"], ["/team/members/2", "موظف", "الصلاحيات"],
  ["/team/roles", "الأدوار والصلاحيات", "مدير عام"], ["/team/environments", "البيئات التعليمية", "بيئة"], ["/team/environments/1", "بيئة", "معلومات عامة"],
  ["/team/support", "مركز الدعم", "عبء العمل"], ["/team/support/tickets", "كل التذاكر", "MDR-000005"], ["/team/support/mine", "تذاكري", "MDR-000005"], ["/team/support/unassigned", "غير المسندة", "MDR-000005"],
  ["/team/support/complaints", "الشكاوى", "MDR-000005"], ["/team/support/tickets?new=1", "كل التذاكر", "تذكرة جديدة نيابةً عن عميل"], ["/team/support/tickets/5", "MDR-000005", "ملاحظة داخلية"], ["/team/support/categories", "تصنيفات", "الحساب"],
  ["/team/support/analytics", "تحليلات الدعم", "أداء الموظفين"], ["/team/finance", "الإدارة المالية", "الباقات"], ["/team/finance/transactions", "المعاملات", "ord_1"],
  ["/team/finance/subscriptions", "الاشتراكات", "تجديد تلقائي"], ["/team/finance/issues", "مشكلات الدفع", "ord_1"], ["/team/ai", "عمليات الذكاء", "provider_timeout"], ["/team/ai/3", "عملية ذكاء", "فحص المحتوى"],
  ["/team/notifications", "الإشعارات", "سجل الإشعارات"], ["/team/reports", "التقارير", "تقرير المستخدمين"], ["/team/reports/tickets", "التقارير", "تفصيل"], ["/team/analytics/users", "تحليلات المستخدمين", "حالة الحسابات"],
  ["/team/analytics/finance", "التحليلات المالية", "الإيراد اليومي"], ["/team/analytics/ai", "تحليلات الذكاء", "أسباب الفشل"], ["/team/audit", "سجل التدقيق", "إيقاف حساب"], ["/team/system/health", "صحة النظام", "لا يوجد تشغيل مسجّل"],
  ["/team/system/jobs", "العمليات الخلفية", "معالجة الإشعارات"], ["/team/settings", "الإعدادات", "مهلة"], ["/team/knowledge", "", ""],
];
for (const [path, title, needle] of PAGES) {
  test(`control center page renders without crashing: ${path}`, async () => {
    PERMS = ALL;
    const r = await mount(path, React.createElement(TeamRoutes));
    assert.deepEqual(r.errors, [], `${path}: ${r.errors.join("\n")}`);
    assert.ok(r.text.includes(title), `${path}: missing title "${title}"`);
    assert.ok(r.text.includes(needle), `${path}: missing "${needle}"; got: ${r.text.slice(0, 300)}`);
  });
}

test("the menu only offers sections the member has permission for", async () => {
  PERMS = ["overview.view", "tickets.view", "tickets.reply"];
  const r = await mount("/team", React.createElement(TeamRoutes));
  assert.deepEqual(r.errors, []);
  assert.ok(r.text.includes("كل التذاكر"));
  for (const hidden of ["كل المستخدمين", "الإدارة المالية", "سجل التدقيق", "الأدوار والصلاحيات", "صحة النظام", "قاعدة المعرفة"]) assert.ok(!r.text.includes(hidden), `menu leaked "${hidden}"`);
});

test("a legacy team account (knowledge only) lands on the Knowledge Base and sees no control sections", async () => {
  PERMS = ["knowledge.manage"];
  const r = await mount("/team", React.createElement(TeamRoutes));
  assert.deepEqual(r.errors, []);
  assert.ok(r.text.includes("قاعدة المعرفة"));
  assert.ok(!r.text.includes("كل التذاكر"));
});

test("internal notes are drawn for the team but the customers' ticket page never receives them", async () => {
  PERMS = ALL;
  const team = await mount("/team/support/tickets/5", React.createElement(TeamRoutes));
  assert.ok(team.text.includes("سري"));
  const customer = await mount("/x", React.createElement(Routes, null, React.createElement(Route, { path: "/x", element: React.createElement(SupportPage) })));
  assert.deepEqual(customer.errors, []);
  assert.ok(customer.text.includes("الدعم والمساعدة"));
  assert.ok(!customer.text.includes("سري"));
});

test("a failing API shows a retryable error state, not a blank page", async () => {
  PERMS = ALL;
  const orig = globalThis.fetch;
  globalThis.fetch = async (url, init) => (String(url).includes("/control/users/") ? new Response(JSON.stringify({ detail: "x" }), { status: 500, headers: { "content-type": "application/json" } }) : orig(url, init));
  try {
    const r = await mount("/team/users", React.createElement(TeamRoutes));
    assert.ok(r.text.includes("تعذّر تحميل البيانات") && r.text.includes("إعادة المحاولة"), r.text.slice(0, 300));
  } finally {
    globalThis.fetch = orig;
  }
});

const clickText = async (container, text) => {
  const el = [...container.querySelectorAll("button")].find((b) => b.textContent.includes(text));
  assert.ok(el, `button "${text}" not found`);
  await act(async () => {
    el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
    await tick(40);
  });
};
async function mountLive(path) {
  const container = w.document.createElement("div");
  w.document.body.appendChild(container);
  const root = createRoot(container);
  const errors = [];
  const origError = console.error;
  console.error = (...a) => errors.push(a.map(String).join(" "));
  await act(async () => {
    root.render(React.createElement(MemoryRouter, { initialEntries: [path] }, React.createElement(SessionProvider, null, React.createElement(EnvironmentProvider, null, React.createElement(TeamRoutes)))));
  });
  for (let i = 0; i < 4; i++) await act(async () => { await tick(80); });
  return { container, errors, done: async () => { console.error = origError; await act(async () => root.unmount()); container.remove(); } };
}

test("new ticket form: an empty submit shows field errors, sends nothing, and shows no success toast", async () => {
  PERMS = ALL;
  const writes = [];
  const orig = globalThis.fetch;
  globalThis.fetch = async (url, init) => { if (init?.method && init.method !== "GET") writes.push(`${init.method} ${url}`); return orig(url, init); };
  const m = await mountLive("/team/support/tickets?new=1");
  try {
    await clickText(m.container, "إنشاء التذكرة");
    const errs = [...m.container.querySelectorAll(".modal .field-msg.err")].map((e) => e.textContent.trim());
    assert.ok(errs.some((e) => e.includes("اختر تصنيفًا")), errs.join(" | "));
    assert.ok(errs.some((e) => e.includes("عنوانًا")));
    assert.deepEqual(writes, [], "nothing may be sent while the form is invalid");
    assert.equal(m.container.querySelector(".toasts").children.length, 0, "no toast at all");
  } finally {
    globalThis.fetch = orig;
    await m.done();
  }
});

test("ticket page: an empty reply is refused locally and explained as such (not as a connection failure)", async () => {
  PERMS = ALL;
  const m = await mountLive("/team/support/tickets/5");
  try {
    await clickText(m.container, "إرسال");
    const toast = m.container.querySelector(".toasts").textContent;
    assert.ok(toast.includes("اكتب نص الرسالة"), toast);
    assert.ok(!toast.includes("الاتصال"), "a validation message must not read as a network error");
    assert.deepEqual(m.errors.filter((e) => !/not wrapped in act/.test(e)), []);
  } finally {
    await m.done();
  }
});

test("errText tells a network failure from a local validation message", async () => {
  const { errText } = await load("/src/team/kit.jsx");
  assert.match(errText(new TypeError("Failed to fetch")), /الاتصال بالخادم/);
  assert.equal(errText(new Error("اكتب نص الرسالة أولًا.")), "اكتب نص الرسالة أولًا.");
  assert.match(errText({ status: 403 }), /صلاحية/);
});

test.after(async () => {
  await vite.close();
});
