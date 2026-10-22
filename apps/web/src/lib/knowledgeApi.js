// Content Maintainer (role "team") surface for the central Knowledge Base. The KB belongs to Madar,
// not to any teacher environment, so none of these calls carries an environment header: authorisation
// is the maintainer role alone, checked by the server on every request.
import { api } from "./api.js";

const AUTH = { auth: true };

const qs = (params) => {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
};

export const knowledgeApi = {
  list: (params) => api.get(`/knowledge/documents/${qs(params)}`, AUTH),
  create: (payload) => api.post("/knowledge/documents/", payload, AUTH),
  update: (id, payload) => api.patch(`/knowledge/documents/${id}/`, payload, AUTH),
  remove: (id) => api.delete(`/knowledge/documents/${id}/`, AUTH),
  publish: (id) => api.post(`/knowledge/documents/${id}/publish/`, {}, AUTH),
  unpublish: (id) => api.post(`/knowledge/documents/${id}/unpublish/`, {}, AUTH),
};
