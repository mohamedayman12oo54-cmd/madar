// Tenant-scoped wrappers around the Phase 5 content endpoints (see
// madar-backend/content/urls.py). Note `video` in responses is provider-
// neutral ({provider, embed_url, thumbnail_url}) — the frontend never builds
// or parses a YouTube/Vimeo URL itself, and only ever SENDS an opaque
// {video_provider, video_ref} pair the backend validates strictly.
import { api } from "./api.js";

function qs(params) {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}

export const contentApi = {
  list: (params) => api.get(`/content/${qs(params)}`, { tenant: true }),
  create: (payload) => api.post("/content/", payload, { tenant: true }),
  update: (id, payload) => api.patch(`/content/${id}/`, payload, { tenant: true }),
  remove: (id) => api.delete(`/content/${id}/`, { tenant: true }),
};
