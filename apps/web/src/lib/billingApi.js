// Tenant-scoped wrappers around the billing endpoints (backend/billing/urls.py).
// Nothing here ever sends a price, amount or status: the server decides all of it.
import { api } from "./api.js";

export const billingApi = {
  plans: () => api.get("/billing/plans/", { auth: true }),
  subscription: () => api.get("/billing/subscription/", { tenant: true }),
  history: () => api.get("/billing/history/", { tenant: true }),
  startCheckout: (planKey) =>
    api.post("/billing/checkout/", { plan_key: planKey }, { tenant: true }),
  checkoutStatus: (attemptId) =>
    api.get(`/billing/checkout/return/?attempt_id=${encodeURIComponent(attemptId)}`, {
      tenant: true,
    }),
  cancel: () => api.post("/billing/subscription/cancel/", {}, { tenant: true }),
};

export const asList = (d) => (Array.isArray(d) ? d : d?.results || []);
