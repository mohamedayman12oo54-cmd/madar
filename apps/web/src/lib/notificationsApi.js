// Tenant-scoped wrappers around the Phase 5 notifications endpoints.
import { api } from "./api.js";

export const notificationsApi = {
  list: (params = {}) => {
    const q = params.unread ? "?unread=true" : "";
    return api.get(`/notifications/${q}`, { tenant: true });
  },
  markRead: (id) => api.post(`/notifications/${id}/read/`, undefined, { tenant: true }),
  unreadCount: () => api.get("/notifications/unread-count/", { tenant: true }),
};
