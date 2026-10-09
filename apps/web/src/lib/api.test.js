// Regression tests for the API client's token handling (Phase 0 / S3).
// Run with:  npm test   (Node's built-in test runner — no extra dependency)
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";

// --- minimal browser-ish globals -------------------------------------------
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

const {
  apiFetch, api, getTokens, setTokens, refreshAccessToken,
  getActiveEnvironmentId, setActiveEnvironmentId, clearActiveEnvironmentId,
} = await import("./api.js");

const json = (status, body) => ({
  status, ok: status >= 200 && status < 300, json: async () => body,
});

beforeEach(() => { store.clear(); });

test("rotated refresh token is stored (not discarded) after a refresh", async () => {
  setTokens({ access: "A0", refresh: "R0" });
  globalThis.fetch = async (url) => {
    if (url.endsWith("/auth/token/refresh/")) return json(200, { access: "A1", refresh: "R1" });
    throw new Error("unexpected " + url);
  };
  const access = await refreshAccessToken();
  assert.equal(access, "A1");
  assert.deepEqual(getTokens(), { access: "A1", refresh: "R1" });
});

test("a second expiry refreshes with the ROTATED token R1, not the old R0", async () => {
  setTokens({ access: "A0", refresh: "R0" });
  const used = [];
  globalThis.fetch = async (url, init) => {
    const body = JSON.parse(init.body);
    used.push(body.refresh);
    // Server behaviour: a blacklisted (already-rotated) token is rejected.
    if (body.refresh === "R0" && used.length > 1) return json(401, { detail: "blacklisted" });
    return body.refresh === "R0"
      ? json(200, { access: "A1", refresh: "R1" })
      : json(200, { access: "A2", refresh: "R2" });
  };
  await refreshAccessToken();
  const second = await refreshAccessToken();
  assert.equal(second, "A2");
  assert.deepEqual(used, ["R0", "R1"]);
  assert.deepEqual(getTokens(), { access: "A2", refresh: "R2" });
});

test("concurrent 401s trigger exactly one refresh call", async () => {
  setTokens({ access: "A0", refresh: "R0" });
  let refreshCalls = 0;
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/auth/token/refresh/")) {
      refreshCalls += 1;
      await new Promise((r) => setTimeout(r, 10));
      return json(200, { access: "A1", refresh: "R1" });
    }
    const auth = init.headers.Authorization;
    return auth === "Bearer A1" ? json(200, { ok: true }) : json(401, { detail: "expired" });
  };
  const results = await Promise.all([
    apiFetch("/x/", { auth: true }), apiFetch("/y/", { auth: true }), apiFetch("/z/", { auth: true }),
  ]);
  assert.equal(refreshCalls, 1);
  assert.deepEqual(results, [{ ok: true }, { ok: true }, { ok: true }]);
  assert.equal(getTokens().refresh, "R1");
});

test("a rejected refresh token clears the session", async () => {
  setTokens({ access: "A0", refresh: "R0" });
  globalThis.fetch = async () => json(401, { detail: "revoked" });
  assert.equal(await refreshAccessToken(), null);
  assert.equal(getTokens(), null);
});

test("a network error or 5xx during refresh does NOT log the user out", async () => {
  setTokens({ access: "A0", refresh: "R0" });
  globalThis.fetch = async () => { throw new TypeError("network down"); };
  assert.equal(await refreshAccessToken(), null);
  assert.deepEqual(getTokens(), { access: "A0", refresh: "R0" });

  globalThis.fetch = async () => json(503, {});
  assert.equal(await refreshAccessToken(), null);
  assert.deepEqual(getTokens(), { access: "A0", refresh: "R0" });
});

// -------------------------- Phase 1: PATCH/DELETE + tenant header --------
test("api.patch and api.delete send the right HTTP method", async () => {
  setTokens({ access: "A0", refresh: "R0" });
  const seen = [];
  globalThis.fetch = async (url, init) => { seen.push({ url, method: init.method }); return json(200, { ok: true }); };
  await api.patch("/x/1/", { name: "n" }, { auth: true });
  await api.delete("/x/1/", { auth: true });
  assert.deepEqual(seen.map((s) => s.method), ["PATCH", "DELETE"]);
});

test("tenant:true attaches X-Madar-Environment when an active environment is set", async () => {
  setTokens({ access: "A0", refresh: "R0" });
  setActiveEnvironmentId(42);
  let seenHeader;
  globalThis.fetch = async (url, init) => { seenHeader = init.headers["X-Madar-Environment"]; return json(200, {}); };
  await apiFetch("/groups/", { tenant: true });
  assert.equal(seenHeader, "42");
});

test("tenant:true sends no X-Madar-Environment header when none is set", async () => {
  setTokens({ access: "A0", refresh: "R0" });
  clearActiveEnvironmentId();
  let seenHeader = "unset";
  globalThis.fetch = async (url, init) => { seenHeader = init.headers["X-Madar-Environment"]; return json(200, {}); };
  await apiFetch("/groups/", { tenant: true });
  assert.equal(seenHeader, undefined);
});

test("tenant:true also authenticates (implies auth) and survives a 401 refresh", async () => {
  setTokens({ access: "expired", refresh: "R0" });
  setActiveEnvironmentId(7);
  globalThis.fetch = async (url, init) => {
    if (url.endsWith("/auth/token/refresh/")) return json(200, { access: "fresh", refresh: "R1" });
    if (init.headers.Authorization === "Bearer fresh" && init.headers["X-Madar-Environment"] === "7") return json(200, { ok: true });
    return json(401, {});
  };
  const result = await apiFetch("/groups/", { tenant: true });
  assert.deepEqual(result, { ok: true });
});

test("getActiveEnvironmentId / setActiveEnvironmentId / clearActiveEnvironmentId round-trip", () => {
  clearActiveEnvironmentId();
  assert.equal(getActiveEnvironmentId(), null);
  setActiveEnvironmentId(15);
  assert.equal(getActiveEnvironmentId(), 15);
  clearActiveEnvironmentId();
  assert.equal(getActiveEnvironmentId(), null);
});

test("a form-level error shows its own message instead of the generic one", async () => {
  const { ApiError } = await import("./api.js");
  const e = new ApiError(400, { detail: "تحقق من البيانات المدخلة.", code: "validation_error", fields: { non_field_errors: ["بيانات الدخول غير صحيحة، حاول مرة أخرى."] } });
  assert.equal(e.message, "بيانات الدخول غير صحيحة، حاول مرة أخرى.");
  const plain = new ApiError(400, { detail: "تحقق من البيانات المدخلة.", fields: { phone: ["x"] } });
  assert.equal(plain.message, "تحقق من البيانات المدخلة.");
});
