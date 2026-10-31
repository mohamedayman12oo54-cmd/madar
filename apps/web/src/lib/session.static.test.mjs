// Policy guard: nobody is signed out for being idle. Signing out happens when the person presses "log out"
// (or the server really refuses the credentials) — never on a timer.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));
const code = walk(SRC).filter((f) => /\.(jsx?|mjs)$/.test(f) && !/\.test\./.test(f));

test("there is no idle sign-out anywhere in the app", () => {
  for (const f of code) {
    const t = fs.readFileSync(f, "utf8");
    assert.doesNotMatch(t, /watchIdle|IDLE_MS|lib\/idle/, `${path.relative(SRC, f)} still references the idle sign-out`);
  }
  assert.ok(!fs.existsSync(path.join(SRC, "lib/idle.js")));
});

test("the staff/student session is kept alive while the page is open, the guardian portal too", () => {
  const session = fs.readFileSync(path.join(SRC, "state/session.jsx"), "utf8");
  assert.match(session, /startKeepAlive/);
  assert.match(session, /refreshAccessToken/);
  assert.match(fs.readFileSync(path.join(SRC, "parent/ParentPortal.jsx"), "utf8"), /startKeepAlive[\s\S]*renewParentSession/);
});

test("a dropped connection never turns into a logout (bootstrap and environment re-check only give up on a 4xx)", () => {
  const session = fs.readFileSync(path.join(SRC, "state/session.jsx"), "utf8");
  assert.match(session, /e\?\.status === 401 \|\| e\?\.status === 403/);
  const env = fs.readFileSync(path.join(SRC, "state/environment.jsx"), "utf8");
  assert.match(env, /e\.status >= 400 && e\.status < 500/);
});

test("every sign-out button leads back to its own login page", () => {
  const read = (f) => fs.readFileSync(path.join(SRC, f), "utf8");
  assert.match(read("dashboard/DashboardLayout.jsx"), /nav\("\/auth\/teacher\/login"/);
  assert.match(read("student/StudentLayout.jsx"), /nav\("\/auth\/student"/);
  assert.match(read("parent/ParentPortal.jsx"), /clearParentSession\(\);\s*nav\("\/auth\/parent"/);
});
