// Cross-stack guard: every API path the frontend calls must resolve to a real
// route in the Django backend, and no API module may be dead code.
//
// Why this exists: the repo had already drifted twice in the same way — test
// files aimed at endpoints that had been renamed, and five duplicate API
// modules whose paths (`/notifications/{id}/read/`, `/notifications/unread-count/`)
// no longer existed on the server. Nothing failed, because nothing checked.
// This test fails loudly the moment a path or a module goes stale.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const BACKEND = join(ROOT, "backend");
const LIB = join(ROOT, "src", "lib");

/** `path("api/v1/<prefix>", include("<app>.urls"))` -> { app: prefix } */
function rootPrefixes() {
  const src = readFileSync(join(BACKEND, "config", "urls.py"), "utf8");
  const out = {};
  for (const m of src.matchAll(/path\(\s*"api\/v1\/([^"]*)"\s*,\s*include\(\s*"(\w+)\.urls"/g)) {
    out[m[2]] = m[1];
  }
  return out;
}

/** Collapse every url parameter to a single placeholder so `<int:pk>` in
 *  Django and `${id}` in JS compare equal. */
const normalize = (p) =>
  ("/" + p.replace(/^\/+/, ""))
    // `${qs(...)}` builds a QUERY STRING, not a path segment — drop it.
    .replace(/\$\{\s*qs\([\s\S]*?\)\s*\}/g, "")
    .replace(/<[^>]+>/g, ":p") // Django converters
    .replace(/\$\{[^}]*\}/g, ":p") // JS template holes (real path params)
    .split("?")[0]
    .replace(/\/+$/, "") + "/";

function backendRoutes() {
  const routes = new Set();
  for (const [app, prefix] of Object.entries(rootPrefixes())) {
    const f = join(BACKEND, app, "urls.py");
    if (!existsSync(f)) continue;
    for (const m of readFileSync(f, "utf8").matchAll(/path\(\s*"([^"]*)"/g)) {
      routes.add(normalize("/" + prefix + m[1]));
    }
  }
  return routes;
}

/** Every `api.get("/x/")` / `apiPut(`/x/${id}/`)` literal in src/lib. */
function frontendCalls() {
  const calls = [];
  for (const file of readdirSync(LIB).filter((f) => f.endsWith(".js") && !f.includes(".test."))) {
    const src = readFileSync(join(LIB, file), "utf8");
    for (const m of src.matchAll(
      /\b(?:api\.(?:get|post|put|patch|delete)|api[A-Z]\w*)\(\s*(["'`])([^"'`]*)\1/g
    )) {
      const raw = m[2];
      if (!raw.startsWith("/")) continue; // not a path literal
      calls.push({ file, raw, path: normalize(raw) });
    }
  }
  return calls;
}

// The backend lives in a sibling checkout. When the frontend is used on its
// own (it ships as a separate project), skip rather than fail — but never
// silently: the skip reason names exactly what is missing.
const BACKEND_PRESENT = existsSync(join(BACKEND, "config", "urls.py"));

test(
  "every frontend API path resolves to a backend route",
  {
    skip: BACKEND_PRESENT
      ? false
      : `backend not found at ${BACKEND} — run this from the full checkout`,
  },
  () => {
    const routes = backendRoutes();
    assert.ok(routes.size > 20, `sanity: parsed ${routes.size} backend routes`);
    const calls = frontendCalls();
    assert.ok(calls.length > 20, `sanity: found ${calls.length} frontend calls`);

    const orphans = calls.filter((c) => !routes.has(c.path));
    assert.deepEqual(
      orphans.map((o) => `${o.file}: ${o.raw}`),
      [],
      "frontend calls an endpoint the backend does not serve"
    );
  }
);

test("no API module in src/lib is dead code", () => {
  const modules = readdirSync(LIB).filter((f) => f.endsWith("Api.js"));
  assert.ok(modules.length > 0, "sanity: found API modules");

  // Collect every import specifier used anywhere in src.
  const imported = new Set();
  const walk = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name);
      if (e.isDirectory()) {
        walk(p);
        continue;
      }
      if (!/\.(jsx?|mjs)$/.test(e.name)) continue;
      for (const m of readFileSync(p, "utf8").matchAll(/from\s+["']([^"']+)["']/g)) {
        imported.add(m[1].split("/").pop());
      }
    }
  };
  walk(join(ROOT, "src"));

  const dead = modules.filter((m) => !imported.has(m));
  assert.deepEqual(dead, [], "API module is imported by nothing — delete it or wire it up");
});
