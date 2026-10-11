// Thin API client for the Madar Django backend.
// - Stores tokens in localStorage (access + refresh).
// - Automatically retries a request once after refreshing the access
//   token if the server says it's expired (401).
// - The backend ROTATES refresh tokens (each refresh returns a new one and
//   blacklists the old one), so the rotated refresh token is always stored.
//   Concurrent 401s share ONE refresh call — a second parallel call would
//   replay the just-blacklisted token and log the user out.
// - Throws ApiError with the backend's parsed error body attached, so
//   screens can map { fields: { phone: "..." } } straight onto their
//   existing per-field error state.

export const BASE_URL = import.meta.env?.VITE_API_URL || "http://127.0.0.1:8000/api/v1";

// A production build must talk to the API over HTTPS only: otherwise tokens and
// passwords would cross the network in clear text. Fail loudly at startup.
if (import.meta.env?.PROD && !/^https:\/\//i.test(BASE_URL)) {
  throw new Error("VITE_API_URL must be an https:// URL in production builds.");
}

const TOKEN_KEY = "madar.tokens";

export function getTokens() {
  try {
    return JSON.parse(localStorage.getItem(TOKEN_KEY) || "null");
  } catch {
    return null;
  }
}

export function setTokens(tokens) {
  if (!tokens) { localStorage.removeItem(TOKEN_KEY); return; }
  localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated() {
  return !!getTokens()?.access;
}

// -------------------------------------------------------------------------
// Active environment (tenant) id — the ONLY thing that gets sent as the
// X-Madar-Environment header (see madar-backend/environments/tenancy.py,
// which is the only place the backend reads it from). This is a UI
// convenience for "which environment did the person last pick" — it is
// NEVER trusted by itself; every tenant-scoped response must still be
// validated against what the backend says the user can access (see
// src/state/environment.jsx, which calls GET /environments/context/ to
// confirm a persisted id before treating it as real).
const ACTIVE_ENV_KEY = "madar.activeEnvironment";

export function getActiveEnvironmentId() {
  const raw = localStorage.getItem(ACTIVE_ENV_KEY);
  return raw ? Number(raw) : null;
}

export function setActiveEnvironmentId(id) {
  if (id === null || id === undefined) { localStorage.removeItem(ACTIVE_ENV_KEY); return; }
  localStorage.setItem(ACTIVE_ENV_KEY, String(id));
}

export function clearActiveEnvironmentId() {
  localStorage.removeItem(ACTIVE_ENV_KEY);
}

export class ApiError extends Error {
  constructor(status, data) {
    // A form-level failure (e.g. wrong login) arrives as fields.non_field_errors;
    // show THAT sentence instead of the generic "check your input".
    const formLevel = data?.fields?.non_field_errors;
    super((Array.isArray(formLevel) && typeof formLevel[0] === "string" && formLevel[0]) || data?.detail || "حدث خطأ غير متوقع.");
    this.status = status;
    this.data = data || {};
    this.code = data?.code;
    this.fields = data?.fields || null;
  }
}

async function performRefresh() {
  // Read at call time: another tab may already have rotated the tokens.
  const tokens = getTokens();
  if (!tokens?.refresh) return null;

  let res;
  try {
    res = await fetch(`${BASE_URL}/auth/token/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: tokens.refresh }),
    });
  } catch {
    // Network failure says nothing about the session — keep the tokens.
    return null;
  }

  if (res.status === 401 || res.status === 400) {
    // The server rejected the refresh token (expired / blacklisted / revoked).
    clearTokens();
    return null;
  }
  if (!res.ok) return null; // 429 / 5xx: transient, keep the tokens and let the caller fail

  const data = await res.json();
  // Keep the ROTATED refresh token; fall back to the old one only if the
  // server (unexpectedly) did not send a new one.
  const next = { access: data.access, refresh: data.refresh || tokens.refresh };
  setTokens(next);
  return next.access;
}

let refreshInFlight = null;

export function refreshAccessToken() {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

/**
 * @param {string} path e.g. "/auth/teacher/login/"
 * @param {{method?:string, body?:object, auth?:boolean, tenant?:boolean}} opts
 *   `tenant`: attach X-Madar-Environment (the currently active environment,
 *   if one is set) — for calls to tenant-scoped endpoints. Implies `auth`.
 */
export async function apiFetch(path, { method = "GET", body, auth = false, tenant = false, raw = false, authorization = null } = {}) {
  const doFetch = async () => {
    // `raw` sends a FormData body (file upload): the browser must set its own
    // multipart Content-Type WITH the boundary, so we must not set one.
    const headers = raw ? {} : { "Content-Type": "application/json" };
    if (auth || tenant) {
      const tokens = getTokens();
      if (tokens?.access) headers.Authorization = `Bearer ${tokens.access}`;
    }
    // A caller-supplied scheme (the guardian's `Parent <token>`) replaces the
    // user JWT entirely and is never refreshed: it is not a user session.
    if (authorization) headers.Authorization = authorization;
    if (tenant) {
      const envId = getActiveEnvironmentId();
      if (envId) headers["X-Madar-Environment"] = String(envId);
    }
    return fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : (raw ? body : JSON.stringify(body)),
    });
  };

  let res = await doFetch();

  if (res.status === 401 && (auth || tenant) && !authorization) {
    const newAccess = await refreshAccessToken();
    if (newAccess) res = await doFetch();
  }

  if (res.status === 204 || res.status === 205) return null;

  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }

  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

export const api = {
  get: (path, opts) => apiFetch(path, { ...opts, method: "GET" }),
  post: (path, body, opts) => apiFetch(path, { ...opts, method: "POST", body }),
  patch: (path, body, opts) => apiFetch(path, { ...opts, method: "PATCH", body }),
  put: (path, body, opts) => apiFetch(path, { ...opts, method: "PUT", body }),
  delete: (path, opts) => apiFetch(path, { ...opts, method: "DELETE" }),
};
