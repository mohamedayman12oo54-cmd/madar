import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarPlus, Wand2 } from "lucide-react";
import { Field, Btn, Banner, Modal } from "../auth/ui.jsx";
import { schedulingApi } from "../lib/dashboardApi.js";
import { ApiError } from "../lib/api.js";
import { useGroups } from "./useGroups.js";
import { groupByDay, timeLabel } from "../lib/dates.js";
import { Confirm, Empty, PageHeader, fmtDateTime } from "./common.jsx";

const STATUS = { planned: "مخططة", open: "مفتوحة", closed: "مغلقة" };
const TONE = { planned: "", open: "good", closed: "warn" };
const listOf = (d) => (Array.isArray(d) ? d : d?.results || []);
const toIso = (local) => new Date(local).toISOString();
const toLocalInput = (iso) => { const d = new Date(iso); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };

function AddSessionModal({ groups, onClose, onCreated }) {
  const [groupId, setGroupId] = useState(groups[0]?.id || "");
  const [when, setWhen] = useState(toLocalInput(new Date().toISOString()));
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(null); setSaving(true);
    try { await schedulingApi.sessions.create({ group_id: Number(groupId), scheduled_at: toIso(when) }); onCreated(); }
    catch (e2) { setErr(e2 instanceof ApiError ? (e2.fields ? Object.values(e2.fields).flat().join(" ") : e2.message) : "تعذّر إنشاء الجلسة."); }
    finally { setSaving(false); }
  };
  return (
    <Modal size="md" title="جلسة إضافية (تعويض أو خارج الموعد)" text="يمكنك تسجيل حصة فعلية حتى لو لم تكن ضمن المواعيد الأسبوعية." onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="المجموعة" required>
          <select className="inp" value={groupId} onChange={(e) => setGroupId(e.target.value)}>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select>
        </Field>
        <Field label="التاريخ والوقت" required><input className="inp" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} required /></Field>
        <Btn type="submit" loading={saving} loadingText="جارٍ الإنشاء…">إنشاء الجلسة</Btn>
      </form>
    </Modal>
  );
}

function GenerateModal({ groups, onClose, onDone }) {
  const [weeks, setWeeks] = useState(2);
  const [groupId, setGroupId] = useState("");
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(null); setSaving(true);
    try { const r = await schedulingApi.sessions.generate({ weeks, ...(groupId ? { group_id: Number(groupId) } : {}) }); onDone(r.created); }
    catch (e2) { setErr(e2 instanceof ApiError ? e2.message : "تعذّر توليد الجلسات."); }
    finally { setSaving(false); }
  };
  return (
    <Modal size="md" title="توليد جلسات من المواعيد الأسبوعية" text="تُنشأ جلسات «مخططة» للأسابيع القادمة. لا تتكرر الجلسات الموجودة، ويمكنك إعادة التوليد بأمان." onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="عدد الأسابيع (1 إلى 8)"><input className="inp" type="number" min="1" max="8" value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} /></Field>
        <Field label="المجموعة"><select className="inp" value={groupId} onChange={(e) => setGroupId(e.target.value)}><option value="">كل المجموعات</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
        <Btn type="submit" loading={saving} loadingText="جارٍ التوليد…">توليد الجلسات</Btn>
      </form>
    </Modal>
  );
}

function RescheduleModal({ session, onClose, onDone }) {
  const [when, setWhen] = useState(toLocalInput(session.scheduled_at));
  const [err, setErr] = useState(null);
  const submit = async (e) => {
    e.preventDefault(); setErr(null);
    try { await schedulingApi.sessions.reschedule(session.id, toIso(when)); onDone(); }
    catch (e2) { setErr(e2 instanceof ApiError ? e2.message : "تعذّر التعديل."); }
  };
  return (
    <Modal title="تعديل موعد الجلسة" onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="التاريخ والوقت" required><input className="inp" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} required /></Field>
        <Btn type="submit">حفظ</Btn>
      </form>
    </Modal>
  );
}

export default function SessionsPage() {
  const { groups, status: groupsStatus } = useGroups();
  const [groupFilter, setGroupFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [data, setData] = useState({ results: [], next: null, previous: null });
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [modal, setModal] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => { setPage(1); }, [groupFilter, statusFilter]);
  const reload = () => {
    schedulingApi.sessions.list({ group_id: groupFilter, status: statusFilter, page })
      .then((d) => { setData(Array.isArray(d) ? { results: d } : d); setStatus("ready"); })
      .catch((e) => { setError(e instanceof ApiError ? e.message : "تعذّر تحميل الجلسات."); setStatus("error"); });
  };
  useEffect(reload, [groupFilter, statusFilter, page]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (id, fn, okText) => {
    setBusyId(id); setNotice(null);
    try { await fn(id); if (okText) setNotice({ tone: "info", text: okText }); reload(); }
    catch (e) { setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر تنفيذ الإجراء." }); }
    finally { setBusyId(null); }
  };

  return (
    <>
      <PageHeader infoKey="sessions" title="الجلسات">
        <Btn variant="ghost" onClick={() => setModal("generate")} disabled={groups.length === 0}><Wand2 size={16} /> توليد من المواعيد</Btn>
        <Btn onClick={() => setModal("add")} disabled={groups.length === 0}><CalendarPlus size={16} /> جلسة إضافية</Btn>
      </PageHeader>
      {groupsStatus === "ready" && groups.length === 0 && <Banner tone="info">أنشئ مجموعة أولًا من صفحة «المجموعات».</Banner>}
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      <div className="dash-filters">
        <select className="inp" value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)}><option value="">كل المجموعات</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select>
        <select className="inp" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="">كل الحالات</option>{Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      </div>
      {status === "loading" && <p className="field-msg">جاري تحميل الجلسات...</p>}
      {status === "error" && <Banner tone="err">{error}</Banner>}
      {status === "ready" && data.results.length === 0 && <Empty title="لا توجد جلسات" text="أضف مواعيد أسبوعية لمجموعاتك ثم ولّد الجلسات منها، أو أنشئ جلسة إضافية." />}
      <div className="cal">
        {groupByDay(listOf(data)).map((day) => (
          <section key={day.key} className={"cal-day" + (day.isToday ? " is-today" : "")}>
            <header className="cal-day-head">
              <div className="cal-date">
                <span className="cal-dnum">{day.date.getDate()}</span>
                <span className="cal-dname">{day.name}</span>
              </div>
              <div className="cal-day-main">
                <h3>{day.label}</h3>
                <span className="cal-hint">{day.hint} · {day.sessions.length} جلسة</span>
              </div>
            </header>

            <div className="cal-sessions">
              {day.sessions.map((s) => (
                <article key={s.id} className={"cal-session s-" + s.status}>
                  <div className="cal-time">{timeLabel(s.scheduled_at)}</div>
                  <div className="cal-session-main">
                    <strong>{s.group?.name || s.group_name}</strong>
                    <span className={"chip-s " + TONE[s.status]}>{STATUS[s.status]}</span>
                    {s.reopened_count ? <span className="stat-sub">أُعيد فتحها {s.reopened_count} مرة</span> : null}
                  </div>
                  <div className="row-actions">
                    {s.status === "planned" && <>
                      <button className="mini-btn" disabled={busyId === s.id} onClick={() => act(s.id, schedulingApi.sessions.open)}>فتح الجلسة</button>
                      <button className="mini-btn" onClick={() => setModal({ reschedule: s })}>تعديل الموعد</button></>}
                    {s.status === "open" && <>
                      <Link className="mini-btn" to={`/app/attendance?session=${s.id}`}>الحضور والتسميع</Link>
                      <button className="mini-btn" disabled={busyId === s.id} onClick={() => act(s.id, schedulingApi.sessions.close, "تم إغلاق الجلسة.")}>إغلاق</button></>}
                    {s.status === "closed" && <button className="mini-btn" disabled={busyId === s.id} onClick={() => setModal({ reopen: s })}>إعادة فتح للتصحيح</button>}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
      {(data.previous || data.next) && (
        <div className="dash-pager">
          <button disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>السابق</button><span>صفحة {page}</span>
          <button disabled={!data.next} onClick={() => setPage((p) => p + 1)}>التالي</button>
        </div>
      )}
      {modal === "add" && <AddSessionModal groups={groups} onClose={() => setModal(null)} onCreated={() => { setModal(null); reload(); }} />}
      {modal === "generate" && <GenerateModal groups={groups} onClose={() => setModal(null)} onDone={(n) => { setModal(null); setNotice({ tone: "info", text: n ? `تم إنشاء ${n} جلسة مخططة.` : "لا توجد جلسات جديدة لإنشائها." }); reload(); }} />}
      {modal?.reschedule && <RescheduleModal session={modal.reschedule} onClose={() => setModal(null)} onDone={() => { setModal(null); reload(); }} />}
      {modal?.reopen && (
        <Confirm title="إعادة فتح الجلسة؟" confirmLabel="إعادة الفتح"
          text="ستُفتح نفس الجلسة لتصحيح الحضور أو التسميع. الإشعارات التي أُرسلت سابقًا لا تُسحب، وقد يصدر إشعار جديد إذا صحّحت إلى «غائب» أو «لم يذاكر»."
          onClose={() => setModal(null)} onConfirm={async () => { await act(modal.reopen.id, schedulingApi.sessions.reopen, "أُعيد فتح الجلسة."); setModal(null); }} />
      )}
    </>
  );
}
