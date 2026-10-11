/**
 * Guests of a session: students of ANOTHER group who came to this one.
 *
 * Their attendance / recitation are taken here as usual, but are filed as a
 * visit and carried into THEIR OWN group's session when that opens - so they
 * are counted once, in the right place. Payment is monthly (not tied to a
 * session) and is recorded straight away.
 */
import { useEffect, useState } from "react";
import { UserPlus, Wallet, X } from "lucide-react";
import { Banner, Btn, Modal } from "../auth/ui.jsx";
import { financialsApi, schedulingApi } from "../lib/dashboardApi.js";
import { ApiError } from "../lib/api.js";
import { Empty, currentMonthValue, fmtDateTime, useDebounced } from "./common.jsx";

const msg = (e, fallback) => (e instanceof ApiError ? e.message : fallback);
const sessionLabel = (s) => `${s.group} — ${fmtDateTime(s.scheduled_at)}`;

function AddGuestModal({ sessionId, onClose, onAdded }) {
  const [q, setQ] = useState("");
  const debounced = useDebounced(q);
  const [rows, setRows] = useState(null);
  const [target, setTarget] = useState({}); // enrollment_id -> chosen home session id ("" = first one that opens)
  const [busyId, setBusyId] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    schedulingApi.sessions.guestCandidates(sessionId, debounced.trim())
      .then((d) => { if (live) setRows(d.results || []); })
      .catch((e) => { if (live) setErr(msg(e, "تعذّر تحميل الطلاب.")); });
    return () => { live = false; };
  }, [sessionId, debounced]);

  const add = async (c) => {
    setBusyId(c.enrollment_id); setErr(null);
    const chosen = target[c.enrollment_id] ?? (c.upcoming[0]?.id ? String(c.upcoming[0].id) : "");
    try { onAdded(await schedulingApi.sessions.addGuest(sessionId, c.enrollment_id, chosen ? Number(chosen) : null)); }
    catch (e) { setErr(msg(e, "تعذّرت الإضافة.")); }
    finally { setBusyId(null); }
  };

  return (
    <Modal size="md" title="إضافة طالب من مجموعة أخرى"
      text="اختر الطالب، وحدّد جلسة مجموعته التي تُغني عنها هذه الزيارة. سيُسجَّل حضوره وتسميعه فيها تلقائيًا عند فتحها." onClose={onClose}>
      <div className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <input className="inp" type="search" placeholder="ابحث باسم الطالب" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
        {rows === null ? <p className="field-msg">جاري التحميل...</p>
          : rows.length === 0 ? <Empty title="لا يوجد طلاب مطابقون" text="الطلاب من مجموعة هذه الجلسة لا يظهرون هنا." />
          : (
            <div className="list-rows guest-pick">
              {rows.map((c) => (
                <div key={c.enrollment_id} className="list-row guest-pick-row">
                  <div className="guest-pick-main">
                    <strong>{c.name}</strong>
                    <span className="stat-sub">{c.grade}{c.groups.length ? ` · ${c.groups.join("، ")}` : ""}</span>
                    <select className="inp" aria-label="الجلسة التي تُغني عنها الزيارة"
                      value={target[c.enrollment_id] ?? (c.upcoming[0]?.id ? String(c.upcoming[0].id) : "")}
                      onChange={(e) => setTarget((t) => ({ ...t, [c.enrollment_id]: e.target.value }))}>
                      {c.upcoming.map((s) => <option key={s.id} value={s.id}>{sessionLabel(s)}</option>)}
                      <option value="">أول جلسة تُفتح لمجموعته</option>
                    </select>
                  </div>
                  <Btn loading={busyId === c.enrollment_id} onClick={() => add(c)}>إضافة</Btn>
                </div>
              ))}
            </div>
          )}
      </div>
    </Modal>
  );
}

function Pick({ on, onClick, disabled, children }) {
  return <button type="button" className={"mini-btn" + (on ? " is-primary" : "")} aria-pressed={on} disabled={disabled} onClick={onClick}>{children}</button>;
}

function whereNote(g) {
  if (g.applied) return g.home_session ? `✓ سُجّل في جلسة مجموعته: ${sessionLabel(g.home_session)}` : "✓ سُجّل في جلسة مجموعته";
  if (g.home_session) return `سيُسجَّل تلقائيًا في جلسة مجموعته: ${sessionLabel(g.home_session)}`;
  return "سيُسجَّل تلقائيًا في أول جلسة تُفتح لمجموعته.";
}

export default function GuestSection({ sessionId, isOpen, guests, onChanged }) {
  const [modal, setModal] = useState(false);
  const [err, setErr] = useState(null);
  const [paid, setPaid] = useState({});
  const [busy, setBusy] = useState(null);

  const run = async (key, fn) => {
    setBusy(key); setErr(null);
    try { await fn(); await onChanged(); } catch (e) { setErr(msg(e, "تعذّر تنفيذ الإجراء.")); } finally { setBusy(null); }
  };
  const mark = (g, body) => run(`${g.enrollment_id}:m`, () => schedulingApi.sessions.markGuest(sessionId, g.enrollment_id, body));
  const cancel = (g) => run(`${g.enrollment_id}:x`, () => schedulingApi.sessions.removeGuest(sessionId, g.enrollment_id));
  const pay = (g) => run(`${g.enrollment_id}:p`, async () => {
    await financialsApi.mark(g.enrollment_id, currentMonthValue(), "paid");
    setPaid((p) => ({ ...p, [g.enrollment_id]: true }));
  });

  return (
    <section className="guest-sec">
      <div className="dash-section-head">
        <h2>ضيوف من مجموعات أخرى</h2>
        <button type="button" className="mini-btn is-primary" disabled={!isOpen} onClick={() => setModal(true)}><UserPlus size={14} /> إضافة ضيف</button>
      </div>
      {err && <Banner tone="err">{err}</Banner>}
      {guests.length === 0
        ? <p className="field-msg">لا يوجد ضيوف. إن جاء طالب من مجموعة أخرى فأضفه هنا ليُسجَّل حضوره في جلسة مجموعته تلقائيًا.</p>
        : (
          <div className="list-rows">
            {guests.map((g) => {
              const locked = !isOpen || busy?.startsWith(`${g.enrollment_id}:`);
              return (
                <div key={g.enrollment_id} className="list-row guest-row">
                  <div className="guest-main">
                    <strong>{g.name}</strong>
                    <span className="guest-note">{whereNote(g)}</span>
                  </div>
                  <div className="row-actions">
                    <Pick on={g.attendance === "present"} disabled={locked} onClick={() => mark(g, { attendance: "present" })}>حاضر</Pick>
                    <Pick on={g.attendance === "absent"} disabled={locked} onClick={() => mark(g, { attendance: "absent" })}>غائب</Pick>
                    <Pick on={g.recitation === "studied"} disabled={locked} onClick={() => mark(g, { recitation: "studied" })}>ذاكر</Pick>
                    <Pick on={g.recitation === "not_studied"} disabled={locked} onClick={() => mark(g, { recitation: "not_studied" })}>لم يذاكر</Pick>
                    <button type="button" className={"mini-btn" + (paid[g.enrollment_id] ? " is-primary" : "")} disabled={locked} onClick={() => pay(g)}>
                      <Wallet size={13} /> {paid[g.enrollment_id] ? "دُفع هذا الشهر" : "تسجيل دفع الشهر"}
                    </button>
                    {!g.applied && <button type="button" className="mini-btn danger" disabled={locked} aria-label={`إلغاء زيارة ${g.name}`} onClick={() => cancel(g)}><X size={13} /> إلغاء</button>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      {modal && <AddGuestModal sessionId={sessionId} onClose={() => setModal(false)} onAdded={async () => { setModal(false); await onChanged(); }} />}
    </section>
  );
}
