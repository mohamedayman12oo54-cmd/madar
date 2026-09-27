// Tenant-scoped wrappers around the Phase 4 financials endpoints (see
// madar-backend/financials/urls.py).
import { api } from "./api.js";

function qs(params) {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}

export const paymentsApi = {
  list: (params) => api.get(`/financials/payments/${qs(params)}`, { tenant: true }),
  create: (payload) => api.post("/financials/payments/", payload, { tenant: true }),
  update: (id, payload) => api.patch(`/financials/payments/${id}/`, payload, { tenant: true }),
  remove: (id) => api.delete(`/financials/payments/${id}/`, { tenant: true }),
};

export const financialSummaryApi = {
  get: (params) => api.get(`/financials/summary/${qs(params)}`, { tenant: true }),
};
