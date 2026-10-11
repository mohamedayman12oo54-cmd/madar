import { useEffect, useState } from "react";
import { Plus, UsersRound, Pencil, Trash2, Clock, CalendarDays } from "lucide-react";
import { Field, TextInput, Btn, Banner, Modal } from "../auth/ui.jsx";
import { gradesApi, groupsApi } from "../lib/academicsApi.js";
import { ApiError } from "../lib/api.js";
import { schedulingApi } from "../lib/dashboardApi.js";
import { fmtClock, scheduleSummary } from "../lib/dates.js";
import TimePicker from "../components/TimePicker.jsx";
import { useGrades } from "./useGrades.js";
import { Confirm, Empty, PageHeader, fmtMoney } from "./common.jsx";

function AddGradeModal({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [fee, setFee] = useState("");
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true); setErr(null);
    try {
      const grade = await gradesApi.create({ name: name.trim(), fee_amount: fee || "0" });
      onCreated(grade);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر إنشاء الصف.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="إضافة صف دراسي" onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="اسم الصف" required>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="مثال: الصف الأول الثانوي" autoFocus />
        </Field>
        <Field label="الرسوم الشهرية (جنيه)" hint="الصف هو من يملك الرسوم؛ المجموعات داخله تشترك في نفس القيمة. تغييرها لا يغيّر الأشهر المسجلة سابقًا.">
          <TextInput type="number" min="0" step="0.01" value={fee} onChange={(e) => setFee(e.target.value)} placeholder="0" />
        </Field>
        <Btn type="submit" loading={saving} loadingText="جارٍ الإنشاء…" disabled={!name.trim()}>إنشاء الصف</Btn>
      </form>
    </Modal>
  );
}

function AddGroupModal({ grade, onClose, onCreated }) {
  const [name, setName] = useState("");
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true); setErr(null);
    try {
      const group = await groupsApi.create({ name: name.trim(), grade_id: grade.id });
      onCreated(group);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر إنشاء المجموعة.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={`إضافة مجموعة إلى «${grade.name}»`} onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="اسم المجموعة" required>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="مثال: مجموعة السبت والثلاثاء" autoFocus />
        </Field>
        <Btn type="submit" loading={saving} loadingText="جارٍ الإنشاء…" disabled={!name.trim()}>إنشاء المجموعة</Btn>
      </form>
    </Modal>
  );
}

function RenameGroupModal({ group, onClose, onRenamed }) {
  const [name, setName] = useState(group.name);
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true); setErr(null);
    try {
      const updated = await groupsApi.update(group.id, { name: name.trim() });
      onRenamed(updated);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر حفظ التعديل.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="إعادة تسمية المجموعة" onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="اسم المجموعة" required>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </Field>
        <Btn type="submit" loading={saving} loadingText="جارٍ الحفظ…" disabled={!name.trim()}>حفظ</Btn>
      </form>
    </Modal>
  );
}

function EditGradeModal({ grade, onClose, onSaved }) {
  const [name, setName] = useState(grade.name);
  const [fee, setFee] = useState(String(grade.fee_amount ?? ""));
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true); setErr(null);
    try { onSaved(await gradesApi.update(grade.id, { name: name.trim(), fee_amount: fee || "0" })); }
    catch (e2) { setErr(e2 instanceof ApiError ? e2.message : "تعذّر حفظ التعديل."); }
    finally { setSaving(false); }
  };
  return (
    <Modal title="تعديل الصف الدراسي" onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="اسم الصف" required><TextInput value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
        <Field label="الرسوم الشهرية (جنيه)" hint="تغيير الرسوم لا يغيّر الأشهر المسجلة سابقًا في المدفوعات.">
          <TextInput type="number" min="0" step="0.01" value={fee} onChange={(e) => setFee(e.target.value)} />
        </Field>
        <Btn type="submit" loading={saving} loadingText="جارٍ الحفظ…" disabled={!name.trim()}>حفظ</Btn>
      </form>
    </Modal>
  );
}

const WEEKDAYS = [[5, "السبت"], [6, "الأحد"], [0, "الاثنين"], [1, "الثلاثاء"], [2, "الأربعاء"], [3, "الخميس"], [4, "الجمعة"]];

function SchedulesModal({ group, onClose }) {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("loading");
  const [weekday, setWeekday] = useState(5);
  const [time, setTime] = useState("18:00");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => schedulingApi.schedules.list({ group_id: group.id })
    .then((d) => { setItems(Array.isArray(d) ? d : d.results || []); setStatus("ready"); })
    .catch(() => setStatus("error"));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const add = async (e) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try { await schedulingApi.schedules.create({ group_id: group.id, weekday, start_time: time }); await load(); }
    catch (e2) { setErr(e2 instanceof ApiError ? (e2.fields ? Object.values(e2.fields).flat().join(" ") : e2.message) : "تعذّر إضافة الموعد."); }
    finally { setBusy(false); }
  };
  const remove = async (id) => { await schedulingApi.schedules.remove(id).catch(() => {}); load(); };

  return (
    <Modal size="md" title={`المواعيد الأسبوعية — ${group.name}`} text="الموعد الأسبوعي توقّع للحصة المعتادة؛ يمكنك توليد جلسات منه من صفحة «الجلسات»." onClose={onClose}>
      {status === "loading" && <p className="field-msg">جاري التحميل...</p>}
      {status === "error" && <Banner tone="err">تعذّر تحميل المواعيد.</Banner>}
      {status === "ready" && (items.length === 0 ? <p className="field-msg">لا توجد مواعيد بعد.</p> : (
        <div className="list-rows" style={{ marginBlockEnd: 14 }}>
          {items.map((s) => (
            <div key={s.id} className="list-row">
              <span><Clock size={14} /> {s.weekday_label} — <span>{fmtClock(s.start_time)}</span></span>
              <button className="mini-btn danger" onClick={() => remove(s.id)}><Trash2 size={13} /> حذف</button>
            </div>
          ))}
        </div>
      ))}
      <form onSubmit={add} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <div className="dash-filters" style={{ marginBlockEnd: 0 }}>
          <select className="inp" value={weekday} onChange={(e) => setWeekday(Number(e.target.value))}>
            {WEEKDAYS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <TimePicker value={time} onChange={setTime} required />
        </div>
        <Btn type="submit" loading={busy} loadingText="جارٍ الإضافة…">إضافة موعد</Btn>
      </form>
    </Modal>
  );
}

export default function GroupsPage() {
  const { grades, status: gradesStatus, error: gradesError, reload: reloadGrades } = useGrades();
  const [activeGradeId, setActiveGradeId] = useState(null);
  const [groups, setGroups] = useState([]);
  const [groupsStatus, setGroupsStatus] = useState("idle"); // idle | loading | ready | error
  const [groupsError, setGroupsError] = useState(null);
  const [modal, setModal] = useState(null);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    if (grades.length && activeGradeId === null) setActiveGradeId(grades[0].id);
    if (grades.length === 0) setActiveGradeId(null);
  }, [grades, activeGradeId]);

  const loadGroups = (gradeId) => {
    if (!gradeId) { setGroups([]); return; }
    setGroupsStatus("loading");
    groupsApi.list({ grade_id: gradeId })
      .then((data) => { setGroups(Array.isArray(data) ? data : data.results || []); setGroupsStatus("ready"); })
      .catch((e) => { setGroupsError(e instanceof ApiError ? e.message : "تعذّر تحميل المجموعات."); setGroupsStatus("error"); });
  };

  useEffect(() => { loadGroups(activeGradeId); }, [activeGradeId]); // eslint-disable-line react-hooks/exhaustive-deps

  const activeGrade = grades.find((g) => g.id === activeGradeId) || null;

  if (gradesStatus === "loading") return <><PageHeader infoKey="groups" title="المجموعات والمواعيد" /><p className="field-msg">جاري تحميل البيانات...</p></>;
  if (gradesStatus === "error") return <><PageHeader infoKey="groups" title="المجموعات والمواعيد" /><Banner tone="err">{gradesError}</Banner></>;

  if (grades.length === 0) {
    return (
      <>
        <PageHeader infoKey="groups" title="المجموعات والمواعيد" />
        <Empty title="أضف أول صف دراسي" text="المجموعات تنتمي إلى صف دراسي — ابدأ بإنشاء صف قبل إضافة مجموعاته." />
        <div style={{ display: "flex", justifyContent: "center", marginTop: 16 }}>
          <Btn onClick={() => setModal("grade")}><Plus size={16} /> إضافة صف دراسي</Btn>
        </div>
        {modal === "grade" && (
          <AddGradeModal onClose={() => setModal(null)} onCreated={() => { setModal(null); reloadGrades(); }} />
        )}
      </>
    );
  }

  return (
    <>
      <PageHeader infoKey="groups" title="المجموعات والمواعيد" />
      {notice && <Banner tone={notice.tone}>{notice.text} <button className="dash-linkish" onClick={() => setNotice(null)}>إخفاء</button></Banner>}
      <div className="dash-tabs">
        {grades.map((g) => (
          <button key={g.id} className={"dash-tab" + (g.id === activeGradeId ? " active" : "")} onClick={() => setActiveGradeId(g.id)}>
            {g.name}
          </button>
        ))}
        <button className="dash-tab dash-tab-add" onClick={() => setModal("grade")} aria-label="إضافة صف دراسي"><Plus size={15} /></button>
      </div>

      <div className="dash-section-head">
        <h2>مجموعات «{activeGrade?.name}» <span className="chip-s">{fmtMoney(activeGrade?.fee_amount ?? 0)} / شهر</span></h2>
        <div className="dash-head-actions">
          <button className="mini-btn" onClick={() => setModal({ editGrade: activeGrade })}><Pencil size={13} /> تعديل الصف</button>
          <button className="mini-btn danger" onClick={() => setModal({ deleteGrade: activeGrade })}><Trash2 size={13} /> حذف الصف</button>
          <Btn onClick={() => setModal("group")}><Plus size={16} /> مجموعة جديدة</Btn>
        </div>
      </div>

      {groupsStatus === "loading" && <p className="field-msg">جاري تحميل المجموعات...</p>}
      {groupsStatus === "error" && <Banner tone="err">{groupsError}</Banner>}
      {groupsStatus === "ready" && groups.length === 0 && (
        <Empty title="لا توجد مجموعات بعد" text={`أضف أول مجموعة داخل «${activeGrade?.name}» لتنظيم طلاب هذا الصف.`} />
      )}
      {groupsStatus === "ready" && groups.length > 0 && (
        <div className="dash-cards">
          {groups.map((g) => (
            <div key={g.id} className="dash-card">
              <div className="k"><UsersRound size={14} /> {g.name}</div>
              <div className="v">{g.student_count}</div>
              <div className="k">طالب نشط</div>
              <div className="group-days">
                {g.schedules?.length
                  ? <><CalendarDays size={13} /> {scheduleSummary(g.schedules)}</>
                  : <span className="stat-sub">لا توجد مواعيد أسبوعية بعد</span>}
              </div>
              <div className="row-actions" style={{ marginBlockStart: 12 }}>
                <button className="mini-btn" onClick={() => setModal({ schedules: g })}><Clock size={13} /> المواعيد</button>
                <button className="mini-btn" onClick={() => setModal({ rename: g })}><Pencil size={13} /> تسمية</button>
                <button className="mini-btn danger" onClick={() => setModal({ deleteGroup: g })}><Trash2 size={13} /></button>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal === "grade" && (
        <AddGradeModal onClose={() => setModal(null)} onCreated={(g) => { setModal(null); reloadGrades(); setActiveGradeId(g.id); }} />
      )}
      {modal === "group" && activeGrade && (
        <AddGroupModal grade={activeGrade} onClose={() => setModal(null)} onCreated={() => { setModal(null); loadGroups(activeGradeId); }} />
      )}
      {modal?.editGrade && (
        <EditGradeModal grade={modal.editGrade} onClose={() => setModal(null)} onSaved={() => { setModal(null); reloadGrades(); }} />
      )}
      {modal?.schedules && <SchedulesModal group={modal.schedules} onClose={() => setModal(null)} />}
      {modal?.deleteGrade && (
        <Confirm danger title="حذف الصف؟" confirmLabel="حذف الصف"
          text={`سيُحذف «${modal.deleteGrade.name}». لا يمكن حذف صف به مجموعات أو طلاب.`}
          onClose={() => setModal(null)}
          onConfirm={async () => {
            try { await gradesApi.remove(modal.deleteGrade.id); setActiveGradeId(null); reloadGrades(); setNotice({ tone: "info", text: "تم حذف الصف." }); }
            catch (e) { setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر حذف الصف." }); }
            setModal(null);
          }} />
      )}
      {modal?.deleteGroup && (
        <Confirm danger title="حذف المجموعة؟" confirmLabel="حذف المجموعة"
          text={`سيُحذف «${modal.deleteGroup.name}» ومواعيدها. لا يمكن حذف مجموعة بها طلاب أو جلسات.`}
          onClose={() => setModal(null)}
          onConfirm={async () => {
            try { await groupsApi.remove(modal.deleteGroup.id); loadGroups(activeGradeId); setNotice({ tone: "info", text: "تم حذف المجموعة." }); }
            catch (e) { setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر حذف المجموعة." }); }
            setModal(null);
          }} />
      )}
      {modal?.rename && (
        <RenameGroupModal group={modal.rename} onClose={() => setModal(null)} onRenamed={() => { setModal(null); loadGroups(activeGradeId); }} />
      )}
    </>
  );
}
