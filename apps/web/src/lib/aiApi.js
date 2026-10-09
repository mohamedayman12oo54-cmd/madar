// Tenant-scoped wrappers around the Phase 5 AI endpoints. The flow is
// ASYNCHRONOUS by design: submit() returns immediately with an operation id
// (status "pending"); get() polls it until it is "completed" or "failed".
import { api } from "./api.js";

export const aiApi = {
  submit: (prompt, idempotencyKey) =>
    api.post("/ai/operations/", { prompt, idempotency_key: idempotencyKey }, { tenant: true }),
  get: (id) => api.get(`/ai/operations/${id}/`, { tenant: true }),
  list: () => api.get("/ai/operations/", { tenant: true }),
};

export const AI_TERMINAL = new Set(["completed", "failed"]);
