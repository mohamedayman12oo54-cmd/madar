// Tenant-scoped wrappers around the Phase 2 academics endpoints (see
// madar-backend/academics/urls.py). Every call uses { tenant: true } — the
// active environment header is attached automatically by lib/api.js from
// whatever src/state/environment.jsx currently has selected; nothing here
// ever passes an environment id itself.
import { api } from "./api.js";

function qs(params) {
  const entries = Object.entries(params || {}).filter(
    ([, v]) => v !== undefined && v !== null && v !== ""
  );
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}

export const gradesApi = {
  list: () => api.get("/academics/grades/", { tenant: true }),
  create: (payload) => api.post("/academics/grades/", payload, { tenant: true }),
  update: (id, payload) => api.patch(`/academics/grades/${id}/`, payload, { tenant: true }),
  remove: (id) => api.delete(`/academics/grades/${id}/`, { tenant: true }),
};

export const groupsApi = {
  list: (params) => api.get(`/academics/groups/${qs(params)}`, { tenant: true }),
  create: (payload) => api.post("/academics/groups/", payload, { tenant: true }),
  update: (id, payload) => api.patch(`/academics/groups/${id}/`, payload, { tenant: true }),
  remove: (id) => api.delete(`/academics/groups/${id}/`, { tenant: true }),
};

export const enrollmentsApi = {
  get: (id) => api.get(`/academics/enrollments/${id}/`, { tenant: true }),
  list: (params) => api.get(`/academics/enrollments/${qs(params)}`, { tenant: true }),
  create: (payload) => api.post("/academics/enrollments/", payload, { tenant: true }),
  update: (id, payload) => api.patch(`/academics/enrollments/${id}/`, payload, { tenant: true }),
};

// The teacher's student self-registration link (the QR in "add student").
export const registrationApi = {
  get: () => api.get("/academics/registration-link/", { tenant: true }),
  create: () => api.post("/academics/registration-link/", {}, { tenant: true }),
  revoke: () => api.delete("/academics/registration-link/", { tenant: true }),
};
