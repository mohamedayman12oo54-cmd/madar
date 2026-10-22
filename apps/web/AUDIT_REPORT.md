# Madar — Audit, Hardening and Dashboard Completion Report

Date: 2026-10-22 · Scope: the full ZIP (React/Vite frontend + Django/DRF backend) · Method: read the code, ran it, changed it, re-ran it.

Status vocabulary: **PASS** (ran and passed) · **FAIL** (ran and failed) · **NOT TESTED** (not run) · **BLOCKED** (could not run here, reason given).

---

## 1. Executive summary

The architecture was sound and was kept: role-scoped tenancy resolved in one place, signed short-lived playback tickets, resumable uploads, a provider-adapter billing layer, static "guard" tests as the project's own spec. Nothing was rebuilt.

What was wrong, in order of consequence:

1. **The fourth role had no working area.** Content Maintainers (`team`) had a login screen but nowhere to land. Added `/team` with a full Knowledge Base screen (list, filter, search, paginate, create, edit, publish, unpublish, delete).
2. **Frontend XSS surface.** QR codes were injected as raw HTML; embed URLs were not allow-listed; the production build had no CSP and shipped source maps.
3. **Backend integrity bugs.** Resumable uploads could accept stray bytes (reproduced: 551 bytes stored for a 524-byte file); resubscribing did not clear `cancel_at_period_end`; editing a published KB document did not bump its version; an unauthenticated webhook read up to 20 MB and returned 500 on an oversized body; a non-numeric `attempt_id` caused a 500.
4. **A privacy leak that contradicted its own comment.** The guardian OTP request revealed whether a phone number is a registered guardian number.
5. **A visibly broken screen that automated overflow checks cannot see.** The parent portal rendered as bare stacked text when opened directly (missing stylesheet import). Found by looking at screenshots, fixed, and now guarded by a test.
6. **Dead and misleading code**: 7 unused API modules, an orphan page, two unused ticket functions (one advertising a viewer-binding the stream endpoint does not enforce), three stale billing files shadowed by a package.

Current verification: backend **1153 tests OK** (1 skipped, reason below), frontend **166/166**, production build OK (entry chunk 379 KB, was 614 KB), Django `check`, `makemigrations --check` and `check --deploy` clean, **290 page×width browser checks + 10 parent-portal checks PASS**.

**Not production-ready until:** the OTP/SMS provider is wired (BLOCKED, §8), secrets from the shipped `.env` are rotated (§8), and the deployment checklist (§11) is done.

---

## 2. Phase 1 — Architecture and inventory

| Layer | Detail |
|---|---|
| Frontend | React 18, react-router 6, Vite 5, framer-motion, lucide-react, qrcode. Arabic/RTL only (`<html lang="ar" dir="rtl">`). Four lazy areas: public+auth, `/app` (teacher), `/learn` (student), `/parent`, `/team`. |
| Backend | Django 5.2, DRF 3.17, SimpleJWT (rotating + blacklisted refresh, `sv` session-version claim), PostgreSQL only, faster-whisper, django-cors-headers. |
| Roles | teacher (owner of an *environment*), student (enrolled in environments), parent (read-only signed session bound to ONE enrollment, no User row), team (content maintainer, central KB). |
| Tenancy | `X-Madar-Environment` header, resolved **only** in `environments/tenancy.py`; every object lookup reviewed is scoped by `request.environment`. The KB is deliberately central. |
| Endpoints | 112 API routes mapped with their permission and throttle classes (`qa/endpoint_map.py`). |
| Frontend↔backend | `routes.conformance.test.mjs` checks every frontend API path against the real backend URL table. PASS. |

---

## 3. Findings and fixes (security table, Phase 5)

Severity is my judgement of impact in this product's context.

| ID | Sev | Component | Finding | Fix | Verification |
|---|---|---|---|---|---|
| S-01 | High | Frontend QR (`StudentsPage`, `student/HomePage`) | SVG string injected with `dangerouslySetInnerHTML` | Vetted and shown through an inert `<img>` data URL (`qrImageSrc`) | Static guard bans HTML sinks; `embed-qr` tests. **PASS** |
| S-02 | Medium | Frontend embeds (`ContentPage`, `VideoDetailPage`) | Embed URL not allow-listed | `safeEmbedUrl` (YouTube-nocookie/Vimeo only, https) + sandboxed iframe; guard requires both | Unit + static tests. **PASS** |
| S-03 | Medium | Frontend build | No CSP; source maps published | CSP `<meta>` generated at build (`script-src 'self'`, `object-src 'none'`, `frame-src` two hosts, `connect-src` = API origin); `sourcemap:false`; `deploy/security-headers.conf` created (it was referenced but missing) with a sync test against `public/_headers` | **Real browser:** no violations on first load; injected inline script and a foreign iframe were blocked. **PASS** |
| S-04 | Low | Frontend API client | Ambient credentials / caching / Referer on API calls, including uploads | `FETCH_HARDENING` (`credentials:omit`, `no-store`, `no-referrer`) on every call via `authFetch` | Static guard. **PASS** |
| S-05 | Low | Frontend quiz drafts | Draft-answer persistence needed one audited place | Consolidated in `lib/quizDraft.js` (session-scoped, cleared on logout); the static guard now allow-lists exactly that module and the parent session | Static guard + tests. **PASS** |
| B-01 | Medium | Billing webhook (unauthenticated) | Read up to 20 MB; oversized body → 500 | Header-first size cap, `RequestDataTooBig` handled; 503 while provider not ready for webhooks | `billing/test_hardening.py`. **PASS** |
| B-02 | Low | Billing checkout return | `?attempt_id=abc` → 500 | Input validation → clean 400 | Test added. **PASS** |
| B-03 | Medium | Billing state | Resubscribe left `cancel_at_period_end=True` | Cleared in `apply_success` | Test. **PASS** |
| B-04 | Medium | Resumable upload | Bytes left by a crashed write became part of the video (reproduced 551 ≠ 524) | PATCH takes the row lock first; positional write, truncate, fsync | `test_bytes_left_by_a_crashed_write_never_become_part_of_the_video`. **PASS** |
| B-05 | Low | Knowledge base | Editing a *published* document did not bump `version` (breaks provenance of AI grounding) | `update()` bumps version when published text changes | 3 new tests. **PASS** |
| B-06 | Medium | Guardian OTP request | 400 for unknown number vs 200 for a registered one (privacy oracle; contradicted `send_pending_code`'s own docstring) | Uniform 200 and body shape; unknown numbers get an inert flow (no code sent, empty `enrollment_ids`) that `verify` can never exchange | 3 tests rewritten/added. **PASS**. The app's real path (`/parent/login`) was already uniform. |
| B-07 | Info | `content/streaming.py` | Docstring claimed a copied link is useless to others; the stream endpoint accepts the ticket alone (documented bearer design). Two unused functions, one repeating the claim | Docstring corrected; dead functions removed | Content suite 100 OK. **PASS** |
| B-08 | Info | `billing/` | Stale flat `providers.py`, `kashier.py`, `test_kashier.py` shadowed by the `providers/` package, breaking two guard tests | Removed | Billing suite OK. **PASS** |

### Checked and found sound (no change)

| Area | Evidence |
|---|---|
| Authorization, live sweep against the running server | Anonymous → 401 on all 35 teacher-scoped, 10 student-scoped and 4 role endpoints. Student token on teacher endpoints → 403 (35/35). Teacher/team tokens on student endpoints → 403 (10/10). Environment ids the teacher does not own → 403 (35/35). **No 5xx** anywhere on the legitimate sweep. **PASS** |
| Production guard rails | Settings refuse to boot with a weak/placeholder `SECRET_KEY`, wildcard hosts, non-https CORS/CSRF, a fake payment provider, or an unconfigured Kashier. Observed live: boot refused until Kashier variables were present. `check --deploy` then: 0 issues. **PASS** |
| Throttling | Guardian code login limited per IP, per phone (10/h) and per code (10/h): hit 429 in testing, as designed. Production defaults to a shared DB cache so limits hold across workers. **PASS** |
| Role isolation in the UI | A team token opening `/app` is redirected to `/auth`. **PASS** |
| Dangerous sinks | No `eval`/`Function`/string timers/HTML sinks anywhere in `src/`. **PASS** |

---

## 4. Phases 2–3 — Pages and dashboards

Functional depth differs by evidence type, stated honestly:

| Role | Surface | Renders with real data at all 10 widths | Interactions verified in a browser | Interactions verified by tests |
|---|---|---|---|---|
| Public | `/`, `/features`, `/teachers`, `/students`, `/contact`, `/auth`, `/auth/teacher/login`, `/auth/student`, `/auth/parent` | **PASS** | not tested | static/a11y/render tests |
| Teacher | overview, students, groups, sessions, attendance, scan, evaluation, financials, content, notifications, billing, settings | **PASS** (12 pages) | drawer, info dialog | backend 1153; frontend render smoke |
| Student | home, records, videos, quizzes, assistant, notifications, settings | **PASS** (7 pages) | not tested | backend + frontend tests |
| Parent | login + portal | **PASS** (10 widths) | wrong-code message, login → portal | backend 34 |
| Team | Knowledge Base | **PASS** | **full CRUD + publish/unpublish at 390px, validation errors, modal focus/Esc** | backend knowledge 15 |

Dashboard completeness: every teacher/student/parent screen in the codebase loads real data and has loading, empty and error states. The team area is new. Features that need third-party credentials keep their integration structure and fail closed rather than faking success: AI model provider, SMS OTP, Kashier checkout. None of those was exercised end-to-end here (**BLOCKED**, no credentials; covered by backend tests with the fake provider).

Improvements made: lazy-loaded areas with a `Suspense` fallback (entry chunk 614 → 379 KB), accessible `Modal` and `Field` (§7), contrast tokens, search focus ring, WCAG 2.2 tap targets on rating buttons and the environment-switch link, parent portal stylesheet fix with a regression guard, dead code removal.

---

## 5. Phase 4 — Backend review

| Check | Result |
|---|---|
| Models/constraints/migrations | Migration chain applies from an empty PostgreSQL database, including the two parallel `environments/0002` and their merge. `check_environment_cardinality` (INV-9) passes. `makemigrations --check`: no changes. **PASS** |
| Permissions / tenancy | See §3 sweep. **PASS** |
| Errors | The 500s found (B-01, B-02) are fixed; none remain in the sweep. **PASS** |
| Transactions / locking | Upload PATCH locks first (B-04); verify exchange is atomic. **PASS** |
| Pagination / serializers | KB endpoint paginated; frontend handles a vanished last page. **PASS** |
| Tests | **1153 OK, 1 skipped** (the billing runbook test skips when the docs tree is not in the archive). Serial run, 77 s. **PASS** |
| Unresolved | No per-environment storage quota for uploads (§8). |

---

## 6. Phase 6 — Responsive matrix (Chromium 1194, headless)

Each cell = all pages of that area, at that width: no horizontal overflow, no console/page errors, no API ≥ 400, landed on the intended route.

| Area (pages) | 320 | 360 | 375 | 390 | 430 | 768 | 1024 | 1280 | 1440 | 1920 |
|---|---|---|---|---|---|---|---|---|---|---|
| Public (9) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Teacher (12) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Student (7) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Team (1) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| Parent portal (1) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

Visual review: contact sheets of every teacher, student and public page at 390px were inspected by eye; the parent portal defect was found this way, fixed, and re-inspected at 390 and 1280.

**Not covered (NOT TESTED):** intermediate widths between the ten listed; **LTR/English** (the app has no English UI — not applicable, not claimed); Safari, Firefox and real devices; public pages `/about`, `/how-it-works`, `/privacy`, `/terms`; auth sub-flows (signup, forgot, claim, environment select, welcome, state screens); video detail/quiz-taking/scanner camera/upload in a browser; landscape and 200% zoom.

**Limits of this environment:** Google Fonts is unreachable from the sandbox, so text was rendered in the fallback font; line breaks can differ slightly with IBM Plex Sans Arabic. Tap targets: after the fixes no target under 24 px remains on the swept pages (one transient 1-element hit on `/learn/settings` did not reproduce on a fresh load).

---

## 7. Phase 7 — Accessibility (WCAG 2.2 AA where feasible)

| Item | Status |
|---|---|
| Modal: `role=dialog`, `aria-modal`, focus moved in, **Tab trap**, Esc, focus restored to opener, stacked-modal safe | **PASS** (6 unit tests + browser check) |
| Teacher mobile drawer: `aria-expanded`/`aria-controls`, dialog semantics, focus in/out, Esc, closes on navigate | **PASS** (browser) |
| Form `Field`: label, `aria-describedby`, `aria-invalid`, `required`, live error region | **PASS** (unit) |
| Colour contrast tokens `--muted` (#5f6675) and `--soft` (#626977) raised; measured 4.63–5.76:1 on the app's backgrounds and guarded by a static test (every text token ≥ 4.5:1 on every surface); search and channel-option focus rings | **PASS**. Status-chip colours beyond the three tested tokens: **NOT TESTED** |
| Target size 2.5.8 (24×24) | **PASS** on swept pages (rating buttons, env-switch fixed) |
| Rating buttons now announce "n من 5" | **PASS** |
| Screen-reader run (NVDA/VoiceOver), automated axe scan, keyboard-only pass of every page | **NOT TESTED** |

---

## 8. Remaining issues (ranked)

| # | Sev | Issue | Status |
|---|---|---|---|
| R-1 | **High (ops)** | A development `.env` was inside the archive (plus a virtualenv, `ai.zip`, `.qodo`). Its values were not printed or used. Treat every value as exposed: **rotate**. The cleaned deliverable excludes all four | Action for you |
| R-2 | **High (blocker)** | OTP/SMS provider not selected or wired. Teacher signup, student claim and password reset cannot complete in production. Dev returns `debug_otp` only when `DEBUG=True` | **BLOCKED** |
| R-3 | Medium | No per-environment storage quota: one tenant can fill the disk with uploads | Open |
| R-4 | Medium | Access and refresh tokens live in `localStorage` (readable by script if an XSS ever lands). Mitigated by no HTML sinks, strict CSP and the guard tests; documented accepted risk | Accepted |
| R-5 | Medium | Playback tickets are short-lived bearer URLs (a live URL streams for its TTL). Documented and accepted; revocation is immediate on the server side | Accepted |
| R-6 | Low | The landing page holds content behind a fixed 2.5 s intro (skipped with reduced motion). Left unchanged: remembering "seen" would need relaxing the project's own `sessionStorage` guard | Recommendation |
| R-7 | Low | Students table on phones scrolls horizontally inside its container (no overflow of the page) | Recommendation: card layout |
| R-8 | Info | No ESLint configuration in the project. I ran an ad-hoc ESLint (react + react-hooks) pass: 0 errors, 0 warnings after fixes. Not added as a dependency | Recommendation |

### Decisions and drift for you (I did not silently edit documentation)

1. **Teacher notes visibility.** The implementation shows teacher notes to the student; the System and Backend documentation say they are private. One of them must change. The guardian portal explicitly excludes them.
2. **Stack.** The Backend documentation still lists the framework as Open; the code is Django/DRF.
3. **Backend README** had stale items; fixed: `X-Environment-ID` → `X-Madar-Environment`, the "36 tests" count. `SECURITY.md` has a new appended section for this pass.

---

## 9. Phases 8–9 — Tests, build, quality

| Check | Result |
|---|---|
| Frontend unit/static/integration (`npm test`) | **166 / 166 PASS** (was 137/139 with 3 test files not even wired in) |
| Backend (`manage.py test`) | **1153 OK, 1 skipped** |
| Production build | **PASS**, no source maps, entry 379 KB / 119 KB gzip |
| `manage.py check` / `makemigrations --check` / `check --deploy` | **PASS / PASS / PASS** (deploy check run with production-like variables and placeholder values only) |
| Browser: responsive sweep (290 page×width) | **PASS** |
| Browser: parent portal (10 widths), team CRUD, drawer, modal | **PASS** |
| Browser: production CSP incl. positive control | **PASS** |
| Authorization sweep (live) | **PASS** |
| Mutation checks (guards actually fail when the protection is removed) | **PASS** for the parent-stylesheet guard |
| Lint | Ad-hoc ESLint **PASS** (not in repo) |
| e2e in CI, Safari/Firefox, load/performance profiling, Lighthouse | **NOT TESTED** |

---

## 10. Files

**Frontend modified (29):** `App.jsx`, `auth/{auth.css, modal.test.mjs, ui.jsx, screens/TeamAuth.jsx}`, `components/Navbar.jsx`, `dashboard/{AiPage, AttendancePage, ContentPage, DashboardLayout, EvaluationPage, SessionsPage, StudentsPage}.jsx`, `dashboard/{dashboard.css, pageInfo.js}`, `index.css`, `lib/{a11y.static.test.mjs, api.js, dashboardApi.js, security.static.test.mjs, video.js}`, `parent/ParentPortal.jsx`, `state/session.jsx`, `student/{HomePage, QuizPages, VideoDetailPage}.jsx`, `student/student.css`, plus `vite.config.js`, `package.json`.
**Frontend created:** `lib/{knowledgeApi.js, quizDraft.js, styles.static.test.mjs}`, `team/{KnowledgePage, TeamLayout, TeamRoutes}.jsx`, `deploy/security-headers.conf`, `qa/` (scripts + README).
**Frontend deleted (7):** `lib/{billingApi, contentApi, evaluationApi, financialsApi, notificationsApi, schedulingApi}.js` (imported by nothing) and `dashboard/BillingReturnPage.jsx` (unrouted; `BillingPage` already handles the return).

**Backend modified (16):** `billing/{events, services, webhooks, test_hardening, test_observability}.py`, `billing/providers/{__init__, kashier}.py`, `content/{streaming, upload_views, test_video}.py`, `knowledge/{serializers, tests}.py`, `parents/{views, tests}.py`, `README.md`, `SECURITY.md`.
**Backend deleted (3):** `billing/{providers.py, kashier.py, test_kashier.py}`.

---

## 11. Run commands and production-readiness checklist

```bash
# Backend (PostgreSQL required; use a throwaway DB for tests)
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
export DJANGO_DEBUG=True DJANGO_SECRET_KEY=dev-only-… DB_NAME=… DB_USER=… DB_PASSWORD=… DB_HOST=127.0.0.1
python manage.py migrate && python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
python manage.py test                       # 1153 tests
# Frontend
npm install && npm run dev                  # http://localhost:5173  (API: VITE_API_URL, default http://127.0.0.1:8000/api/v1)
npm test                                    # 166 tests
VITE_API_URL=https://api.example.com/api/v1 npm run build   # production build (https required)
```

Demo accounts (local throwaway DB only, password `Demo1234!`): team `team@madar`; teacher `ahmed@madar.test`; student phone `201119998888`.

| Pre-launch item | Status |
|---|---|
| Rotate every secret from the shipped `.env`; never ship `.env`, venv, `ai.zip`, `.qodo` | **TODO** |
| Wire an SMS/OTP provider | **BLOCKED** |
| `DJANGO_DEBUG=False`, 50+ char random `DJANGO_SECRET_KEY`, explicit `DJANGO_ALLOWED_HOSTS`, https-only `CORS_ALLOWED_ORIGINS` / `DJANGO_CSRF_TRUSTED_ORIGINS`; `DJANGO_BEHIND_TLS_PROXY=True` when TLS terminates at a proxy | enforced by the settings guard; `check --deploy` = 0 issues with and without the TLS-proxy flag |
| `python manage.py createcachetable` once (shared throttle cache across workers) | **TODO** |
| `DJANGO_NUM_PROXIES=N` when behind N trusted proxies (default 0 = socket IP; otherwise all clients share the proxy IP and IP throttles collapse) | **TODO** |
| Kashier variables (`KASHIER_*`, `BILLING_CHECKOUT_RETURN_URL`), webhook URL registered, billing workers scheduled | **TODO** |
| Serve the frontend with `deploy/security-headers.conf` (nginx) or `public/_headers` (Netlify/Cloudflare) for `frame-ancestors`, HSTS, etc. | **TODO** |
| Do not web-serve `MEDIA_ROOT`; use `X-Accel-Redirect` for video at scale | design supports it |
| Storage quota per environment; backups; monitoring | **TODO** |
| Run `qa/` scripts against staging; add axe + a screen-reader pass | **NOT TESTED** |

---

## Addendum — UI polish pass (2026-10-23)

Requested: fix empty gaps on phones, make the frontend more coordinated, shrink oversized buttons, restyle the student AI chat like ChatGPT.

| Area | Change |
|---|---|
| Controls | One scale for every control: 42px fields, 40px buttons (was 46px), `.9rem` text, 12px radius, auto width instead of full-width stretching; primary buttons use a subtle navy gradient. Phones keep 16px inputs (no iOS zoom). |
| Empty gaps | Empty states are compact panels with an icon; the live message area under fields takes no space when empty; filters wrap two per row; stat cards fill rows (odd last card spans); page headers keep actions on one row; student stat cards go 5-across on wide screens; the scan page's manual-code field and button share one row. |
| Cohesion | Stat cards with tinted icon tiles, unified section headings, billing hero/plan cards re-spaced, student home greeting inside a navy hero card, students table becomes readable cards on phones, `PageHeader` accepts a `sub` line. |
| Student AI chat | `student/AssistantPage.jsx` + new `student/chat.css`: scrolling thread (your question as a bubble, answer as plain text with an avatar), welcome state with suggestion cards, docked rounded composer with auto-growing textarea and circular send button (Enter sends / Shift+Enter newline on desktop; newline on touch), typing dots, copy and retry actions, collapsible Sources. API, idempotency and polling logic unchanged. |

Verification: 166/166 frontend tests, production build, ESLint (0 problems), responsive sweep 290/290 pass (all roles × 10 widths 320–1920, no overflow, no console errors); chat flow exercised in a browser against the dev backend (suggestion fill, multiline, auto-grow, send, pending state, failed state with retry, completed answer with sources). Not tested: a real AI provider answer (none configured), iOS Safari, screen reader.

---

## Addendum 2 — Session self check-in (QR), desktop layout, settings (2026-10-23)

**New feature: students check themselves in by QR.** On the teacher's scan page (beside the camera, with the selected open session) the teacher presses «إنشاء رمز الحضور» and gets a QR plus a 6-digit code to announce in class (with copy-link, big full-screen view, regenerate, stop, and a live "checked in" count). The student scans the QR → `/checkin/<token>` → enters the phone number of their Madar account and the code → attendance is recorded as present.

Backend (`scheduling/checkin.py`, `CheckinLink` model + migration `0005`, tests `scheduling/test_checkin.py`, 20 tests):

| Property | How it is enforced |
|---|---|
| Two secrets, two channels | QR carries a 128-bit opaque token; the 6-digit code is only announced aloud. A photo of the QR alone marks no one. |
| Environment- and group-scoped | The phone must belong to an ACTIVE enrollment in that session's group. Students of other teachers/groups cannot check in and cannot learn anything. |
| Attendance only | The endpoint can only write `present`. It never writes absence, recitation or payments and reads no records. Public info is limited to environment name, group and time. |
| No oracle | Wrong code, unknown phone, wrong group, inactive student → one identical message; constant-time code comparison. |
| Never overrides the teacher | A manual absence is not overturned; an auto-absence (after a session was closed and reopened) can be. |
| Lifetime | Only while the session is OPEN; expires after 3 h; a new link revokes the previous one; closing the session ends it. |
| Brute-force limits | Throttled per IP (120/h), per phone (8/h) and per link (200/h → the 10^6 code space cannot be walked within a link's life). |
| Teacher endpoints | Environment owner only; 404 for another teacher's session. |

Public routes: `GET /api/v1/scheduling/checkin/<token>/`, `POST /api/v1/scheduling/checkin/<token>/submit/`. Teacher routes: `GET|POST|DELETE /api/v1/scheduling/sessions/<id>/checkin/`.

Known limitation (by design of the requested flow): anyone who knows a classmate's phone AND is told the code could check that classmate in remotely — the code being announced in class is the control. Ask students not to share it; the teacher can regenerate at any time and sees the count.
Students who attend as GUESTS from another group use the teacher's badge scanner, not this form.

**Desktop/laptop layout:** content centers at 1320px max on very wide screens; the scan page is two columns (camera | check-in panel) from 1000px; settings are two columns of titled cards; the billing hero's call-to-action sits beside the text instead of stretching across; group cards form a grid; empty states fill their container; student stat cards sit five across. Also fixed: the 6-box code field overflowing narrow cards (now equal-width columns).

Verification: 168 frontend tests (2 new), ESLint 0 problems, production build, 30 overflow checks (6 widths × 5 pages) clean, full browser run of the flow (teacher creates → student submits → teacher count updates; repeat shows «حضورك مسجّل بالفعل»). Not tested: a real phone camera scanning the QR, iOS Safari.
