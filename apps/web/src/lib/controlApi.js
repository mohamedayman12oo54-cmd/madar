// Madar Control Center (role "team") and the customers' support API. Authorisation is decided by the server on
// every request (control/access.py); nothing here is tenant-scoped, so no environment header is sent.
import { api, authFetch, BASE_URL } from "./api.js";

const AUTH = { auth: true };

export const qs = (params) => {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "" && v !== false);
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()}` : "";
};

const get = (path, params) => api.get(`${path}${qs(params)}`, AUTH);

/** Multipart when files are attached, JSON otherwise. */
function withFiles(path, fields, files) {
  if (!files || files.length === 0) return api.post(path, fields, AUTH);
  const fd = new FormData();
  Object.entries(fields).forEach(([k, v]) => v !== undefined && v !== null && fd.append(k, String(v)));
  files.forEach((f) => fd.append("files", f));
  return api.post(path, fd, { ...AUTH, raw: true });
}

/** An authenticated download (CSV export / ticket attachment): the browser cannot attach the bearer header to a
 *  plain link, so the file is fetched and handed to the user as a blob. */
export async function downloadFile(path, params, fallbackName = "download") {
  const res = await authFetch(`${BASE_URL}${path}${qs(params)}`);
  if (!res.ok) {
    let msg = "تعذّر تنزيل الملف.";
    try {
      msg = (await res.json()).detail || msg;
    } catch {
      /* not json */
    }
    throw new Error(msg);
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = m ? decodeURIComponent(m[1]) : fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const controlApi = {
  me: () => get("/control/me/"),
  overview: (p) => get("/control/overview/", p),
  feed: () => get("/control/feed/"),
  search: (q) => get("/control/search/", { q }),
  recipients: (q, kind) => get("/control/recipients/", { q, kind }),

  users: (p) => get("/control/users/", p),
  user: (id) => get(`/control/users/${id}/`),
  updateUser: (id, body) => api.patch(`/control/users/${id}/`, body, AUTH),
  suspendUser: (id, reason) => api.post(`/control/users/${id}/suspend/`, { reason }, AUTH),
  restoreUser: (id, reason) => api.post(`/control/users/${id}/restore/`, { reason }, AUTH),
  userActivity: (id) => get(`/control/users/${id}/activity/`),
  userTickets: (id) => get(`/control/users/${id}/tickets/`),
  userNotifications: (id) => get(`/control/users/${id}/notifications/`),
  userHistory: (id) => get(`/control/users/${id}/history/`),
  teachers: (p) => get("/control/teachers/", p),
  students: (p) => get("/control/students/", p),
  parents: (p) => get("/control/parents/", p),
  parent: (phone) => get(`/control/parents/${phone}/`),

  team: (p) => get("/control/team/", p),
  member: (id) => get(`/control/team/${id}/`),
  updateMember: (id, body) => api.patch(`/control/team/${id}/`, body, AUTH),
  memberTickets: (id) => get(`/control/team/${id}/tickets/`),
  memberActivity: (id) => get(`/control/team/${id}/activity/`),
  roles: () => get("/control/roles/"),
  createRole: (body) => api.post("/control/roles/", body, AUTH),
  updateRole: (id, body) => api.patch(`/control/roles/${id}/`, body, AUTH),
  deleteRole: (id) => api.delete(`/control/roles/${id}/`, AUTH),
  permissions: () => get("/control/permissions/"),

  environments: (p) => get("/control/environments/", p),
  environment: (id) => get(`/control/environments/${id}/`),
  updateEnvironment: (id, body) => api.patch(`/control/environments/${id}/`, body, AUTH),

  supportOverview: (p) => get("/control/support/overview/", p),
  supportAnalytics: (p) => get("/control/support/analytics/", p),
  agents: () => get("/control/support/agents/"),
  categories: () => get("/control/support/categories/"),
  createCategory: (body) => api.post("/control/support/categories/", body, AUTH),
  updateCategory: (id, body) => api.patch(`/control/support/categories/${id}/`, body, AUTH),
  deleteCategory: (id) => api.delete(`/control/support/categories/${id}/`, AUTH),
  tickets: (p) => get("/control/support/tickets/", p),
  ticket: (id) => get(`/control/support/tickets/${id}/`),
  createTicket: (fields, files) => withFiles("/control/support/tickets/", fields, files),
  bulkTickets: (body) => api.post("/control/support/tickets/bulk/", body, AUTH),
  replyTicket: (id, fields, files) => withFiles(`/control/support/tickets/${id}/messages/`, fields, files),
  setTicketStatus: (id, status, note) => api.post(`/control/support/tickets/${id}/status/`, { status, note }, AUTH),
  setTicketPriority: (id, priority) => api.post(`/control/support/tickets/${id}/priority/`, { priority }, AUTH),
  setTicketCategory: (id, category) => api.post(`/control/support/tickets/${id}/category/`, { category }, AUTH),
  assignTicket: (id, assignee) => api.post(`/control/support/tickets/${id}/assign/`, { assignee }, AUTH),
  downloadAttachment: (id, name) => downloadFile(`/control/support/attachments/${id}/`, null, name),

  financeOverview: (p) => get("/control/finance/overview/", p),
  transactions: (p) => get("/control/finance/transactions/", p),
  subscriptions: (p) => get("/control/finance/subscriptions/", p),
  plans: () => get("/control/finance/plans/"),
  paymentIssues: () => get("/control/finance/issues/"),

  aiOverview: (p) => get("/control/ai/overview/", p),
  aiOperations: (p) => get("/control/ai/operations/", p),
  aiOperation: (id) => get(`/control/ai/operations/${id}/`),

  notificationOverview: (p) => get("/control/notifications/overview/", p),
  notifications: (p) => get("/control/notifications/", p),
  notification: (id) => get(`/control/notifications/${id}/`),
  platformNotices: (p) => get("/control/notifications/platform/", p),
  sendNotice: (body) => api.post("/control/notifications/platform/", body, AUTH),
  templates: () => get("/control/notifications/templates/"),
  createTemplate: (body) => api.post("/control/notifications/templates/", body, AUTH),
  updateTemplate: (id, body) => api.patch(`/control/notifications/templates/${id}/`, body, AUTH),
  deleteTemplate: (id) => api.delete(`/control/notifications/templates/${id}/`, AUTH),

  reports: () => get("/control/reports/"),
  report: (name, p) => get(`/control/reports/${name}/`, p),
  exportReport: (name, p) => downloadFile(`/control/reports/${name}/`, { ...p, export: "csv" }, `madar-${name}.csv`),
  audit: (p) => get("/control/audit/", p),
  exportAudit: (p) => downloadFile("/control/audit/", { ...p, export: "csv" }, "audit-log.csv"),
  exportTickets: (p) => downloadFile("/control/support/tickets/", { ...p, export: "csv" }, "tickets.csv"),
  exportTransactions: (p) => downloadFile("/control/finance/transactions/", { ...p, export: "csv" }, "transactions.csv"),

  health: () => get("/control/system/health/"),
  jobs: (p) => get("/control/system/jobs/", p),
  settings: () => get("/control/settings/"),
  saveSettings: (body) => api.patch("/control/settings/", body, AUTH),
};

// Teachers and students: their OWN tickets only (the server filters by the signed-in account).
export const supportApi = {
  categories: () => get("/control/customer/categories/"),
  list: () => get("/control/customer/tickets/"),
  create: (fields, files) => withFiles("/control/customer/tickets/", fields, files),
  get: (id) => get(`/control/customer/tickets/${id}/`),
  reply: (id, body, files) => withFiles(`/control/customer/tickets/${id}/messages/`, { body }, files),
  rate: (id, rating, comment) => api.post(`/control/customer/tickets/${id}/rate/`, { rating, comment }, AUTH),
  downloadAttachment: (id, name) => downloadFile(`/control/customer/attachments/${id}/`, null, name),
};
