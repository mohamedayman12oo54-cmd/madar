import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Btn, Banner } from "../auth/ui.jsx";
import { schedulingApi } from "../lib/dashboardApi.js";
import { ApiError } from "../lib/api.js";
import { Empty, PageHeader, fmtDateTime } from "./common.jsx";
import GuestSection from "./GuestSection.jsx";

const listOf = (d) => (Array.isArray(d) ? d : d?.results || []);
const LABEL = { present: "حاضر", absent: "غائب", studied: "ذاكر", not_studied: "لم يذاكر" };
const TONE = { present: "good", studied: "good", absent: "bad", not_studied: "bad" };

/** Fast Session. Each tap is ONE small write sent immediately; the screen
 *  advances without waiting for the server (so a slow network never stalls the
 *  class) and any tap that failed stays visible, with a retry, until it saves. */
export default function AttendancePage() {
  const [params, setParams] = useSearchParams();
  const sessionId = params.get("session") ? Number(params.get("session")) : null;
  const [sessions, setSessions] = useState([]);
  const [roster, setRoster] = useState(null); // { session, students, counts }
  const [mode, setMode] = useState("attendance"); // attendance | recitation
  const [index, setIndex] = useState(0);
  const [failed, setFailed] = useState({}); // `${kind}:${enrollmentId}` -> status that failed to save
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(0);

  useEffect(() => {
    schedulingApi.sessions
      .list({ status: "open" })
      .then((d) => setSessions(listOf(d)))
      .catch(() => {});
  }, [roster?.session?.status]);

  const load = useCallback(async (id) => {
    setError(null);
    try {
      setRoster(await schedulingApi.sessions.roster(id));
      setIndex(0);
      setFailed({});
    } catch (e) {
      setRoster(null);
      setError(e instanceof ApiError ? e.message : "تعذّر تحميل الجلسة.");
    }
  }, []);
  useEffect(() => {
    if (sessionId) load(sessionId);
    else setRoster(null);
  }, [sessionId, load]);

  const students = useMemo(() => roster?.students || [], [roster]);
  const current = students[index];
  const isOpen = roster?.session.status === "open";
  const field = mode === "attendance" ? "attendance" : "recitation";

  const counts = useMemo(() => {
    const c = { present: 0, absent: 0, studied: 0, not_studied: 0 };
    students.forEach((s) => {
      if (s.attendance) c[s.attendance] += 1;
      if (s.recitation) c[s.recitation] += 1;
    });
    return c;
  }, [students]);

  const save = useCallback(
    async (enrollmentId, status, kind) => {
      inFlight.current += 1;
      const key = `${kind}:${enrollmentId}`;
      try {
        await (kind === "attendance" ? schedulingApi.markAttendance : schedulingApi.markRecitation)(
          sessionId,
          enrollmentId,
          status
        );
        setFailed((f) => {
          const n = { ...f };
          delete n[key];
          return n;
        });
      } catch (e) {
        setFailed((f) => ({ ...f, [key]: status }));
        if (e instanceof ApiError && e.status === 400) setError(e.message);
      } finally {
        inFlight.current -= 1;
      }
    },
    [sessionId]
  );

  const mark = (status) => {
    if (!current || !isOpen) return;
    setRoster((r) => ({
      ...r,
      students: r.students.map((s) =>
        s.enrollment_id === current.enrollment_id ? { ...s, [field]: status } : s
      ),
    }));
    save(current.enrollment_id, status, field);
    setIndex((i) => Math.min(i + 1, students.length)); // advance at once — never wait on the network
  };
  const skip = () => setIndex((i) => Math.min(i + 1, students.length)); // records nothing

  // Guests change on the server (carried marks, targets): refresh only that block, keep the student's place.
  const refreshGuests = useCallback(async () => {
    try {
      const fresh = await schedulingApi.sessions.roster(sessionId);
      setRoster((r) => (r ? { ...r, guests: fresh.guests } : r));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "تعذّر تحديث الضيوف.");
    }
  }, [sessionId]);

  const retry = (s, kind) => save(s.enrollment_id, failed[`${kind}:${s.enrollment_id}`], kind);

  const sessionAction = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      await fn(sessionId);
      await load(sessionId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "تعذّر تنفيذ الإجراء.");
    } finally {
      setBusy(false);
    }
  };

  if (!sessionId) {
    return (
      <>
        <PageHeader infoKey="attendance" title="الحضور والتسميع" />
        {sessions.length === 0 ? (
          <Empty
            title="لا توجد جلسة مفتوحة"
            text="افتح جلسة من صفحة «الجلسات» أولًا ثم عد إلى هنا."
          />
        ) : (
          <>
            <p className="field-msg">اختر الجلسة المفتوحة:</p>
            <div className="list-rows">
              {sessions.map((s) => (
                <button
                  key={s.id}
                  className="list-row dash-card-btn"
                  onClick={() => setParams({ session: s.id })}
                >
                  <strong>{s.group.name}</strong>
                  <span className="stat-sub">{fmtDateTime(s.scheduled_at)}</span>
                </button>
              ))}
            </div>
          </>
        )}
        {error && <Banner tone="err">{error}</Banner>}
      </>
    );
  }

  const done = index >= students.length && students.length > 0;
  const failedKeys = Object.keys(failed);

  return (
    <>
      <PageHeader
        infoKey="attendance"
        title={roster ? `${roster.session.group.name}` : "الحضور والتسميع"}
      >
        <button className="mini-btn" onClick={() => setParams({})}>
          تغيير الجلسة
        </button>
        {roster?.session.status === "planned" && (
          <Btn loading={busy} onClick={() => sessionAction(schedulingApi.sessions.open)}>
            فتح الجلسة
          </Btn>
        )}
        {roster?.session.status === "open" && (
          <Btn
            variant="ghost"
            loading={busy}
            onClick={() => sessionAction(schedulingApi.sessions.close)}
          >
            إغلاق الجلسة
          </Btn>
        )}
        {roster?.session.status === "closed" && (
          <Btn
            variant="ghost"
            loading={busy}
            onClick={() => sessionAction(schedulingApi.sessions.reopen)}
          >
            إعادة فتح للتصحيح
          </Btn>
        )}
      </PageHeader>
      {error && <Banner tone="err">{error}</Banner>}
      {failedKeys.length > 0 && (
        <Banner tone="err">
          تعذّر حفظ {failedKeys.length} تسجيل — تحقق من الاتصال ثم اضغط «إعادة المحاولة» بجانب الاسم
          أدناه.
        </Banner>
      )}
      {roster && !isOpen && (
        <Banner tone="info">
          {roster.session.status === "planned"
            ? "الجلسة لم تُفتح بعد؛ افتحها لتبدأ التسجيل."
            : "الجلسة مغلقة. أعد فتحها إن أردت تصحيح تسجيل."}
        </Banner>
      )}

      {roster && (
        <>
          <div className="dash-filters">
            <div className="seg" role="tablist">
              <button
                className={mode === "attendance" ? "active" : ""}
                onClick={() => {
                  setMode("attendance");
                  setIndex(0);
                }}
              >
                الحضور
              </button>
              <button
                className={mode === "recitation" ? "active" : ""}
                onClick={() => {
                  setMode("recitation");
                  setIndex(0);
                }}
              >
                التسميع
              </button>
            </div>
            <span className="chip-s good">حاضر {counts.present}</span>
            <span className="chip-s bad">غائب {counts.absent}</span>
            <span className="chip-s good">ذاكر {counts.studied}</span>
            <span className="chip-s bad">لم يذاكر {counts.not_studied}</span>
          </div>

          {students.length === 0 ? (
            <Empty
              title="لا يوجد طلاب نشطون في هذه المجموعة"
              text="أضف طلابًا لهذه المجموعة من صفحة «الطلاب»."
            />
          ) : (
            <div className="fs-card" aria-live="polite">
              {done ? (
                <>
                  <div className="fs-name">انتهيت من كل الطلاب ✅</div>
                  <div className="fs-sub">
                    يمكنك مراجعة القائمة أدناه وتصحيح أي تسجيل، ثم إغلاق الجلسة.
                  </div>
                </>
              ) : (
                <>
                  <div className="fs-sub">
                    الطالب {index + 1} من {students.length} —{" "}
                    {mode === "attendance" ? "الحضور" : "التسميع"}
                  </div>
                  <div className="fs-name">{current.name}</div>
                  <div className="fs-sub">
                    {current[field] ? `مسجّل: ${LABEL[current[field]]}` : "لم يُسجَّل بعد"}
                  </div>
                  <div className="fs-actions">
                    {mode === "attendance" ? (
                      <>
                        <button
                          className="tap good"
                          disabled={!isOpen}
                          onClick={() => mark("present")}
                        >
                          حاضر
                        </button>
                        <button
                          className="tap bad"
                          disabled={!isOpen}
                          onClick={() => mark("absent")}
                        >
                          غائب
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          className="tap good"
                          disabled={!isOpen}
                          onClick={() => mark("studied")}
                        >
                          ذاكر
                        </button>
                        <button
                          className="tap bad"
                          disabled={!isOpen}
                          onClick={() => mark("not_studied")}
                        >
                          لم يذاكر
                        </button>
                        <button className="tap skip" onClick={skip}>
                          تخطي
                        </button>
                      </>
                    )}
                  </div>
                  <div
                    className="row-actions"
                    style={{ justifyContent: "center", marginBlockStart: 16 }}
                  >
                    <button
                      className="mini-btn"
                      disabled={index === 0}
                      onClick={() => setIndex((i) => i - 1)}
                    >
                      <ChevronRight size={14} /> السابق
                    </button>
                    <button className="mini-btn" onClick={skip}>
                      التالي <ChevronLeft size={14} />
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          <div className="dash-section-head">
            <h2>القائمة</h2>
          </div>
          <div className="list-rows">
            {students.map((s, i) => (
              <div key={s.enrollment_id} className="list-row">
                <button className="dash-linkish" onClick={() => setIndex(i)}>
                  {s.name}
                </button>
                <div className="row-actions">
                  {s.carried_from && (
                    <span className="stat-sub">
                      مُرحَّل من زيارة {s.carried_from.group} —{" "}
                      {fmtDateTime(s.carried_from.scheduled_at)}
                    </span>
                  )}
                  {["attendance", "recitation"].map(
                    (kind) =>
                      s[kind] && (
                        <span key={kind} className={"chip-s " + TONE[s[kind]]}>
                          {LABEL[s[kind]]}
                        </span>
                      )
                  )}
                  {s.auto_absent && <span className="stat-sub">غياب تلقائي — يمكنك تغييره</span>}
                  {["attendance", "recitation"].map(
                    (kind) =>
                      failed[`${kind}:${s.enrollment_id}`] && (
                        <button
                          key={kind}
                          className="mini-btn danger"
                          onClick={() => retry(s, kind)}
                        >
                          لم يُحفظ — إعادة المحاولة
                        </button>
                      )
                  )}
                </div>
              </div>
            ))}
          </div>
          <GuestSection
            sessionId={sessionId}
            isOpen={isOpen}
            guests={roster.guests || []}
            onChanged={refreshGuests}
          />
        </>
      )}
    </>
  );
}
