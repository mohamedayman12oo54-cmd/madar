// Exams — teacher (build / publish / results) and student (take). The student endpoints never accept an
// enrollment id: the server derives the student from the token and the active environment.
import { api } from "./api.js";

const T = { tenant: true };

export const examsApi = {
  list: () => api.get("/exams/", T),
  get: (id) => api.get(`/exams/${id}/`, T),
  create: (body) => api.post("/exams/", body, T),
  update: (id, body) => api.put(`/exams/${id}/`, body, T),
  remove: (id) => api.delete(`/exams/${id}/`, T),
  publish: (id) => api.post(`/exams/${id}/publish/`, {}, T),
  results: (id) => api.get(`/exams/${id}/results/`, T),
  // "Something went wrong for this student": allow ONE more sitting. The best score is the one that counts.
  reopen: (id, enrollment_id) => api.post(`/exams/${id}/reopen/`, { enrollment_id }, T),
};

export const studentExamsApi = {
  list: () => api.get("/student/exams/", T),
  start: (id, retake = false) => api.post(`/student/exams/${id}/start/`, retake ? { retake: true } : {}, T),
  question: (id, index) => api.get(`/student/exams/${id}/question/${index}/`, T),
  answer: (id, question_id, choice_id) => api.post(`/student/exams/${id}/answer/`, { question_id, choice_id }, T),
  violation: (id, type) => api.post(`/student/exams/${id}/violation/`, { type }, T),
  submit: (id) => api.post(`/student/exams/${id}/submit/`, {}, T),
  result: (id) => api.get(`/student/exams/${id}/result/`, T),
};
