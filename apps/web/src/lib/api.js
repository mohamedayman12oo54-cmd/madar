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

const BASE_URL = import.meta.env?.VITE_API_URL || "http://127.0.0.1:8000/api/v1";

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

export class ApiError extends Error {
  constructor(status, data) {
    super(data?.detail || "حدث خطأ غير متوقع.");
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
 * @param {{method?:string, body?:object, auth?:boolean}} opts
 */
export async function apiFetch(path, { method = "GET", body, auth = false } = {}) {
  const doFetch = async () => {
    const headers = { "Content-Type": "application/json" };
    if (auth) {
      const tokens = getTokens();
      if (tokens?.access) headers.Authorization = `Bearer ${tokens.access}`;
    }
    return fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let res = await doFetch();

  if (res.status === 401 && auth) {
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
};
