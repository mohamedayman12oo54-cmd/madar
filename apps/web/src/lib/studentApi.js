// Student Area wrappers. Every call is scoped to the student's ONE active
// environment by the server-derived header (lib/api.js `tenant: true`); no
// function accepts an enrollment/student id — the server knows who is asking.
import { api } from "./api.js";
import { qs } from "./dashboardApi.js";

const T = { tenant: true };

export const studentApi = {
  overview: () => api.get("/student/overview/", T),
  attendance: () => api.get("/student/attendance/", T),
  recitation: () => api.get("/student/recitation/", T),
  payments: () => api.get("/student/payments/", T),
  evaluation: () => api.get("/student/evaluation/", T),
  videos: () => api.get("/student/videos/", T),
  video: (id) => api.get(`/student/videos/${id}/`, T),
  materials: (kind) => api.get(`/student/materials/${qs({ kind })}`, T),
  material: (id) => api.get(`/student/materials/${id}/`, T),
  documentTicket: (id) => api.post(`/content/${id}/document-ticket/`, {}, T),
  playbackTicket: (id, quality) =>
    api.post(`/content/${id}/playback-ticket/`, quality ? { quality } : {}, T),
  videoProgress: (id, position_seconds, duration_seconds) =>
    api.put(`/content/${id}/progress/`, { position_seconds, duration_seconds }, T),
  notifications: {
    list: (params) => api.get(`/student/notifications/${qs(params)}`, T),
    read: (id) => api.post(`/student/notifications/${id}/read/`, {}, T),
    readAll: () => api.post("/student/notifications/read-all/", {}, T),
  },
  quizzes: {
    list: () => api.get("/student/quizzes/", T),
    request: (content_id, idempotency_key) =>
      api.post("/student/quizzes/", { content_id, idempotency_key }, T),
    operation: (id) => api.get(`/student/quizzes/operations/${id}/`, T),
    get: (id) => api.get(`/student/quizzes/${id}/`, T),
    submit: (id, answers) => api.post(`/student/quizzes/${id}/submit/`, { answers }, T),
  },
  // same shape as aiApi so the assistant page is shared with the teacher
  assistant: {
    submit: (prompt, idempotencyKey) =>
      api.post("/student/assistant/", { prompt, idempotency_key: idempotencyKey }, T),
    get: (id) => api.get(`/student/assistant/${id}/`, T),
    list: () => api.get("/student/assistant/", T),
  },
};
