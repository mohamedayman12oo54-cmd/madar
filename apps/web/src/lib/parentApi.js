// Guardian (ولي الأمر) portal. A guardian has NO account: they prove they control
// the phone the teacher recorded plus the child's student code, and receive a read-only, short-lived
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
    if (s.expires_at && Date.now() > s.expires_at) {
      sessionStorage.removeItem(KEY);
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

export function saveParentSession(data) {
  const children = (data.children && data.children.length ? data.children : [data]).map((c) => ({
    token: c.token,
    student_name: c.student_name,
    grade: c.grade,
    teacher_environment: c.teacher_environment,
  }));
  const s = { children, active: 0, expires_at: Date.now() + (data.expires_in || 21600) * 1000 };
  try {
    sessionStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* private mode: portal still works for this render */
  }
  return s;
}

export function setActiveChild(index) {
  const s = getParentSession();
  if (!s || !s.children[index]) return s;
  s.active = index;
  try {
    sessionStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
  return s;
}

/** Swap every child's token for a fresh one (the server accepts a still-valid token and issues a new one), so a
 *  portal tab that stays open never expires under the guardian. A child the server no longer accepts (the
 *  teacher changed the phone, the student was deactivated) is dropped; with none left the session is over.
 *  A network failure keeps the current tokens. Returns the updated session, or null when it is over. */
export async function renewParentSession() {
  const s = getParentSession();
  if (!s) return null;
  const kept = [];
  let ttl = null;
  let activeToken = s.children[s.active]?.token;
  for (const c of s.children) {
    try {
      const r = await api.post("/parent/renew/", {}, withParent(c.token));
      kept.push({ ...c, token: r.token });
      ttl = r.expires_in || ttl;
      if (c.token === activeToken) activeToken = r.token;
    } catch (e) {
      if (e?.status === 401) continue;
      kept.push(c); // offline / 5xx: nothing is known about this session, keep it
    }
  }
  if (!kept.length) {
    clearParentSession();
    return null;
  }
  const next = {
    ...s,
    children: kept,
    active: Math.max(0, kept.findIndex((c) => c.token === activeToken)),
    expires_at: ttl ? Date.now() + ttl * 1000 : s.expires_at,
  };
  try {
    sessionStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
  return next;
}

export function clearParentSession() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

const withParent = (token) => ({ authorization: `Parent ${token}` });

export const parentApi = {
  // Phone the teacher recorded for the guardian + the child's student code.
  login: (phone, student_code) => api.post("/parent/login/", { phone, student_code }),
  overview: (token) => api.get("/parent/overview/", withParent(token)),
};
