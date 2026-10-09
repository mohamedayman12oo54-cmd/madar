import { useEffect, useId, useState } from "react";
import { Search, UserRoundPlus, Pencil, QrCode } from "lucide-react";
import { Field, TextInput, PhoneInput, Btn, Banner, Modal } from "../auth/ui.jsx";
import { enrollmentsApi, groupsApi } from "../lib/academicsApi.js";
import { ApiError } from "../lib/api.js";
import { formatPhone, phoneError } from "../lib/phone.js";
import QRCode from "qrcode";
import { scannerApi } from "../lib/dashboardApi.js";
import { useGrades } from "./useGrades.js";
import { CheckList, Confirm, Empty, PageHeader, toggleId, useDebounced } from "./common.jsx";

const listOf = (d) => (Array.isArray(d) ? d : d?.results || []);

/** One form for BOTH "add" and "edit" so the two can never drift apart.
 *  Edit rules (enforced by the server too): grade is fixed for the year; the
 *  login phone can only be corrected while the account is unclaimed and not
 *  shared with another teacher; the name here is this teacher's own label. */
function StudentFormModal({ grades, enrollment, onClose, onSaved }) {
  const editing = !!enrollment;
  const [name, setName] = useState(enrollment?.student.name || "");
  const [phone, setPhone] = useState(enrollment ? `+${enrollment.student.phone}` : "");
  const [gradeId, setGradeId] = useState(enrollment?.grade.id || grades[0]?.id || "");
  const [groups, setGroups] = useState([]);
  const [groupIds, setGroupIds] = useState(enrollment?.groups.map((g) => g.id) || []);
  const [parentName, setParentName] = useState(enrollment?.parent_name || "");
  const [parentPhone, setParentPhone] = useState(enrollment?.parent_phone ? `+${enrollment.parent_phone}` : "");
  const [active, setActive] = useState(enrollment ? enrollment.is_active : true);
  const [err, setErr] = useState(null);
  const [fe, setFe] = useState({});
  const [saving, setSaving] = useState(false);
  const phoneLocked = editing && !enrollment.can_edit_phone;
  const formId = useId();

  useEffect(() => {
    if (!gradeId) { setGroups([]); return; }
    groupsApi.list({ grade_id: gradeId }).then((d) => setGroups(listOf(d))).catch(() => setGroups([]));
  }, [gradeId]);

  const changeGrade = (id) => { setGradeId(id); setGroupIds([]); };

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    const errors = {};
    if (name.trim().length < 2) errors[editing ? "student_name" : "name"] = "أدخل اسم الطالب (حرفان على الأقل).";
    if (!phoneLocked) { const pe = phoneError(phone); if (pe) errors.phone = pe; }
    const ppe = phoneError(parentPhone, { required: !editing });
    if (ppe) errors.parent_phone = ppe;
    if (!gradeId) { setErr("اختر الصف الدراسي أولًا."); return; }
    if (Object.keys(errors).length) { setFe(errors); return; }
    setFe({});
    setSaving(true);
    try {
      if (editing) {
        const body = { student_name: name.trim(), parent_name: parentName.trim(), parent_phone: parentPhone, group_ids: groupIds, is_active: active };
        if (!phoneLocked && phone !== `+${enrollment.student.phone}`) body.phone = phone;
        await enrollmentsApi.update(enrollment.id, body);
        onSaved({ edited: true });
      } else {
        const res = await enrollmentsApi.create({
          name: name.trim(), phone, grade_id: gradeId, group_ids: groupIds, is_active: active,
          parent_name: parentName.trim(), parent_phone: parentPhone,
        });
        onSaved({ created: res.created, enrollmentId: res.enrollment_id, active });
      }
    } catch (e2) {
      if (e2 instanceof ApiError && e2.fields) setFe(e2.fields);
      else setErr(e2 instanceof ApiError ? e2.message : "تعذّر حفظ البيانات.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal size="lg" title={editing ? "تعديل بيانات الطالب" : "إضافة طالب"}
      text={editing ? "صحّح ما أخطأت فيه. التعديل يخص بيئتك أنت فقط." : "سيتمكن الطالب من تفعيل حسابه لاحقًا برقم الهاتف هذا إذا كان نشطًا."}
      onClose={onClose}
      footer={<>
        <Btn variant="ghost" type="button" onClick={onClose}>إلغاء</Btn>
        <Btn type="submit" form={formId} loading={saving} loadingText="جارٍ الحفظ…">{editing ? "حفظ التعديلات" : "إضافة الطالب"}</Btn>
      </>}>
      <form id={formId} onSubmit={submit} className="dash-form" noValidate>
        {err && <div className="form-wide"><Banner tone="err">{err}</Banner></div>}
        <Field label="اسم الطالب" required error={fe.name || fe.student_name}>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} autoFocus maxLength={150} />
        </Field>
        <Field label="رقم هاتف الطالب (موبايل)" required error={fe.phone}
          hint={phoneLocked ? "لا يمكن تعديل الرقم بعد أن يفعّل الطالب حسابه أو إذا كان مرتبطًا بمعلم آخر." : "اختر الدولة ثم اكتب الرقم — يُقبل رقم موبايل صحيح لتلك الدولة فقط."}>
          <PhoneInput value={phone} onChange={(e) => setPhone(e.target.value)} error={fe.phone} disabled={phoneLocked} />
        </Field>
        <Field label="الصف الدراسي" required error={fe.grade_id} hint={editing ? "لا يمكن تغيير الصف خلال نفس العام الدراسي." : undefined}>
          <select className="inp" value={gradeId} disabled={editing} onChange={(e) => changeGrade(Number(e.target.value))}>
            {grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        </Field>
        <Field className="form-wide" label="المجموعات (يمكن اختيار أكثر من مجموعة)" error={fe.group_ids}>
          <CheckList items={groups} selected={groupIds} onToggle={(id) => setGroupIds((l) => toggleId(l, id))} empty="لا توجد مجموعات في هذا الصف بعد." />
        </Field>
        <Field label="اسم ولي الأمر (اختياري)" error={fe.parent_name}>
          <TextInput value={parentName} onChange={(e) => setParentName(e.target.value)} maxLength={150} />
        </Field>
        <Field label={editing ? "هاتف ولي الأمر" : "هاتف ولي الأمر"} required={!editing} error={fe.parent_phone} hint="للتواصل فقط — لا ينشئ حسابًا لولي الأمر.">
          <PhoneInput value={parentPhone} onChange={(e) => setParentPhone(e.target.value)} error={fe.parent_phone} />
        </Field>
        <label className="check-item form-wide">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          <span>الطالب نشط (يستطيع تفعيل حسابه والدخول)</span>
        </label>
      </form>
    </Modal>
  );
}

export default function StudentsPage() {
  const { grades, status: gradesStatus } = useGrades();
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search);
  const [gradeFilter, setGradeFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ results: [], count: 0, next: null, previous: null });
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [form, setForm] = useState(null); // null | "add" | enrollment
  const [confirm, setConfirm] = useState(null); // enrollment being toggled
  const [notice, setNotice] = useState(null);
  const [badge, setBadge] = useState(null);

  useEffect(() => { setPage(1); }, [debouncedSearch, gradeFilter, activeFilter]);

  const reload = () => {
    setStatus((s) => (s === "ready" ? "ready" : "loading"));
    enrollmentsApi.list({ search: debouncedSearch, grade_id: gradeFilter, is_active: activeFilter, page })
      .then((res) => { setData(Array.isArray(res) ? { results: res, count: res.length } : res); setStatus("ready"); })
      .catch((e) => { setError(e instanceof ApiError ? e.message : "حدث خطأ أثناء تحميل البيانات."); setStatus("error"); });
  };
  useEffect(reload, [debouncedSearch, gradeFilter, activeFilter, page]); // eslint-disable-line react-hooks/exhaustive-deps

  const setActive = async (enrollment, value) => {
    try {
      const updated = await enrollmentsApi.update(enrollment.id, { is_active: value });
      setData((d) => ({ ...d, results: d.results.map((r) => (r.id === updated.id ? updated : r)) }));
      setNotice({ tone: "info", text: value
        ? "تم تفعيل الطالب. يستطيع الآن تفعيل حسابه والدخول."
        : "تم إيقاف الطالب. لن يستطيع الدخول أو تفعيل حسابه إلا إذا فعّله معلم آخر." });
    } catch (e) {
      setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر تغيير الحالة." });
    }
    setConfirm(null);
  };

  const onSaved = async (result) => {
    setForm(null);
    if (result.edited) { setNotice({ tone: "info", text: "تم حفظ التعديلات." }); reload(); return; }
    if (page === 1) reload(); else setPage(1);
    const saved = await enrollmentsApi.get(result.enrollmentId).catch(() => null);
    setNotice({
      tone: "info", editId: saved?.id, editRow: saved,
      text: (result.created ? "تمت إضافة الطالب. " : "هذا الطالب مسجّل لديك بالفعل. ")
        + (result.active ? "يستطيع تفعيل حسابه برقم هاتفه." : "الطالب غير نشط: لن يستطيع التفعيل حتى تفعّله."),
    });
  };

  return (
    <>
      <PageHeader infoKey="students" title="الطلاب" count={data.count}>
        <Btn onClick={() => setForm("add")} disabled={gradesStatus !== "ready" || grades.length === 0}>
          <UserRoundPlus size={16} /> إضافة طالب
        </Btn>
      </PageHeader>

      {gradesStatus === "ready" && grades.length === 0 && (
        <Banner tone="info">أنشئ صفًا دراسيًا أولًا من صفحة «المجموعات» قبل إضافة الطلاب.</Banner>
      )}
      {notice && (
        <Banner tone={notice.tone}>
          {notice.text}{" "}
          {notice.editRow && <button className="dash-linkish" onClick={() => setForm(notice.editRow)}>تعديل بيانات الطالب</button>}{" "}
          <button className="dash-linkish" onClick={() => setNotice(null)}>إخفاء</button>
        </Banner>
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
        <select className="inp" value={activeFilter} onChange={(e) => setActiveFilter(e.target.value)}>
          <option value="">الكل</option><option value="true">النشطون</option><option value="false">غير النشطين</option>
        </select>
      </div>

      {status === "loading" && <p className="field-msg">جاري تحميل البيانات...</p>}
      {status === "error" && <Banner tone="err">{error}</Banner>}
      {status === "ready" && data.results.length === 0 && (
        <Empty title={debouncedSearch || gradeFilter || activeFilter ? "لا نتائج مطابقة" : "لا يوجد طلاب بعد"}
          text={debouncedSearch || gradeFilter || activeFilter ? "جرّب تعديل البحث أو الفلتر." : "ابدأ بإضافة أول طالب في هذه البيئة."} />
      )}

      {status === "ready" && data.results.length > 0 && (
        <>
          <div className="dash-table-wrap">
            <table className="dash-table">
              <thead><tr><th>الاسم</th><th>رقم الهاتف</th><th>ولي الأمر</th><th>الصف</th><th>المجموعات</th><th>الحالة</th><th></th></tr></thead>
              <tbody>
                {data.results.map((e) => (
                  <tr key={e.id}>
                    <td>{e.student.name}</td>
                    <td className="ltr-cell">{formatPhone(e.student.phone)}</td>
                    <td>{e.parent_name || e.parent_phone ? <>{e.parent_name} <span className="ltr-cell">{e.parent_phone ? formatPhone(e.parent_phone) : ""}</span></> : "—"}</td>
                    <td>{e.grade.name}</td>
                    <td><div className="tag-list">{e.groups.length ? e.groups.map((g) => <span key={g.id} className="chip-s">{g.name}</span>) : "—"}</div></td>
                    <td>
                      <button className={"dash-pill" + (e.is_active ? " on" : "")} onClick={() => (e.is_active ? setConfirm(e) : setActive(e, true))}
                        aria-label={e.is_active ? "إيقاف الطالب" : "تفعيل الطالب"}>
                        {e.is_active ? "نشط" : "غير نشط"}
                      </button>
                    </td>
                    <td className="row-actions">
                      <button className="mini-btn" onClick={() => setForm(e)}><Pencil size={13} /> تعديل</button>
                      <button className="mini-btn" onClick={() => setBadge(e)}><QrCode size={13} /> بادچ <code className="badge-chip">{e.qr_token}</code></button>
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

      {form && <StudentFormModal grades={grades} enrollment={form === "add" ? null : form} onClose={() => setForm(null)} onSaved={onSaved} />}
      {badge && <BadgeModal enrollment={badge} onClose={() => setBadge(null)} onRotated={reload} />}
      {confirm && (
        <Confirm danger title="إيقاف الطالب؟" confirmLabel="نعم، إيقاف"
          text={`«${confirm.student.name}» لن يستطيع الدخول أو تفعيل حسابه، وستنتهي جلساته الحالية، إلا إذا فعّله معلم آخر. بياناته عندك تبقى كما هي.`}
          onConfirm={() => setActive(confirm, false)} onClose={() => setConfirm(null)} />
      )}
    </>
  );
}

/** Printable student badge. The QR encodes ONLY the opaque token — no name,
 *  no id, no phone — so a photographed badge leaks nothing. Rotating issues a
 *  new token and the old badge stops working immediately. */
function BadgeModal({ enrollment, onClose, onRotated }) {
  const [svg, setSvg] = useState("");
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState(enrollment.qr_token);

  useEffect(() => {
    let alive = true;
    QRCode.toString(token || "", { type: "svg", margin: 1, width: 220, errorCorrectionLevel: "M" })
      .then((out) => { if (alive) setSvg(out); })
      .catch(() => { if (alive) setSvg(""); });
    return () => { alive = false; };
  }, [token]);

  const rotate = async () => {
    setBusy(true);
    try {
      const r = await scannerApi.rotateBadge(enrollment.id);
      setToken(r.qr_token);
      onRotated?.();
    } finally { setBusy(false); }
  };

  return (
    <Modal size="md" title={`بادچ ${enrollment.display_name || enrollment.student_name}`}
      text="اطبع هذا الرمز وسلّمه للطالب. الرمز لا يحتوي على أي بيانات شخصية، ويمكنك تغييره في أي وقت."
      onClose={onClose}
      footer={<>
        <Btn variant="ghost" onClick={onClose}>إغلاق</Btn>
        <Btn variant="ghost" loading={busy} onClick={rotate}>تغيير الرمز</Btn>
        <Btn onClick={() => window.print()}>طباعة</Btn>
      </>}>
      <div className="badge-print">
        {svg
          ? <div className="badge-qr" aria-label="رمز الطالب" dangerouslySetInnerHTML={{ __html: svg }} />
          : <p className="field-msg">تعذّر توليد الرمز.</p>}
        <strong>{enrollment.display_name || enrollment.student_name}</strong>
        <span className="stat-sub">{enrollment.grade_name || ""}</span>
        {/* The same code the QR encodes — printed so it can be read aloud or
            typed in when a camera is not available. */}
        <code className="badge-code">{token}</code>
      </div>
      <Banner tone="info">إصدار رمز جديد يُبطل البادچ القديم فورًا — استخدمه إذا ضاع أو تمت مشاركته.</Banner>
    </Modal>
  );
}
