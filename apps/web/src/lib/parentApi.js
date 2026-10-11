// Guardian (ولي الأمر) portal. A guardian has NO account: they prove they control
// the phone the teacher recorded (OTP), and receive a read-only, short-lived
// session bound to one child. It is kept in sessionStorage — it dies with the
// tab — and sent as `Authorization: Parent <token>`, never as a user JWT.
import { api } from "./api.js";

const KEY = "madar.parent.session";

export function getParentSession() {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw);
    if (!s?.children?.length) return null;
    if (s.expires_at && Date.now() > s.expires_at) { sessionStorage.removeItem(KEY); return null; }
    return s;
  } catch { return null; }
}

export function saveParentSession(data) {
  const children = (data.children && data.children.length ? data.children : [data])
    .map((c) => ({ token: c.token, student_name: c.student_name, grade: c.grade, teacher_environment: c.teacher_environment }));
  const s = { children, active: 0, expires_at: Date.now() + (data.expires_in || 21600) * 1000 };
  try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* private mode: portal still works for this render */ }
  return s;
}

export function setActiveChild(index) {
  const s = getParentSession();
  if (!s || !s.children[index]) return s;
  s.active = index;
  try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ignore */ }
  return s;
}

export function clearParentSession() {
  try { sessionStorage.removeItem(KEY); } catch { /* ignore */ }
}

const FLOW = "parent-access"; // accounts.views.PURPOSE_MAP
const withParent = (token) => ({ authorization: `Parent ${token}` });

export const parentApi = {
  request: (phone) => api.post("/parent/request/", { phone }),
  otpVerify: (pending_id, code) => api.post(`/auth/otp/${FLOW}/verify/`, { pending_id, code }),
  otpResend: (pending_id) => api.post(`/auth/otp/${FLOW}/resend/`, { pending_id }),
  verify: (pending_id) => api.post("/parent/verify/", { pending_id }),
  overview: (token) => api.get("/parent/overview/", withParent(token)),
};
