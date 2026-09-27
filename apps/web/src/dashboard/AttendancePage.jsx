import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CalendarClock, LockOpen } from "lucide-react";
import { Btn, Banner } from "../auth/ui.jsx";
import { sessionsApi, attendanceApi } from "../lib/schedulingApi.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import { useGroups } from "./useGroups.js";
import ComingSoon from "./ComingSoon.jsx";

const STATUS_LABEL = { planned: "مخطط لها", open: "مفتوحة", closed: "مغلقة" };

function fmt(iso) {
  return new Date(iso).toLocaleString("ar-EG", { dateStyle: "medium", timeStyle: "short" });
}

function SessionPicker({ onPick }) {
  const { grades } = useGrades();
  const { groups, status, error } = useGroups();
  const [groupId, setGroupId] = useState(null);
  const [sessions, setSessions] = useState([]);

  useEffect(() => { if (groups.length && groupId === null) setGroupId(groups[0].id); }, [groups, groupId]);
  useEffect(() => {
    if (!groupId) return;
    sessionsApi.list({ group_id: groupId }).then((data) => setSessions((data.results || data).filter((s) => s.status !== "planned")));
  }, [groupId]);

  const gradeName = (id) => grades.find((g) => g.id === id)?.name || "";

  if (status === "loading") return <p className="field-msg">جاري تحميل البيانات...</p>;
  if (status === "error") return <Banner tone="err">{error}</Banner>;
  if (groups.length === 0) return <ComingSoon title="لا توجد مجموعات بعد" text="أنشئ مجموعة وجلسة أولًا من صفحة «الجلسات»." />;

  return (
    <div className="dash-filters">
      <select className="inp" value={groupId || ""} onChange={(e) => setGroupId(Number(e.target.value))}>
        {groups.map((g) => <option key={g.id} value={g.id}>{gradeName(g.grade_id)} — {g.name}</option>)}
      </select>
      <select className="inp" onChange={(e) => e.target.value && onPick(Number(e.target.value))} defaultValue="">
        <option value="" disabled>اختر جلسة…</option>
        {sessions.map((s) => (
          <option key={s.id} value={s.id}>{fmt(s.scheduled_at)} — {STATUS_LABEL[s.status]}</option>
        ))}
      </select>
      {sessions.length === 0 && groupId && <p className="field-msg">لا توجد جلسات مفتوحة أو مغلقة لهذه المجموعة بعد.</p>}
    </div>
  );
}

export default function AttendancePage() {
  const [params, setParams] = useSearchParams();
  const sessionId = params.get("session");

  const [session, setSession] = useState(null);
  const [records, setRecords] = useState([]);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);
  const [openingErr, setOpeningErr] = useState(null);

  const load = () => {
    if (!sessionId) return;
    setStatus("loading");
    Promise.all([sessionsApi.get(sessionId), attendanceApi.list({ session_id: sessionId })])
      .then(([s, a]) => { setSession(s); setRecords(a.results || a); setStatus("ready"); })
      .catch((e) => { setError(e instanceof ApiError ? e.message : "تعذّر تحميل بيانات الحضور."); setStatus("error"); });
  };

  useEffect(load, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const openSession = async () => {
    setOpeningErr(null);
    try {
      const updated = await sessionsApi.open(sessionId);
      setSession(updated);
      load();
    } catch (e) {
      setOpeningErr(e instanceof ApiError ? e.message : "تعذّر فتح الجلسة.");
    }
  };

  const toggle = async (record) => {
    const next = record.status === "present" ? "absent" : "present";
    const updated = await attendanceApi.setStatus(record.id, next).catch(() => null);
    if (updated) setRecords((list) => list.map((r) => (r.id === updated.id ? updated : r)));
  };

  if (!sessionId) {
    return (
      <>
        <div className="dash-section-head"><h2>الحضور</h2></div>
        <SessionPicker onPick={(id) => setParams({ session: String(id) })} />
      </>
    );
  }

  return (
    <>
      <div className="dash-section-head"><h2>الحضور</h2></div>

      {status === "loading" && <p className="field-msg">جاري تحميل البيانات...</p>}
      {status === "error" && <Banner tone="err">{error}</Banner>}

      {status === "ready" && session && (
        <>
          <div className="dash-card" style={{ marginBottom: 18 }}>
            <div className="k"><CalendarClock size={14} /> {fmt(session.scheduled_at)} — {session.group.name}</div>
            <div className="v" style={{ fontSize: "1rem" }}>{STATUS_LABEL[session.status]}</div>
          </div>

          {session.status === "planned" && (
            <>
              {openingErr && <Banner tone="err">{openingErr}</Banner>}
              <ComingSoon title="لم تُفتح هذه الجلسة بعد" text="افتح الجلسة أولًا لبدء تسجيل حضور الطلاب.">
              </ComingSoon>
              <div style={{ display: "flex", justifyContent: "center", marginTop: 16 }}>
                <Btn onClick={openSession}><LockOpen size={16} /> فتح الجلسة</Btn>
              </div>
            </>
          )}

          {session.status !== "planned" && records.length === 0 && (
            <ComingSoon title="لا يوجد طلاب في هذه المجموعة" text="أضف طلابًا إلى هذه المجموعة من صفحة «الطلاب» أولًا." />
          )}

          {session.status !== "planned" && records.length > 0 && (
            <div className="dash-table-wrap">
              <table className="dash-table">
                <thead><tr><th>الطالب</th><th>الحالة</th></tr></thead>
                <tbody>
                  {records.map((r) => (
                    <tr key={r.id}>
                      <td>{r.student.name}</td>
                      <td>
                        <button className={"dash-pill" + (r.status === "present" ? " on" : "")} onClick={() => toggle(r)}>
                          {r.status === "present" ? "حاضر" : "غائب"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}
