// Tenant-scoped wrappers around the Phase 4 evaluation endpoints (see
// madar-backend/evaluation/urls.py).
import { api } from "./api.js";

function qs(params) {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}

export const notesApi = {
  list: (params) => api.get(`/evaluation/notes/${qs(params)}`, { tenant: true }),
  create: (payload) => api.post("/evaluation/notes/", payload, { tenant: true }),
  remove: (id) => api.delete(`/evaluation/notes/${id}/`, { tenant: true }),
};

export const ratingsApi = {
  list: (params) => api.get(`/evaluation/ratings/${qs(params)}`, { tenant: true }),
  create: (payload) => api.post("/evaluation/ratings/", payload, { tenant: true }),
  remove: (id) => api.delete(`/evaluation/ratings/${id}/`, { tenant: true }),
};
