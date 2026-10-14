// Auth-flow-specific wrappers around the generic API client, one
// function per backend endpoint (see madar-backend/accounts/urls.py and
// environments/urls.py) — screens call these instead of touching
// apiFetch directly.
import { api, setTokens, clearTokens, getTokens } from "../lib/api.js";

export const authApi = {
  teamLogin: (identifier, password) => api.post("/auth/team/login/", { identifier, password }),
  teacherLogin: (identifier, password) => api.post("/auth/teacher/login/", { identifier, password }),
  studentLogin: (phone, password) => api.post("/auth/student/login/", { phone, password }),

  teacherSignupStart: (payload) => api.post("/auth/teacher/signup/", payload),
  teacherSignupEnvironment: (payload) => api.post("/auth/teacher/signup/environment/", payload),

  teacherForgotRequest: (identifier) => api.post("/auth/teacher/forgot/", { identifier }),
  teacherForgotReset: (payload) => api.post("/auth/teacher/forgot/reset/", payload),

  // payload: { channel: "phone"|"email", student_code, phone? | email? }
  studentClaimRequest: (payload) => api.post("/auth/student/claim/", payload),
  studentClaimActivate: (payload) => api.post("/auth/student/claim/activate/", payload),

  studentForgotRequest: (phone) => api.post("/auth/student/forgot/", { phone }),
  studentForgotReset: (payload) => api.post("/auth/student/forgot/reset/", payload),

  otpVerify: (flow, pending_id, code) => api.post(`/auth/otp/${flow}/verify/`, { pending_id, code }),
  otpResend: (flow, pending_id) => api.post(`/auth/otp/${flow}/resend/`, { pending_id }),

  me: () => api.get("/auth/me/", { auth: true }),
  logout: async () => {
    const tokens = getTokens();
    if (tokens?.refresh) {
      // The refresh token is the credential for logout (no access token
      // needed), so this still revokes it when the access token has expired.
      try { await api.post("/auth/logout/", { refresh: tokens.refresh }); } catch { /* best-effort */ }
    }
    clearTokens();
  },
};

export const envApi = {
  teacherList: () => api.get("/environments/teacher/", { auth: true }),
  teacherEnter: (id) => api.post(`/environments/teacher/${id}/enter/`, undefined, { auth: true }),
  studentList: () => api.get("/environments/student/", { auth: true }),
  studentEnter: (id) => api.post(`/environments/student/${id}/enter/`, undefined, { auth: true }),
  // Server-side confirmation of the currently active environment (the one
  // named by X-Madar-Environment, i.e. whatever src/state/environment.jsx
  // currently has selected). Used to validate a *persisted* selection
  // (page reload / new tab) before trusting it for any tenant-scoped call —
  // never to pick the environment in the first place, which only ever
  // happens through teacherEnter/studentEnter above (backend-authorized
  // lists) or a person's own click on an EnvCard.
  context: () => api.get("/environments/context/", { tenant: true }),
};

export function saveSession(data) {
  setTokens({ access: data.access, refresh: data.refresh });
  return data.user;
}

/** Maps a backend ApiError onto the { field: message } shape every
 * screen already keeps in its `fe` state — falls back to a single
 * top-level error string (the screens' `err` state) when the backend
 * didn't return field-level detail. */
export function fieldErrorsFrom(apiError) {
  if (apiError?.fields && typeof apiError.fields === "object" && !Array.isArray(apiError.fields)) {
    const out = {};
    for (const [k, v] of Object.entries(apiError.fields)) {
      out[k] = Array.isArray(v) ? v[0] : String(v);
    }
    return out;
  }
  return null;
}
