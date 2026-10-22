import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarPlus, Wand2 } from "lucide-react";
import { Field, Btn, Banner, Modal } from "../auth/ui.jsx";
import { schedulingApi } from "../lib/dashboardApi.js";
import { ApiError } from "../lib/api.js";
import { useGroups } from "./useGroups.js";
import { useGrades } from "./useGrades.js";
import DateTimePicker from "../components/DateTimePicker.jsx";
import TimePicker from "../components/TimePicker.jsx";
import { groupByDay, timeLabel } from "../lib/dates.js";
import { Confirm, Empty, PageHeader, fmtDateTime } from "./common.jsx";

const STATUS = { planned: "مخططة", open: "مفتوحة", closed: "مغلقة" };
const TONE = { planned: "", open: "good", closed: "warn" };
const listOf = (d) => (Array.isArray(d) ? d : d?.results || []);
const toIso = (local) => new Date(local).toISOString();
const toLocalInput = (iso) => {
  const d = new Date(iso);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};

const pad2 = (n) => String(n).padStart(2, "0");
// "YYYY-MM-DDTHH:MM" (local) → the clock part "HH:MM" one hour later (same day, capped at 23:55).
const hourLater = (local) => {
  const h = Number(local.slice(11, 13)) + 1;
  return h > 23 ? "23:55" : `${pad2(h)}:${local.slice(14, 16)}`;
};
// The end time-of-day picked next to a start date-time → an ISO instant on the same local day.
const endIso = (startLocal, hhmm) => new Date(`${startLocal.slice(0, 10)}T${hhmm}`).toISOString();
const endsAfterStart = (startLocal, hhmm) =>
  new Date(`${startLocal.slice(0, 10)}T${hhmm}`) > new Date(startLocal);

function AddSessionModal({ grades, groups, onClose, onCreated }) {
  // A session belongs to ONE group, so "a grade" means one session per group
  // of that grade. The teacher picks the grade, then which of its groups.
  const [gradeId, setGradeId] = useState(grades[0]?.id || "");
  const [picked, setPicked] = useState([]);
  const [when, setWhen] = useState(toLocalInput(new Date().toISOString()));
  const [until, setUntil] = useState(hourLater(toLocalInput(new Date().toISOString())));
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);

  const ofGrade = groups.filter((g) => String(g.grade_id) === String(gradeId));
  const allPicked = ofGrade.length > 0 && ofGrade.every((g) => picked.includes(g.id));
  const toggle = (id) =>
    setPicked((l) => (l.includes(id) ? l.filter((x) => x !== id) : [...l, id]));
  const toggleAll = () => setPicked(allPicked ? [] : ofGrade.map((g) => g.id));
  const changeGrade = (id) => {
    setGradeId(id);
    setPicked([]);
  };

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    if (!picked.length) {
      setErr("اختر مجموعة واحدة على الأقل.");
      return;
    }
    if (!endsAfterStart(when, until)) {
      setErr("وقت الانتهاء يجب أن يكون بعد وقت البداية في نفس اليوم.");
      return;
    }
    setSaving(true);
    try {
      onCreated(
        await schedulingApi.sessions.bulk({
          grade_id: Number(gradeId),
          group_ids: picked,
          scheduled_at: toIso(when),
          ends_at: endIso(when, until),
        })
      );
    } catch (e2) {
      setErr(
        e2 instanceof ApiError
          ? e2.fields
            ? Object.values(e2.fields).flat().join(" ")
            : e2.message
          : "تعذّر إنشاء الجلسات."
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      size="md"
      title="جلسة إضافية (تعويض أو خارج الموعد)"
      text="اختر الصف ثم مجموعة أو أكثر (أو كل مجموعات الصف) وحدّد اليوم والوقت."
      onClose={onClose}
    >
      <form onSubmit={submit} className="dash-form" noValidate>
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="الصف" required>
          <select className="inp" value={gradeId} onChange={(e) => changeGrade(e.target.value)}>
            {grades.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="التاريخ ووقت البداية" required>
          <DateTimePicker value={when} onChange={setWhen} />
        </Field>
        <Field
          label="وقت الانتهاء"
          required
          hint="تُغلق الجلسة تلقائيًا عند هذا الوقت، ويُسجَّل غائبًا كل من لم يُسجَّل حضوره."
        >
          <TimePicker value={until} onChange={setUntil} required />
        </Field>
        <Field className="form-wide" label="المجموعات" required>
          {ofGrade.length === 0 ? (
            <p className="field-msg">لا توجد مجموعات في هذا الصف.</p>
          ) : (
            <div className="pick-chips" role="group" aria-label="المجموعات">
              <button
                type="button"
                className={"pick-chip pick-all" + (allPicked ? " is-sel" : "")}
                aria-pressed={allPicked}
                onClick={toggleAll}
              >
                كل مجموعات الصف ({ofGrade.length})
              </button>
              {ofGrade.map((g) => (
                <button
                  key={g.id}
                  type="button"
                  className={"pick-chip" + (picked.includes(g.id) ? " is-sel" : "")}
                  aria-pressed={picked.includes(g.id)}
                  onClick={() => toggle(g.id)}
                >
                  {g.name}
                </button>
              ))}
            </div>
          )}
        </Field>
        <p className="stat-sub form-wide">
          {picked.length
            ? `سيتم إنشاء ${picked.length} جلسة (جلسة لكل مجموعة).`
            : "لم تختر أي مجموعة بعد."}{" "}
          لا تتكرر جلسة موجودة لنفس المجموعة في نفس الموعد.
        </p>
        <Btn type="submit" loading={saving} loadingText="جارٍ الإنشاء…" disabled={!picked.length}>
          {picked.length > 1 ? `إنشاء ${picked.length} جلسات` : "إنشاء الجلسة"}
        </Btn>
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
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      const r = await schedulingApi.sessions.generate({
        weeks,
        ...(groupId ? { group_id: Number(groupId) } : {}),
      });
      onDone(r.created);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر توليد الجلسات.");
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      size="md"
      title="توليد جلسات من المواعيد الأسبوعية"
      text="تُنشأ جلسات «مخططة» للأسابيع القادمة. لا تتكرر الجلسات الموجودة، ويمكنك إعادة التوليد بأمان."
      onClose={onClose}
    >
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="عدد الأسابيع (1 إلى 8)">
          <input
            className="inp"
            type="number"
            min="1"
            max="8"
            value={weeks}
            onChange={(e) => setWeeks(Number(e.target.value))}
          />
        </Field>
        <Field label="المجموعة">
          <select className="inp" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
            <option value="">كل المجموعات</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </Field>
        <Btn type="submit" loading={saving} loadingText="جارٍ التوليد…">
          توليد الجلسات
        </Btn>
      </form>
    </Modal>
  );
}

function RescheduleModal({ session, onClose, onDone }) {
  const [when, setWhen] = useState(toLocalInput(session.scheduled_at));
  const [until, setUntil] = useState(
    session.ends_at
      ? toLocalInput(session.ends_at).slice(11, 16)
      : hourLater(toLocalInput(session.scheduled_at))
  );
  const [err, setErr] = useState(null);
  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    if (!endsAfterStart(when, until)) {
      setErr("وقت الانتهاء يجب أن يكون بعد وقت البداية في نفس اليوم.");
      return;
    }
    try {
      await schedulingApi.sessions.reschedule(session.id, toIso(when), endIso(when, until));
      onDone();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر التعديل.");
    }
  };
  return (
    <Modal title="تعديل موعد الجلسة" onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="التاريخ ووقت البداية" required>
          <DateTimePicker value={when} onChange={setWhen} />
        </Field>
        <Field label="وقت الانتهاء" required>
          <TimePicker value={until} onChange={setUntil} required />
        </Field>
        <Btn type="submit">حفظ</Btn>
      </form>
    </Modal>
  );
}

export default function SessionsPage() {
  const { groups, status: groupsStatus } = useGroups();
  const { grades } = useGrades();
  const [gradeFilter, setGradeFilter] = useState("");
  const [groupFilter, setGroupFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [data, setData] = useState({ results: [], next: null, previous: null });
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [modal, setModal] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    setPage(1);
  }, [gradeFilter, groupFilter, statusFilter]);
  const filterGroups = gradeFilter
    ? groups.filter((g) => String(g.grade_id) === String(gradeFilter))
    : groups;
  const gradeName = (id) => grades.find((g) => g.id === id)?.name;
  const reload = () => {
    schedulingApi.sessions
      .list({ grade_id: gradeFilter, group_id: groupFilter, status: statusFilter, page })
      .then((d) => {
        setData(Array.isArray(d) ? { results: d } : d);
        setStatus("ready");
      })
      .catch((e) => {
        setError(e instanceof ApiError ? e.message : "تعذّر تحميل الجلسات.");
        setStatus("error");
      });
  };
  useEffect(reload, [gradeFilter, groupFilter, statusFilter, page]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (id, fn, okText) => {
    setBusyId(id);
    setNotice(null);
    try {
      await fn(id);
      if (okText) setNotice({ tone: "info", text: okText });
      reload();
    } catch (e) {
      setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر تنفيذ الإجراء." });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <PageHeader infoKey="sessions" title="الجلسات">
        <Btn variant="ghost" onClick={() => setModal("generate")} disabled={groups.length === 0}>
          <Wand2 size={16} /> توليد من المواعيد
        </Btn>
        <Btn onClick={() => setModal("add")} disabled={groups.length === 0 || grades.length === 0}>
          <CalendarPlus size={16} /> جلسة إضافية
        </Btn>
      </PageHeader>
      {groupsStatus === "ready" && groups.length === 0 && (
        <Banner tone="info">أنشئ مجموعة أولًا من صفحة «المجموعات».</Banner>
      )}
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      <div className="dash-filters">
        <select
          className="inp"
          aria-label="الصف"
          value={gradeFilter}
          onChange={(e) => {
            setGradeFilter(e.target.value);
            setGroupFilter("");
          }}
        >
          <option value="">كل الصفوف</option>
          {grades.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <select
          className="inp"
          aria-label="المجموعة"
          value={groupFilter}
          onChange={(e) => setGroupFilter(e.target.value)}
        >
          <option value="">كل المجموعات</option>
          {filterGroups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <select
          className="inp"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">كل الحالات</option>
          {Object.entries(STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </div>
      {status === "loading" && <p className="field-msg">جاري تحميل الجلسات...</p>}
      {status === "error" && <Banner tone="err">{error}</Banner>}
      {status === "ready" && data.results.length === 0 && (
        <Empty
          title="لا توجد جلسات"
          text="أضف مواعيد أسبوعية لمجموعاتك ثم ولّد الجلسات منها، أو أنشئ جلسة إضافية."
        />
      )}
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
                <span className="cal-hint">
                  {day.hint} · {day.sessions.length} جلسة
                </span>
              </div>
            </header>

            <div className="cal-sessions">
              {day.sessions.map((s) => (
                <article key={s.id} className={"cal-session s-" + s.status}>
                  <div className="cal-time">
                    {timeLabel(s.scheduled_at)}
                    {s.ends_at ? <span className="stat-sub"> – {timeLabel(s.ends_at)}</span> : null}
                  </div>
                  <div className="cal-session-main">
                    <strong>{s.group?.name || s.group_name}</strong>
                    {gradeName(s.group?.grade_id) && (
                      <span className="stat-sub">{gradeName(s.group.grade_id)}</span>
                    )}
                    <span className={"chip-s " + TONE[s.status]}>{STATUS[s.status]}</span>
                    {s.reopened_count ? (
                      <span className="stat-sub">أُعيد فتحها {s.reopened_count} مرة</span>
                    ) : null}
                    {s.status === "open" && s.auto_close_at ? (
                      <span className="stat-sub">تُغلق تلقائيًا {timeLabel(s.auto_close_at)}</span>
                    ) : null}
                  </div>
                  <div className="row-actions">
                    {s.status === "planned" && (
                      <>
                        <button
                          className="mini-btn"
                          disabled={busyId === s.id}
                          onClick={() => act(s.id, schedulingApi.sessions.open)}
                        >
                          فتح الجلسة
                        </button>
                        <button className="mini-btn" onClick={() => setModal({ reschedule: s })}>
                          تعديل الموعد
                        </button>
                      </>
                    )}
                    {s.status === "open" && (
                      <>
                        <Link className="mini-btn" to={`/app/attendance?session=${s.id}`}>
                          الحضور والتسميع
                        </Link>
                        <button
                          className="mini-btn"
                          disabled={busyId === s.id}
                          onClick={() =>
                            act(s.id, schedulingApi.sessions.close, "تم إغلاق الجلسة.")
                          }
                        >
                          إغلاق
                        </button>
                      </>
                    )}
                    {s.status === "closed" && (
                      <button
                        className="mini-btn"
                        disabled={busyId === s.id}
                        onClick={() => setModal({ reopen: s })}
                      >
                        إعادة فتح للتصحيح
                      </button>
                    )}
                    <button
                      className="mini-btn danger"
                      disabled={busyId === s.id}
                      onClick={() => setModal({ remove: s })}
                    >
                      حذف
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
      {(data.previous || data.next) && (
        <div className="dash-pager">
          <button disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>
            السابق
          </button>
          <span>صفحة {page}</span>
          <button disabled={!data.next} onClick={() => setPage((p) => p + 1)}>
            التالي
          </button>
        </div>
      )}
      {modal === "add" && (
        <AddSessionModal
          grades={grades}
          groups={groups}
          onClose={() => setModal(null)}
          onCreated={(r) => {
            setModal(null);
            setNotice({
              tone: "info",
              text: r.created
                ? `تم إنشاء ${r.created} جلسة.${r.skipped?.length ? ` وتم تخطي ${r.skipped.length} لأن لها جلسة في نفس الموعد.` : ""}`
                : "كل المجموعات المختارة لديها جلسة في هذا الموعد بالفعل.",
            });
            reload();
          }}
        />
      )}
      {modal === "generate" && (
        <GenerateModal
          groups={groups}
          onClose={() => setModal(null)}
          onDone={(n) => {
            setModal(null);
            setNotice({
              tone: "info",
              text: n ? `تم إنشاء ${n} جلسة مخططة.` : "لا توجد جلسات جديدة لإنشائها.",
            });
            reload();
          }}
        />
      )}
      {modal?.reschedule && (
        <RescheduleModal
          session={modal.reschedule}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            reload();
          }}
        />
      )}
      {modal?.remove && (
        <Confirm
          danger
          title="حذف الجلسة؟"
          confirmLabel="حذف الجلسة"
          text={`ستُحذف جلسة ${modal.remove.group?.name || ""} المقررة ${fmtDateTime(modal.remove.scheduled_at)} نهائيًا. إن كانت تحمل تسجيلات حضور أو تسميع فلن تُحذف حتى لا تضيع البيانات.`}
          onClose={() => setModal(null)}
          onConfirm={async () => {
            await act(modal.remove.id, schedulingApi.sessions.remove, "تم حذف الجلسة.");
            setModal(null);
          }}
        />
      )}
      {modal?.reopen && (
        <Confirm
          title="إعادة فتح الجلسة؟"
          confirmLabel="إعادة الفتح"
          text="ستُفتح نفس الجلسة لتصحيح الحضور أو التسميع. الإشعارات التي أُرسلت سابقًا لا تُسحب، وقد يصدر إشعار جديد إذا صحّحت إلى «غائب» أو «لم يذاكر»."
          onClose={() => setModal(null)}
          onConfirm={async () => {
            await act(modal.reopen.id, schedulingApi.sessions.reopen, "أُعيد فتح الجلسة.");
            setModal(null);
          }}
        />
      )}
    </>
  );
}
