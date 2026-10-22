// Public self check-in (no login): a student who scanned the teacher's QR marks THEMSELVES present
// with their platform phone number + the code the teacher announced. The token comes from the QR link.
import { api } from "./api.js";

const seg = (token) => encodeURIComponent(token || "");

export const checkinApi = {
  info: (token) => api.get(`/scheduling/checkin/${seg(token)}/`),
  submit: (token, phone, code) =>
    api.post(`/scheduling/checkin/${seg(token)}/submit/`, { phone, code }),
};
