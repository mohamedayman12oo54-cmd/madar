import { useEffect, useState } from "react";
import { Plus, Search, UserRoundPlus } from "lucide-react";
import { Field, TextInput, PhoneInput, Btn, Banner, Modal } from "../auth/ui.jsx";
import { enrollmentsApi, groupsApi } from "../lib/academicsApi.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import ComingSoon from "./ComingSoon.jsx";

function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

function AddStudentModal({ grades, onClose, onCreated }) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [gradeId, setGradeId] = useState(grades[0]?.id || "");
  const [groups, setGroups] = useState([]);
  const [groupId, setGroupId] = useState("");
  const [err, setErr] = useState(null);
  const [fe, setFe] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setGroupId("");
    if (!gradeId) { setGroups([]); return; }
    groupsApi.list({ grade_id: gradeId }).then((data) => setGroups(Array.isArray(data) ? data : data.results || [])).catch(() => setGroups([]));
  }, [gradeId]);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null); setFe({});
    if (name.trim().length < 2) { setFe({ name: "أدخل اسم الطالب." }); return; }
    if (phone.replace(/\D/g, "").length < 8) { setFe({ phone: "أدخل رقم هاتف صحيح." }); return; }
    if (!gradeId) { setErr("اختر الصف الدراسي أولًا."); return; }
    setSaving(true);
    try {
      await enrollmentsApi.create({ name: name.trim(), phone, grade_id: gradeId, group_id: groupId || null });
      onCreated();
    } catch (e2) {
      if (e2 instanceof ApiError && e2.fields) setFe(e2.fields);
      else setErr(e2 instanceof ApiError ? e2.message : "تعذّر إضافة الطالب.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="إضافة طالب" text="سيتمكن الطالب من تفعيل حسابه لاحقًا باستخدام رقم الهاتف هذا." onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="اسم الطالب" required error={fe.name}>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </Field>
        <Field label="رقم الهاتف" required error={fe.phone}>
          <PhoneInput value={phone} onChange={(e) => setPhone(e.target.value)} error={fe.phone} />
        </Field>
        <Field label="الصف الدراسي" required error={fe.grade_id}>
          <select className="inp" value={gradeId} onChange={(e) => setGradeId(Number(e.target.value))}>
            {grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        </Field>
        <Field label="المجموعة (اختياري)" error={fe.group_id}>
          <select className="inp" value={groupId} onChange={(e) => setGroupId(e.target.value)} disabled={!groups.length}>
            <option value="">بدون مجموعة</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        </Field>
        <Btn type="submit" loading={saving} loadingText="جارٍ الإضافة…">إضافة الطالب</Btn>
      </form>
    </Modal>
  );
}

export default function StudentsPage() {
  const { grades, status: gradesStatus } = useGrades();
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search);
  const [gradeFilter, setGradeFilter] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ results: [], count: 0, next: null, previous: null });
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [showAdd, setShowAdd] = useState(false);

  useEffect(() => { setPage(1); }, [debouncedSearch, gradeFilter]);

  const reload = () => {
    setStatus((s) => (s === "ready" ? "ready" : "loading"));
    enrollmentsApi.list({ search: debouncedSearch, grade_id: gradeFilter, page })
      .then((res) => { setData(Array.isArray(res) ? { results: res, count: res.length } : res); setStatus("ready"); })
      .catch((e) => { setError(e instanceof ApiError ? e.message : "حدث خطأ أثناء تحميل البيانات."); setStatus("error"); });
  };

  useEffect(reload, [debouncedSearch, gradeFilter, page]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleActive = async (enrollment) => {
    const updated = await enrollmentsApi.update(enrollment.id, { is_active: !enrollment.is_active }).catch(() => null);
    if (updated) setData((d) => ({ ...d, results: d.results.map((r) => (r.id === updated.id ? updated : r)) }));
  };

  return (
    <>
      <div className="dash-section-head">
        <h2>الطلاب{data.count ? ` (${data.count})` : ""}</h2>
        <Btn onClick={() => setShowAdd(true)} disabled={gradesStatus !== "ready" || grades.length === 0}>
          <UserRoundPlus size={16} /> إضافة طالب
        </Btn>
      </div>

      {gradesStatus === "ready" && grades.length === 0 && (
        <Banner tone="info">أنشئ صفًا دراسيًا أولًا من صفحة «المجموعات» قبل إضافة الطلاب.</Banner>
      )}

      <div className="dash-filters">
        <div className="dash-search">
          <Search size={16} />
          <input placeholder="ابحث بالاسم أو رقم الهاتف" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="inp" value={gradeFilter} onChange={(e) => setGradeFilter(e.target.value)}>
          <option value="">كل الصفوف</option>
          {grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
        </select>
      </div>

      {status === "loading" && <p className="field-msg">جاري تحميل البيانات...</p>}
      {status === "error" && <Banner tone="err">{error}</Banner>}

      {status === "ready" && data.results.length === 0 && (
        <ComingSoon
          title={debouncedSearch || gradeFilter ? "لا نتائج مطابقة" : "لا يوجد طلاب بعد"}
          text={debouncedSearch || gradeFilter ? "جرّب تعديل البحث أو الفلتر." : "ابدأ بإضافة أول طالب في هذه البيئة."}
        />
      )}

      {status === "ready" && data.results.length > 0 && (
        <>
          <div className="dash-table-wrap">
            <table className="dash-table">
              <thead>
                <tr><th>الاسم</th><th>رقم الهاتف</th><th>الصف</th><th>المجموعة</th><th>الحالة</th></tr>
              </thead>
              <tbody>
                {data.results.map((e) => (
                  <tr key={e.id}>
                    <td>{e.student.name}</td>
                    <td className="ltr-cell">{e.student.phone}</td>
                    <td>{e.grade.name}</td>
                    <td>{e.group?.name || "—"}</td>
                    <td>
                      <button className={"dash-pill" + (e.is_active ? " on" : "")} onClick={() => toggleActive(e)}>
                        {e.is_active ? "نشط" : "غير نشط"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(data.previous || data.next) && (
            <div className="dash-pager">
              <button disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>السابق</button>
              <span>صفحة {page}</span>
              <button disabled={!data.next} onClick={() => setPage((p) => p + 1)}>التالي</button>
            </div>
          )}
        </>
      )}

      {showAdd && (
        <AddStudentModal grades={grades} onClose={() => setShowAdd(false)} onCreated={() => { setShowAdd(false); if (page === 1) reload(); else setPage(1); }} />
      )}
    </>
  );
}
