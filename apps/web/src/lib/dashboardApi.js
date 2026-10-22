// Tenant-scoped wrappers for the teacher dashboard. `tenant: true` attaches the
// active-environment header from lib/api.js — no function here ever takes an
// environment id (the server derives and checks it; see ADR-008).
import { ApiError, BASE_URL, api, authFetch, setTokens } from "./api.js";

export function qs(params) {
  const entries = Object.entries(params || {}).filter(
    ([, v]) => v !== undefined && v !== null && v !== ""
  );
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}
const T = { tenant: true };

export const overviewApi = { get: () => api.get("/environments/overview/", T) };

export const settingsApi = {
  environment: () => api.get("/environments/current/", T),
  renameEnvironment: (payload) => api.patch("/environments/current/", payload, T),
  me: () => api.get("/auth/me/", { auth: true }),
  updateName: (name) => api.patch("/auth/me/", { name }, { auth: true }),
  async changePassword(current_password, password, password2) {
    const data = await api.post(
      "/auth/change-password/",
      { current_password, password, password2 },
      { auth: true }
    );
    // All OTHER sessions were just revoked; keep this device signed in.
    if (data?.access) setTokens({ access: data.access, refresh: data.refresh });
    return data;
  },
  signOutEverywhere: () => api.post("/auth/sign-out-everywhere/", {}, { auth: true }),
};

// Teacher QR scanner. The badge token is opaque and resolved SERVER-side
// against the active environment, so the client never maps a code to a
// student itself and a foreign badge simply 404s.
export const scannerApi = {
  resolve: (token, session_id) => api.post("/scheduling/scan/resolve/", { token, session_id }, T),
  attendance: (token, session_id, status = "present") =>
    api.post("/scheduling/scan/attendance/", { token, session_id, status }, T),
  recitation: (token, session_id, status) =>
    api.post("/scheduling/scan/recitation/", { token, session_id, status }, T),
  payment: (token) => api.post("/scheduling/scan/payment/", { token }, T),
  rotateBadge: (enrollmentId) => api.post(`/scheduling/scan/badge/${enrollmentId}/rotate/`, {}, T),
};

export const schedulingApi = {
  schedules: {
    list: (params) => api.get(`/scheduling/schedules/${qs(params)}`, T),
    create: (payload) => api.post("/scheduling/schedules/", payload, T),
    remove: (id) => api.delete(`/scheduling/schedules/${id}/`, T),
  },
  sessions: {
    list: (params) => api.get(`/scheduling/sessions/${qs(params)}`, T),
    create: (payload) => api.post("/scheduling/sessions/", payload, T),
    bulk: (payload) => api.post("/scheduling/sessions/bulk/", payload, T),
    reschedule: (id, scheduled_at, ends_at) =>
      api.patch(
        `/scheduling/sessions/${id}/`,
        { scheduled_at, ...(ends_at ? { ends_at } : {}) },
        T
      ),
    generate: (payload) => api.post("/scheduling/sessions/generate/", payload, T),
    open: (id) => api.post(`/scheduling/sessions/${id}/open/`, {}, T),
    close: (id) => api.post(`/scheduling/sessions/${id}/close/`, {}, T),
    reopen: (id) => api.post(`/scheduling/sessions/${id}/reopen/`, {}, T),
    roster: (id) => api.get(`/scheduling/sessions/${id}/roster/`, T),
    // Self check-in link (QR token + announced code) for one open session.
    checkin: {
      get: (id) => api.get(`/scheduling/sessions/${id}/checkin/`, T),
      create: (id) => api.post(`/scheduling/sessions/${id}/checkin/`, {}, T),
      revoke: (id) => api.delete(`/scheduling/sessions/${id}/checkin/`, T),
    },
    remove: (id) => api.delete(`/scheduling/sessions/${id}/`, T),
    // students of OTHER groups who attend this session as guests
    guestCandidates: (id, q) =>
      api.get(`/scheduling/sessions/${id}/guest-candidates/${qs({ q })}`, T),
    addGuest: (id, enrollment_id, home_session_id) =>
      api.post(
        `/scheduling/sessions/${id}/guests/`,
        { enrollment_id, ...(home_session_id ? { home_session_id } : {}) },
        T
      ),
    markGuest: (id, enrollment_id, body) =>
      apiPut(`/scheduling/sessions/${id}/guests/${enrollment_id}/`, body),
    removeGuest: (id, enrollment_id) =>
      api.delete(`/scheduling/sessions/${id}/guests/${enrollment_id}/`, T),
  },
  markAttendance: (session_id, enrollment_id, status) =>
    apiPut("/scheduling/attendance/mark/", { session_id, enrollment_id, status }),
  markRecitation: (session_id, enrollment_id, status) =>
    apiPut("/scheduling/recitation/mark/", { session_id, enrollment_id, status }),
};

// api.js has no put(); one-liner using the same client.
import { apiFetch } from "./api.js";
function apiPut(path, body) {
  return apiFetch(path, { method: "PUT", body, tenant: true });
}

export const financialsApi = {
  sheet: (params) => api.get(`/financials/monthly/${qs(params)}`, T),
  mark: (enrollment_id, month, status, note = "") =>
    apiPut("/financials/monthly/", { enrollment_id, month, status, note }),
  history: (enrollmentId) => api.get(`/financials/enrollments/${enrollmentId}/history/`, T),
};

export const evaluationApi = {
  sheet: (params) => api.get(`/evaluation/monthly/${qs(params)}`, T),
  setRating: (enrollment_id, month, value) =>
    apiPut("/evaluation/ratings/", { enrollment_id, month, value }),
  publishRating: (enrollment_id, month) =>
    api.post("/evaluation/ratings/publish/", { enrollment_id, month }, T),
  publishAll: (payload) => api.post("/evaluation/ratings/publish-all/", payload, T),
  setState: (enrollment_id, month, state) =>
    apiPut("/evaluation/states/", { enrollment_id, month, state }),
  notes: {
    list: (enrollmentId) => api.get(`/evaluation/notes/${qs({ enrollment_id: enrollmentId })}`, T),
    create: (enrollment_id, body) => api.post("/evaluation/notes/", { enrollment_id, body }, T),
    update: (id, body) => api.patch(`/evaluation/notes/${id}/`, { body }, T),
    remove: (id) => api.delete(`/evaluation/notes/${id}/`, T),
  },
  recommend: (enrollment_id, month, idempotency_key) =>
    api.post("/ai/state-recommendations/", { enrollment_id, month, idempotency_key }, T),
  operation: (id) => api.get(`/ai/operations/${id}/`, T),
};

export const contentApi = {
  list: (params) => api.get(`/content/${qs(params)}`, T),
  create: (payload) => api.post("/content/", payload, T),
  update: (id, payload) => api.patch(`/content/${id}/`, payload, T),
  remove: (id) => api.delete(`/content/${id}/`, T),
  publish: (id) => api.post(`/content/${id}/publish/`, {}, T),
  transcript: (id) => api.get(`/content/${id}/transcript/`, T),
  retryTranscript: (id) => api.post(`/content/${id}/transcript/`, {}, T),

  // --- uploaded video (resumable) ---
  /**
   * Uploads in chunks against a server-held offset, so a dropped connection
   * resumes instead of restarting. The server is the authority on the offset:
   * on a mismatch (409) we adopt ITS value rather than trusting our own.
   */
  async uploadVideo(id, file, onProgress, { signal } = {}) {
    const created = await api.post(
      `/content/${id}/uploads/`,
      {
        filename: file.name,
        total_bytes: file.size,
        content_type: file.type || "",
      },
      T
    );

    const url = `${BASE_URL}/content/uploads/${created.id}/`;
    const chunkSize = created.max_chunk_bytes || 8 * 1024 * 1024;
    let offset = created.offset || 0;
    let attempts = 0;

    while (offset < file.size) {
      if (signal?.aborted) throw new ApiError(0, { detail: "تم إلغاء الرفع." });
      const end = Math.min(offset + chunkSize, file.size);
      let res;
      try {
        res = await authFetch(url, {
          method: "PATCH",
          headers: {
            "Upload-Offset": String(offset),
            "Content-Type": "application/offset+octet-stream",
          },
          body: file.slice(offset, end),
          signal,
        });
      } catch (networkError) {
        // A transient drop: ask the server where it actually got to and retry
        // from there. This is the whole point of a resumable upload.
        if (++attempts > 5 || signal?.aborted) throw new ApiError(0, null);
        await new Promise((r) => setTimeout(r, 1000 * attempts));
        const probe = await authFetch(url).catch(() => null);
        if (probe?.ok) offset = (await probe.json()).offset ?? offset;
        continue;
      }

      if (res.status === 409) {
        offset = (await res.json()).offset ?? offset; // re-sync, do not guess
        continue;
      }
      if (!res.ok) {
        let data = null;
        try {
          data = await res.json();
        } catch {
          /* empty */
        }
        throw new ApiError(res.status, data);
      }

      attempts = 0;
      const body = await res.json();
      offset = body.offset ?? end;
      onProgress?.(Math.round((offset / file.size) * 100));
      if (body.is_complete) return body;
    }
    return { is_complete: true };
  },
  uploadStatus: (sessionId) => api.get(`/content/uploads/${sessionId}/`, T),
  abortUpload: (sessionId) => api.delete(`/content/uploads/${sessionId}/`, T),
  removeVideo: (id) => api.delete(`/content/${id}/video/`, T),
  playbackTicket: (id) => api.post(`/content/${id}/playback-ticket/`, {}, T),
  watchers: (id) => api.get(`/content/${id}/watchers/`, T),
};

export const notificationsApi = {
  list: (params) => api.get(`/notifications/${qs(params)}`, T),
  summary: () => api.get("/notifications/summary/", T),
  broadcasts: () => api.get("/notifications/broadcasts/", T),
  broadcastDetail: (id) => api.get(`/notifications/broadcasts/${id}/`, T),
  broadcast: (payload) => api.post("/notifications/broadcast/", payload, T),
  retryFailed: () => api.post("/notifications/retry-failed/", {}, T),
};

// Billing (teacher owner only). The server decides everything: prices, caps, trial dates, whether a
// payment succeeded. The client sends a plan KEY and nothing else (no amount, no environment id).
export const billingApi = {
  plans: () => api.get("/billing/plans/", T),
  subscription: () => api.get("/billing/subscription/", T),
  history: (page) => api.get(`/billing/history/${qs({ page })}`, T),
  checkout: (plan_key) => api.post("/billing/checkout/", { plan_key }, T),
  checkoutStatus: (attemptId) =>
    api.get(`/billing/checkout/return/${qs({ attempt_id: attemptId })}`, T),
  cancel: () => api.post("/billing/subscription/cancel/", {}, T),
};
