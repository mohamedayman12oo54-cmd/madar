import { useEffect, useState } from "react";
import { NotebookPen, Star, History } from "lucide-react";
import { Field, Btn, Banner, Modal } from "../auth/ui.jsx";
import { enrollmentsApi } from "../lib/academicsApi.js";
import { sessionsApi } from "../lib/schedulingApi.js";
import { notesApi, ratingsApi } from "../lib/evaluationApi.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import { useGroups } from "./useGroups.js";
import ComingSoon from "./ComingSoon.jsx";

function fmt(iso) {
  return new Date(iso).toLocaleDateString("ar-EG", { dateStyle: "medium" });
}

function SessionSelect({ groupId, value, onChange }) {
  const [sessions, setSessions] = useState([]);
  useEffect(() => {
    if (!groupId) return;
    sessionsApi.list({ group_id: groupId }).then((data) => setSessions((data.results || data).filter((s) => s.status !== "planned")));
  }, [groupId]);
  return (
    <Field label="ربط بجلسة (اختياري)">
      <select className="inp" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">بدون ربط بجلسة</option>
        {sessions.map((s) => <option key={s.id} value={s.id}>{fmt(s.scheduled_at)}</option>)}
      </select>
    </Field>
  );
}

function AddNoteModal({ enrollment, groupId, onClose, onSaved }) {
  const [body, setBody] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!body.trim()) { setErr("اكتب نص الملاحظة."); return; }
    setSaving(true); setErr(null);
    try {
      await notesApi.create({ enrollment_id: enrollment.id, session_id: sessionId || null, body: body.trim() });
      onSaved();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر حفظ الملاحظة.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={`ملاحظة جديدة — ${enrollment.student.name}`} onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="الملاحظة" required>
          <textarea className="inp" rows={4} value={body} onChange={(e) => setBody(e.target.value)} autoFocus />
        </Field>
        <SessionSelect groupId={groupId} value={sessionId} onChange={setSessionId} />
        <Btn type="submit" loading={saving} loadingText="جارٍ الحفظ…">حفظ الملاحظة</Btn>
      </form>
    </Modal>
  );
}

function AddRatingModal({ enrollment, groupId, onClose, onSaved }) {
  const [value, setValue] = useState(0);
  const [sessionId, setSessionId] = useState("");
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!value) { setErr("اختر تقييمًا من 1 إلى 5."); return; }
    setSaving(true); setErr(null);
    try {
      await ratingsApi.create({ enrollment_id: enrollment.id, session_id: sessionId || null, value });
      onSaved();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر حفظ التقييم.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={`تقييم جديد — ${enrollment.student.name}`} onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="التقييم" required>
          <div style={{ display: "flex", gap: 6 }}>
            {[1, 2, 3, 4, 5].map((n) => (
              <button type="button" key={n} onClick={() => setValue(n)} style={{ background: "none", border: 0, cursor: "pointer" }}>
                <Star size={26} fill={n <= value ? "#E3A63E" : "none"} color={n <= value ? "#E3A63E" : "var(--line-2)"} />
              </button>
            ))}
          </div>
        </Field>
        <SessionSelect groupId={groupId} value={sessionId} onChange={setSessionId} />
        <Btn type="submit" loading={saving} loadingText="جارٍ الحفظ…">حفظ التقييم</Btn>
      </form>
    </Modal>
  );
}

function HistoryModal({ enrollment, onClose }) {
  const [notes, setNotes] = useState(null);
  const [ratings, setRatings] = useState(null);

  useEffect(() => {
    notesApi.list({ enrollment_id: enrollment.id }).then((d) => setNotes(d.results || d)).catch(() => setNotes([]));
    ratingsApi.list({ enrollment_id: enrollment.id }).then((d) => setRatings(d.results || d)).catch(() => setRatings([]));
  }, [enrollment.id]);

  return (
    <Modal title={`سجل ${enrollment.student.name}`} onClose={onClose}>
      <div className="dash-form">
        <div>
          <strong style={{ fontSize: ".85rem", color: "var(--soft)" }}>التقييمات</strong>
          {ratings === null && <p className="field-msg">جاري التحميل...</p>}
          {ratings?.length === 0 && <p className="field-msg">لا يوجد تقييمات بعد.</p>}
          {ratings?.map((r) => (
            <div key={r.id} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
              <span>{"★".repeat(r.value)}{"☆".repeat(5 - r.value)}</span>
              <span className="field-msg" style={{ margin: 0 }}>{fmt(r.created_at)}</span>
            </div>
          ))}
        </div>
        <div>
          <strong style={{ fontSize: ".85rem", color: "var(--soft)" }}>الملاحظات</strong>
          {notes === null && <p className="field-msg">جاري التحميل...</p>}
          {notes?.length === 0 && <p className="field-msg">لا توجد ملاحظات بعد.</p>}
          {notes?.map((n) => (
            <div key={n.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
              <p style={{ margin: 0 }}>{n.body}</p>
              <span className="field-msg" style={{ margin: 0 }}>{fmt(n.created_at)}</span>
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
}

export default function EvaluationPage() {
  const { grades } = useGrades();
  const { groups, status: groupsStatus, error: groupsError } = useGroups();
  const [groupId, setGroupId] = useState(null);
  const [enrollments, setEnrollments] = useState([]);
  const [status, setStatus] = useState("idle");
  const [modal, setModal] = useState(null); // {type:"note"|"rating"|"history", enrollment}

  useEffect(() => { if (groups.length && groupId === null) setGroupId(groups[0].id); }, [groups, groupId]);

  useEffect(() => {
    if (!groupId) return;
    setStatus("loading");
    enrollmentsApi.list({ group_id: groupId })
      .then((data) => { setEnrollments(data.results || data); setStatus("ready"); })
      .catch(() => setStatus("error"));
  }, [groupId]);

  const gradeName = (id) => grades.find((g) => g.id === id)?.name || "";

  if (groupsStatus === "loading") return <p className="field-msg">جاري تحميل البيانات...</p>;
  if (groupsStatus === "error") return <Banner tone="err">{groupsError}</Banner>;
  if (groups.length === 0) return <ComingSoon title="أضف مجموعة أولًا" text="أنشئ مجموعة وأضف طلابًا إليها من صفحتَي «المجموعات» و«الطلاب»." />;

  return (
    <>
      <div className="dash-section-head"><h2>التقييم</h2></div>

      <div className="dash-filters">
        <select className="inp" value={groupId || ""} onChange={(e) => setGroupId(Number(e.target.value))}>
          {groups.map((g) => <option key={g.id} value={g.id}>{gradeName(g.grade_id)} — {g.name}</option>)}
        </select>
      </div>

      {status === "loading" && <p className="field-msg">جاري التحميل...</p>}
      {status === "error" && <Banner tone="err">حدث خطأ أثناء تحميل البيانات.</Banner>}

      {status === "ready" && enrollments.length === 0 && (
        <ComingSoon title="لا يوجد طلاب في هذه المجموعة" text="أضف طلابًا إلى هذه المجموعة من صفحة «الطلاب»." />
      )}

      {status === "ready" && enrollments.length > 0 && (
        <div className="dash-table-wrap">
          <table className="dash-table">
            <thead><tr><th>الطالب</th><th></th></tr></thead>
            <tbody>
              {enrollments.map((e) => (
                <tr key={e.id}>
                  <td>{e.student.name}</td>
                  <td style={{ display: "flex", gap: 8 }}>
                    <Btn variant="ghost" onClick={() => setModal({ type: "note", enrollment: e })}><NotebookPen size={14} /> ملاحظة</Btn>
                    <Btn variant="ghost" onClick={() => setModal({ type: "rating", enrollment: e })}><Star size={14} /> تقييم</Btn>
                    <Btn variant="ghost" onClick={() => setModal({ type: "history", enrollment: e })}><History size={14} /> السجل</Btn>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal?.type === "note" && (
        <AddNoteModal enrollment={modal.enrollment} groupId={groupId} onClose={() => setModal(null)} onSaved={() => setModal(null)} />
      )}
      {modal?.type === "rating" && (
        <AddRatingModal enrollment={modal.enrollment} groupId={groupId} onClose={() => setModal(null)} onSaved={() => setModal(null)} />
      )}
      {modal?.type === "history" && (
        <HistoryModal enrollment={modal.enrollment} onClose={() => setModal(null)} />
      )}
    </>
  );
}
