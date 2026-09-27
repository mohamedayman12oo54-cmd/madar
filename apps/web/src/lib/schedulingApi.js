// Tenant-scoped wrappers around the Phase 3 scheduling endpoints (see
// madar-backend/scheduling/urls.py). Same convention as academicsApi.js:
// every call uses { tenant: true } — the active environment header is
// attached automatically from src/state/environment.jsx.
import { api } from "./api.js";

function qs(params) {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}

export const sessionsApi = {
  list: (params) => api.get(`/scheduling/sessions/${qs(params)}`, { tenant: true }),
  get: (id) => api.get(`/scheduling/sessions/${id}/`, { tenant: true }),
  create: (payload) => api.post("/scheduling/sessions/", payload, { tenant: true }),
  reschedule: (id, scheduled_at) => api.patch(`/scheduling/sessions/${id}/`, { scheduled_at }, { tenant: true }),
  open: (id) => api.post(`/scheduling/sessions/${id}/open/`, undefined, { tenant: true }),
  close: (id) => api.post(`/scheduling/sessions/${id}/close/`, undefined, { tenant: true }),
  reopen: (id) => api.post(`/scheduling/sessions/${id}/reopen/`, undefined, { tenant: true }),
};

export const attendanceApi = {
  list: (params) => api.get(`/scheduling/attendance/${qs(params)}`, { tenant: true }),
  setStatus: (id, status) => api.patch(`/scheduling/attendance/${id}/`, { status }, { tenant: true }),
};
