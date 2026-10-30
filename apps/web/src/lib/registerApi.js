// Public student self-registration (no login): a student who scanned the teacher's QR fills the form.
// The token comes from the QR link. The server never returns the student's badge code.
import { api } from "./api.js";

const seg = (token) => encodeURIComponent(token || "");

export const registerApi = {
  info: (token) => api.get(`/academics/register/${seg(token)}/`),
  submit: (token, payload) => api.post(`/academics/register/${seg(token)}/submit/`, payload),
};
