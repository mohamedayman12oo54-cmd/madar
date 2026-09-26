import { useEffect, useState } from "react";
import { Plus, UsersRound } from "lucide-react";
import { Field, TextInput, Btn, Banner, Modal } from "../auth/ui.jsx";
import { gradesApi, groupsApi } from "../lib/academicsApi.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import ComingSoon from "./ComingSoon.jsx";

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
        <Field label="الرسوم الدراسية (جنيه)" hint="يمكن تعديلها لاحقًا — الصف هو من يملك قيمة الرسوم.">
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

export default function GroupsPage() {
  const { grades, status: gradesStatus, error: gradesError, reload: reloadGrades } = useGrades();
  const [activeGradeId, setActiveGradeId] = useState(null);
  const [groups, setGroups] = useState([]);
  const [groupsStatus, setGroupsStatus] = useState("idle"); // idle | loading | ready | error
  const [groupsError, setGroupsError] = useState(null);
  const [modal, setModal] = useState(null); // "grade" | "group" | {rename: group}

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

  if (gradesStatus === "loading") return <p className="field-msg">جاري تحميل البيانات...</p>;
  if (gradesStatus === "error") return <Banner tone="err">{gradesError}</Banner>;

  if (grades.length === 0) {
    return (
      <>
        <ComingSoon title="أضف أول صف دراسي" text="المجموعات تنتمي إلى صف دراسي — ابدأ بإنشاء صف قبل إضافة مجموعاته." />
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
      <div className="dash-tabs">
        {grades.map((g) => (
          <button key={g.id} className={"dash-tab" + (g.id === activeGradeId ? " active" : "")} onClick={() => setActiveGradeId(g.id)}>
            {g.name}
          </button>
        ))}
        <button className="dash-tab dash-tab-add" onClick={() => setModal("grade")} aria-label="إضافة صف دراسي"><Plus size={15} /></button>
      </div>

      <div className="dash-section-head">
        <h2>مجموعات «{activeGrade?.name}»</h2>
        <Btn onClick={() => setModal("group")}><Plus size={16} /> مجموعة جديدة</Btn>
      </div>

      {groupsStatus === "loading" && <p className="field-msg">جاري تحميل المجموعات...</p>}
      {groupsStatus === "error" && <Banner tone="err">{groupsError}</Banner>}
      {groupsStatus === "ready" && groups.length === 0 && (
        <ComingSoon title="لا توجد مجموعات بعد" text={`أضف أول مجموعة داخل «${activeGrade?.name}» لتنظيم طلاب هذا الصف.`} />
      )}
      {groupsStatus === "ready" && groups.length > 0 && (
        <div className="dash-cards">
          {groups.map((g) => (
            <button key={g.id} className="dash-card dash-card-btn" onClick={() => setModal({ rename: g })}>
              <div className="k"><UsersRound size={14} /> {g.name}</div>
              <div className="v">{g.student_count}</div>
              <div className="k">طالب</div>
            </button>
          ))}
        </div>
      )}

      {modal === "grade" && (
        <AddGradeModal onClose={() => setModal(null)} onCreated={(g) => { setModal(null); reloadGrades(); setActiveGradeId(g.id); }} />
      )}
      {modal === "group" && activeGrade && (
        <AddGroupModal grade={activeGrade} onClose={() => setModal(null)} onCreated={() => { setModal(null); loadGroups(activeGradeId); }} />
      )}
      {modal?.rename && (
        <RenameGroupModal group={modal.rename} onClose={() => setModal(null)} onRenamed={() => { setModal(null); loadGroups(activeGradeId); }} />
      )}
    </>
  );
}
