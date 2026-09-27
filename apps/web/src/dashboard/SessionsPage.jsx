import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, CalendarClock, Lock, LockOpen, RotateCcw, ClipboardCheck } from "lucide-react";
import { Field, Btn, Banner, Modal } from "../auth/ui.jsx";
import { sessionsApi } from "../lib/schedulingApi.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import { useGroups } from "./useGroups.js";
import ComingSoon from "./ComingSoon.jsx";

const STATUS_LABEL = { planned: "مخطط لها", open: "مفتوحة", closed: "مغلقة" };

function fmt(iso) {
  return new Date(iso).toLocaleString("ar-EG", { dateStyle: "medium", timeStyle: "short" });
}

function PlanSessionModal({ groupId, onClose, onCreated }) {
  const [when, setWhen] = useState("");
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!when) { setErr("اختر موعد الجلسة."); return; }
    setSaving(true); setErr(null);
    try {
      const session = await sessionsApi.create({ group_id: groupId, scheduled_at: new Date(when).toISOString() });
      onCreated(session);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر إنشاء الجلسة.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="جلسة جديدة" onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="الموعد" required>
          <input className="inp" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} autoFocus />
        </Field>
        <Btn type="submit" loading={saving} loadingText="جارٍ الإنشاء…">إنشاء الجلسة</Btn>
      </form>
    </Modal>
  );
}

export default function SessionsPage() {
  const nav = useNavigate();
  const { grades } = useGrades();
  const { groups, status: groupsStatus, error: groupsError } = useGroups();
  const [groupId, setGroupId] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);
  const [showPlan, setShowPlan] = useState(false);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    if (groups.length && groupId === null) setGroupId(groups[0].id);
  }, [groups, groupId]);

  const load = (gid) => {
    if (!gid) { setSessions([]); return; }
    setStatus("loading");
    sessionsApi.list({ group_id: gid })
      .then((data) => { setSessions(data.results || data); setStatus("ready"); })
      .catch((e) => { setError(e instanceof ApiError ? e.message : "تعذّر تحميل الجلسات."); setStatus("error"); });
  };

  useEffect(() => { load(groupId); }, [groupId]); // eslint-disable-line react-hooks/exhaustive-deps

  const gradeName = (id) => grades.find((g) => g.id === id)?.name || "";

  const runAction = async (session, action) => {
    setBusyId(session.id);
    try {
      const updated = await sessionsApi[action](session.id);
      setSessions((list) => list.map((s) => (s.id === updated.id ? updated : s)));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "تعذّر تنفيذ الإجراء.");
    } finally {
      setBusyId(null);
    }
  };

  if (groupsStatus === "loading") return <p className="field-msg">جاري تحميل البيانات...</p>;
  if (groupsStatus === "error") return <Banner tone="err">{groupsError}</Banner>;

  if (groups.length === 0) {
    return <ComingSoon title="أضف مجموعة أولًا" text="الجلسات تنتمي إلى مجموعة — أنشئ مجموعة من صفحة «المجموعات» أولًا." />;
  }

  return (
    <>
      <div className="dash-section-head">
        <h2>الجلسات</h2>
        <Btn onClick={() => setShowPlan(true)} disabled={!groupId}><Plus size={16} /> جلسة جديدة</Btn>
      </div>

      <div className="dash-filters">
        <select className="inp" value={groupId || ""} onChange={(e) => setGroupId(Number(e.target.value))}>
          {groups.map((g) => <option key={g.id} value={g.id}>{gradeName(g.grade_id)} — {g.name}</option>)}
        </select>
      </div>

      {error && <Banner tone="err">{error}</Banner>}
      {status === "loading" && <p className="field-msg">جاري تحميل الجلسات...</p>}

      {status === "ready" && sessions.length === 0 && (
        <ComingSoon title="لا توجد جلسات بعد" text="أضف أول جلسة لهذه المجموعة." />
      )}

      {status === "ready" && sessions.length > 0 && (
        <div className="dash-cards" style={{ gridTemplateColumns: "1fr" }}>
          {sessions.map((s) => (
            <div key={s.id} className="dash-card dash-session-row">
              <div className="dash-session-info">
                <div className="k"><CalendarClock size={14} /> {fmt(s.scheduled_at)}</div>
                <span className={"dash-pill" + (s.status === "open" ? " on" : "")}>{STATUS_LABEL[s.status]}</span>
                {s.reopened_count > 0 && <span className="dash-tag">أُعيد فتحها {s.reopened_count} مرة</span>}
              </div>
              <div className="dash-session-actions">
                {s.status === "planned" && (
                  <Btn variant="secondary" loading={busyId === s.id} onClick={() => runAction(s, "open")}><LockOpen size={14} /> فتح الجلسة</Btn>
                )}
                {s.status === "open" && (
                  <>
                    <Btn variant="ghost" onClick={() => nav(`/app/attendance?session=${s.id}`)}><ClipboardCheck size={14} /> الحضور</Btn>
                    <Btn variant="secondary" loading={busyId === s.id} onClick={() => runAction(s, "close")}><Lock size={14} /> إغلاق</Btn>
                  </>
                )}
                {s.status === "closed" && (
                  <>
                    <Btn variant="ghost" onClick={() => nav(`/app/attendance?session=${s.id}`)}><ClipboardCheck size={14} /> الحضور</Btn>
                    <Btn variant="secondary" loading={busyId === s.id} onClick={() => runAction(s, "reopen")}><RotateCcw size={14} /> إعادة الفتح</Btn>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showPlan && (
        <PlanSessionModal groupId={groupId} onClose={() => setShowPlan(false)} onCreated={() => { setShowPlan(false); load(groupId); }} />
      )}
    </>
  );
}
