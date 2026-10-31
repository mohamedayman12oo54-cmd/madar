// The guardian portal never signs a guardian out on a timer: while the tab is open its tokens are renewed.
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";

const mem = () => {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) };
};
globalThis.localStorage = mem();
globalThis.sessionStorage = mem();

const { getParentSession, saveParentSession, renewParentSession } = await import("./parentApi.js");

const json = (status, body) => ({ status, ok: status >= 200 && status < 300, json: async () => body });
const two = () => saveParentSession({ expires_in: 60, children: [
  { token: "A1", student_name: "علي", grade: "أول", teacher_environment: "x" },
  { token: "B1", student_name: "منى", grade: "ثاني", teacher_environment: "x" },
] });

beforeEach(() => sessionStorage.removeItem("madar.parent.session"));

test("renewal swaps every child's token for the fresh one and pushes the expiry forward", async () => {
  two();
  const seen = [];
  globalThis.fetch = async (url, init) => {
    seen.push({ url: String(url), auth: init.headers.Authorization });
    const old = init.headers.Authorization.split(" ")[1];
    return json(200, { token: old.replace("1", "2"), expires_in: 86400 });
  };
  const before = getParentSession().expires_at;
  const next = await renewParentSession();
  assert.deepEqual(next.children.map((c) => c.token), ["A2", "B2"]);
  assert.ok(seen.every((c) => c.url.endsWith("/parent/renew/") && c.auth.startsWith("Parent ")));
  assert.ok(next.expires_at > before + 60 * 60 * 1000, "a day from now, not a minute");
  assert.equal(getParentSession().children[0].token, "A2", "stored for the next page load too");
});

test("the child being viewed stays selected after a renewal", async () => {
  two();
  const s = getParentSession();
  s.active = 1;
  sessionStorage.setItem("madar.parent.session", JSON.stringify(s));
  globalThis.fetch = async (_u, init) => json(200, { token: init.headers.Authorization.split(" ")[1] + "x", expires_in: 100 });
  const next = await renewParentSession();
  assert.equal(next.active, 1);
  assert.equal(next.children[next.active].student_name, "منى");
});

test("a child the server no longer accepts is dropped; the others keep going", async () => {
  two();
  globalThis.fetch = async (_u, init) =>
    init.headers.Authorization.endsWith("A1") ? json(401, { detail: "x" }) : json(200, { token: "B2", expires_in: 100 });
  const next = await renewParentSession();
  assert.deepEqual(next.children.map((c) => c.student_name), ["منى"]);
});

test("when no child is accepted any more the session is over", async () => {
  two();
  globalThis.fetch = async () => json(401, { detail: "x" });
  assert.equal(await renewParentSession(), null);
  assert.equal(getParentSession(), null);
});

test("a network failure is not a logout: the current tokens are kept", async () => {
  two();
  globalThis.fetch = async () => { throw new TypeError("offline"); };
  const next = await renewParentSession();
  assert.deepEqual(next.children.map((c) => c.token), ["A1", "B1"]);
  assert.equal(getParentSession().children.length, 2);
});
