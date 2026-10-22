# مدار — Madar Backend

Django + Django REST Framework API for the Madar frontend (`../madar-frontend`).
Built from scratch to match every auth screen in that frontend exactly —
field names, error shapes, and flow order all mirror the UI.

## Requirements
- Python 3.11+

## Getting started
```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then edit — see "Environment variables" below
python manage.py migrate
python manage.py seed_demo      # creates ready-to-use demo accounts (see below)
python manage.py runserver
```

The API is now at `http://127.0.0.1:8000/api/v1/`. Point the frontend at it via
`madar-frontend/.env` → `VITE_API_URL=http://127.0.0.1:8000/api/v1`.

Run the test suite (1,150+ tests covering every flow, including negative, permission and tenant-isolation cases):
```bash
python manage.py test
```

## Demo accounts (`seed_demo`)
Password for every seeded account is `Demo1234!`.
| Role | How to log in |
|---|---|
| Team | identifier `team@madar` |
| Teacher | identifier `ahmed@madar.test` or phone `201001234567` |
| Student (already claimed) | phone `201119998888` |
| Student (try the claim flow) | phone `201117776666` |

There's no "team signup" screen anywhere in the product, so team accounts are
provisioned by whoever runs the backend:
```bash
python manage.py create_team_user "team@madar" --name "اسم الفريق"
```

## Architecture
- **`accounts`** — the custom `User` model (one table for teacher/student/team,
  see the model's docstring for why), `PendingAuth` (backs every OTP-gated
  multi-step flow statelessly — the SPA just carries a `pending_id` from one
  step to the next instead of the server holding a session), serializers,
  views, JWT issuing.
- **`environments`** — `Environment` (a teacher's class/teaching space) and
  `EnvironmentMembership` (who can enter which environment, and when they
  last did — powers both env-select screens' "آخر دخول" line).

## Every endpoint, mapped to the screen that calls it
| Endpoint | Screen |
|---|---|
| `POST /auth/team/login/` | Team login |
| `POST /auth/teacher/login/` | Teacher login |
| `POST /auth/teacher/signup/` → `POST /auth/otp/teacher-signup/verify/` → `POST /auth/teacher/signup/environment/` | Teacher signup (3 steps) |
| `POST /auth/teacher/forgot/` → `POST /auth/otp/teacher-reset/verify/` → `POST /auth/teacher/forgot/reset/` | Teacher forgot-password |
| `POST /auth/student/login/` | Student login |
| `POST /auth/student/claim/` → `POST /auth/otp/student-claim/verify/` → `POST /auth/student/claim/activate/` | Student claim |
| `POST /auth/student/forgot/` → `POST /auth/otp/student-reset/verify/` → `POST /auth/student/forgot/reset/` | Student forgot-password |
| `POST /auth/otp/<flow>/resend/` | every OTP screen's "إعادة إرسال" timer |
| `POST /auth/token/refresh/`, `POST /auth/logout/`, `GET /auth/me/` | session plumbing |
| `GET /environments/teacher/`, `POST /environments/teacher/<id>/enter/` | Teacher environment select |
| `GET /environments/student/`, `POST /environments/student/<id>/enter/` | Student environment select |
| `POST /environments/students/` | *(new — see below)* |
| `GET /api/v1/health/` | load balancer / uptime checks (no auth) |

All under `/api/v1`. `<flow>` is one of `teacher-signup` / `teacher-reset` /
`student-claim` / `student-reset`.

## What I added beyond the given screens (and why)
The provided frontend has no teacher dashboard, so **there was no screen
anywhere that actually creates a student record for the Claim flow to
claim** — Student Claim would otherwise always dead-end at "not found."
`POST /environments/students/` (teacher-only, phone + name + environment id)
is the minimum piece of real infrastructure needed to make that flow
genuinely work end-to-end. It's covered by tests and by `seed_demo`, but has
no frontend UI yet — wire it up wherever the real teacher dashboard lands.

I also found and fixed one real gap while wiring things up: the Student
Login screen's "نسيت كلمة المرور؟" link pointed at the **teacher's**
forgot-password screen (there simply wasn't a student one). I built a
proper student forgot-password flow (phone → OTP → new password), mirroring
the teacher one, and pointed the link at it.

## Security posture
- **Passwords**: hashed with Django's default (PBKDF2); the password policy
  (`accounts/validators.py`) is kept in exact lockstep with the frontend's
  `PW_RULES` in `src/auth/ui.jsx` — if one changes, update the other.
- **JWT** via `djangorestframework-simplest`: short-lived access tokens (30
  min), rotating refresh tokens with blacklisting (`/auth/logout/` actually
  revokes the refresh token, not just a client-side "forget the token").
- **OTP**: 6 digits, 5-minute expiry, hashed at rest (never stored in
  plaintext), max 5 attempts before lockout, purpose-scoped (a signup OTP
  cannot be replayed against the reset endpoint even with the same
  `pending_id` shape — tested explicitly).
- **Anti-enumeration**: forgot-password endpoints (teacher and student)
  return an identical response whether or not the identifier exists — tested
  explicitly. (Student Claim is deliberately the *opposite*: "no account
  found" is the product's own designed UX, since a teacher explicitly tells
  a student "I registered you with this number," so confirming that is the
  point, not a leak.)
- **Rate limiting** (DRF throttling): login endpoints, OTP request/verify,
  and other sensitive writes all have scoped rate limits (see
  `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` in `settings.py`).
- **CORS**: explicit origin allow-list only, never a wildcard; no cookies/
  credentials involved (auth is header-based JWT), which keeps CSRF out of
  scope for the API itself.
- **Authorization**: every view requires authentication by default
  (`DEFAULT_PERMISSION_CLASSES`) unless a view explicitly opts out — a
  forgotten `permission_classes` can never accidentally expose an endpoint.
  Role checks (`IsTeacher`/`IsStudent`) are enforced on every environment
  endpoint (tested: a teacher cannot list/enter another teacher's
  environment; a student cannot hit teacher-only endpoints, and vice versa).
- **Production hardening auto-enables on `DJANGO_DEBUG=False`**: HSTS,
  secure cookies, SSL redirect, and the app refuses to boot at all with
  `DEBUG=False` and no real `DJANGO_SECRET_KEY` set. Verified with
  `manage.py check --deploy`.
- **No SMS/email provider is wired up** (that requires a paid third-party
  account I can't provision here). In `DEBUG` mode only, every OTP endpoint
  echoes the generated code back in the response (`debug_otp`) so the whole
  flow is testable without one — this is impossible to accidentally enable
  in production because it's gated on `DEBUG`, not just an env flag. Wire
  `accounts/models.py PendingAuth.set_new_otp()`'s caller sites to your SMS/
  email provider of choice before going live — search the codebase for
  `debug_otp`.

## Testing
- `python manage.py test` — the full unit/integration suite (1,152 tests at the last full run) (Django's test client),
  covering every flow's happy path plus the security-relevant edge cases
  above (wrong password, replayed/cross-purpose OTP, attempt lockout,
  enumeration, cross-tenant access, weak passwords, mismatched passwords,
  duplicate email/phone, already-claimed re-claim, blacklisted token reuse).
- The whole thing was also verified with real HTTP requests (not just
  Django's test client) — every endpoint, in the exact sequence and JSON
  shape the frontend actually sends — including a real CORS preflight
  check against the configured origin allow-list.

## Environment variables (`.env`)
See `.env.example` for the full list with comments. The important ones:
- `DJANGO_SECRET_KEY` — required in production; the app refuses to start
  with `DEBUG=False` and no real key set.
- `DJANGO_DEBUG` — defaults to `False` (secure by default).
- `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
  `DJANGO_CSRF_TRUSTED_ORIGINS` — comma-separated, no wildcards.
- `DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT` — PostgreSQL connection (required; SQLite is no longer supported).

## Known limitations (being upfront about scope)
- No real SMS/email sending (see above).
- No teacher dashboard exists in the given frontend, so there's no UI for
  `POST /environments/students/` yet — it's real and tested, just needs a
  screen.
- PostgreSQL only (see `POSTGRESQL.md`; `docker-compose.yml` starts one locally).

## Deploying for real
`manage.py runserver` is dev-only (Django says so itself). For production:
```bash
pip install gunicorn
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```
Put this behind a real reverse proxy (nginx/Caddy) that terminates TLS —
`SECURE_SSL_REDIRECT`/HSTS assume HTTPS reaches Django already, whether
directly or via `X-Forwarded-Proto` from the proxy. Set every variable in
`.env.example` for real (especially `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`) — the app refuses to boot
with `DEBUG=False` and the placeholder secret key, on purpose.


## لوحة المعلم (v2) — ما تغيّر
- مراجعة الأمان: `SECURITY.md` • المطابقة للوثائق: `../CONFORMANCE.md`
- بعد سحب هذه النسخة: `python manage.py migrate` (يحافظ على بياناتك؛ خذ نسخة احتياطية من قاعدة PostgreSQL أولًا).
- الـ workers (عمليات منفصلة في الإنتاج):
  ```bash
  python manage.py process_notifications     # تسليم الإشعارات (غير متزامن)
  python manage.py process_ai_operations     # المساعد + اقتراح الحالة
  python manage.py purge_pending_auth        # يوميًا: حذف تدفقات OTP المنتهية
  ```
- نقاط جديدة (كلها داخل بيئة المعلم النشطة `X-Madar-Environment` ومحصورة بها):
  `scheduling/{schedules,sessions/generate,sessions/<id>/roster,attendance/mark,recitation/mark}` •
  `financials/monthly` • `evaluation/{monthly,ratings,ratings/publish,states,notes}` •
  `ai/state-recommendations` • `content/<id>/publish` • `notifications/{broadcast,summary,retry-failed}` •
  `environments/{overview,current}` • `auth/{change-password,sign-out-everywhere}` والتعديل `PATCH auth/me`.
- أرقام الهاتف: ترسلها دائمًا برمز الدولة (`+20 100 …`). تُخزَّن بصيغة `201001234567`.
- الاختبارات: `python manage.py test` (280).

> **مهم بعد التحديث:** شغّل `python manage.py migrate` — الـ migration `0004_canonical_phones` يوحّد صيغة أرقام الحسابات القديمة (وإلا يفشل دخول من سُجّل قبل التحديث). للتشخيص: `python manage.py diagnose_login <رقم أو بريد>` (وضع DEBUG فقط).


## لوحة الطالب
- نقاط `/api/v1/student/*` (تتطلب دور طالب + `X-Madar-Environment` لبيئة هو نشط فيها): `overview` • `attendance` • `recitation` • `payments` • `evaluation` • `videos` • `notifications` (+`read-all`, `<id>/read`) • `quizzes` (+`operations/<id>`, `<id>`, `<id>/submit`) • `assistant`.
- `python manage.py migrate` (يضيف `studentarea` و`ContentItem.quiz_source` وأنواع جديدة في `ai`).
- الـ worker `process_ai_operations` يولّد الآن الاختبارات أيضًا — شغّله بجانب الخادم.
- الاختبارات: `python manage.py test` (312).
