# QA scripts (Playwright + Python)

Ad-hoc browser and API checks used for the audit. They are **not** part of `npm test` because they need
a running stack and seeded demo data. Install once: `pip install playwright && playwright install chromium`.

Prerequisites: Django on `127.0.0.1:8000` (DEBUG, throwaway database, `python manage.py seed_demo`) and
`npm run dev` on `127.0.0.1:5173`. Set `QA_OUT=./qa-out` for screenshots/JSON (default).

| Script | What it checks |
|---|---|
| `responsive.py [team public teacher student]` | Every page at 320/360/375/390/430/768/1024/1280/1440/1920: horizontal overflow, console/page errors, API 4xx/5xx, redirects, tap targets < 24px |
| `flow.py` | Team knowledge CRUD + publish/unpublish at 390px, first-visit info dialog, modal focus trap/Esc/focus return, teacher mobile drawer semantics |
| `parent.py [widths…]` | Guardian code login through the UI, portal at each width. **Mind the throttle: 10 attempts/hour per phone** |
| `csp.py`, `csp2.py` | Production build (`VITE_API_URL=https://… vite build`) served by `spa.py`: no CSP violations; inline script and foreign iframe are blocked |
| `endpoint_map.py qa-out/endpoints.json` → `authsweep.py` | Lists every route with its permission classes, then probes anonymous / wrong-role / foreign-environment access |

Notes: the seeded accounts and `Demo1234!` password are for the throwaway local database only. Google Fonts
is not reachable from some sandboxes; the scripts ignore that one network error.
