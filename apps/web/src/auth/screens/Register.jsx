import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { CircleAlert } from "lucide-react";
import { phoneError } from "../../lib/phone.js";
import { registerApi } from "../../lib/registerApi.js";
import { ApiError } from "../../lib/api.js";
import {
  AuthShell,
  AuthCard,
  Head,
  Field,
  TextInput,
  PhoneInput,
  Btn,
  Banner,
  StateView,
  SuccessRing,
  OrbitBig,
} from "../ui.jsx";

/** Student self-registration. The QR in the teacher's "add student" screen opens this page. The student
 *  enters their own data and picks ONE grade + ONE group; the server enrols them. It can do ONE thing
 *  (create that enrolment) and never shows or accepts anything about other students. */
export function RegisterPage() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [bad, setBad] = useState(null);
  const [f, setF] = useState({
    name: "",
    phone: "",
    gradeId: "",
    groupId: "",
    parentName: "",
    parentPhone: "",
  });
  const [fe, setFe] = useState({});
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(null);

  useEffect(() => {
    let live = true;
    registerApi
      .info(token)
      .then((d) => live && setInfo(d))
      .catch(
        (e) =>
          live &&
          setBad(e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم، حاول مرة أخرى.")
      );
    return () => {
      live = false;
    };
  }, [token]);

  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const groups = useMemo(
    () => info?.grades.find((g) => String(g.id) === String(f.gradeId))?.groups || [],
    [info, f.gradeId]
  );

  const submit = async (e) => {
    e?.preventDefault();
    const x = {};
    if (f.name.trim().length < 2) x.name = "أدخل اسمك (حرفان على الأقل).";
    const pe = phoneError(f.phone);
    if (pe) x.phone = pe;
    if (!f.gradeId) x.gradeId = "اختر الصف.";
    if (!f.groupId) x.groupId = "اختر المجموعة.";
    if (f.parentName.trim().length < 2) x.parentName = "أدخل اسم ولي الأمر.";
    const ppe = phoneError(f.parentPhone);
    if (ppe) x.parentPhone = ppe;
    setFe(x);
    setErr(null);
    if (Object.keys(x).length) return;
    setLoading(true);
    try {
      setDone(
        await registerApi.submit(token, {
          name: f.name.trim(),
          phone: f.phone,
          grade_id: Number(f.gradeId),
          group_id: Number(f.groupId),
          parent_name: f.parentName.trim(),
          parent_phone: f.parentPhone,
        })
      );
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 404) setBad(e2.message);
      else if (e2 instanceof ApiError && e2.fields) {
        const m = e2.fields;
        setFe({
          name: m.name?.[0],
          phone: m.phone?.[0],
          gradeId: m.grade_id?.[0],
          groupId: m.group_ids?.[0] || m.group_id?.[0],
          parentName: m.parent_name?.[0],
          parentPhone: m.parent_phone?.[0],
        });
        setErr(e2.message);
      } else setErr(e2 instanceof ApiError ? e2.message : "تعذّر الاتصال بالخادم، حاول مرة أخرى.");
    } finally {
      setLoading(false);
    }
  };

  if (bad)
    return (
      <AuthShell>
        <AuthCard>
          <StateView
            tone="info"
            icon={<CircleAlert size={30} />}
            title="تعذّر التسجيل"
            text={bad}
          />
        </AuthCard>
      </AuthShell>
    );

  if (done)
    return (
      <AuthShell>
        <AuthCard>
          <StateView
            tone="ok"
            icon={<SuccessRing />}
            title="تم تسجيلك بنجاح"
            text="سيعطيك المعلّم كود الطالب الخاص بك لاحقًا لتفعيل حسابك."
          />
        </AuthCard>
      </AuthShell>
    );

  if (!info)
    return (
      <AuthShell>
        <div className="dash-boot" role="status" aria-label="جارٍ التحميل">
          <OrbitBig />
        </div>
      </AuthShell>
    );

  return (
    <AuthShell>
      <AuthCard>
        <Head title="تسجيل طالب جديد" sub={info.environment} />
        <form className="auth-body" onSubmit={submit} noValidate>
          {err && <Banner tone="err">{err}</Banner>}
          <Field label="اسم الطالب" required error={fe.name}>
            <TextInput
              value={f.name}
              onChange={set("name")}
              error={fe.name}
              autoComplete="name"
              maxLength={150}
            />
          </Field>
          <Field label="رقم هاتف الطالب" required error={fe.phone}>
            <PhoneInput
              value={f.phone}
              onChange={(e) => setF((s) => ({ ...s, phone: e.target.value }))}
              error={fe.phone}
            />
          </Field>
          <Field label="الصف" required error={fe.gradeId}>
            <select
              className={"inp" + (fe.gradeId ? " err" : "")}
              value={f.gradeId}
              onChange={(e) => setF((s) => ({ ...s, gradeId: e.target.value, groupId: "" }))}
            >
              <option value="">اختر الصف</option>
              {info.grades.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="المجموعة"
            required
            error={fe.groupId}
            hint={f.gradeId && groups.length === 0 ? "لا توجد مجموعات في هذا الصف بعد." : "مجموعة واحدة فقط."}
          >
            <select
              className={"inp" + (fe.groupId ? " err" : "")}
              value={f.groupId}
              onChange={set("groupId")}
              disabled={!f.gradeId}
            >
              <option value="">{f.gradeId ? "اختر المجموعة" : "اختر الصف أولًا"}</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="اسم ولي الأمر" required error={fe.parentName}>
            <TextInput
              value={f.parentName}
              onChange={set("parentName")}
              error={fe.parentName}
              maxLength={150}
            />
          </Field>
          <Field label="رقم هاتف ولي الأمر" required error={fe.parentPhone}>
            <PhoneInput
              value={f.parentPhone}
              onChange={(e) => setF((s) => ({ ...s, parentPhone: e.target.value }))}
              error={fe.parentPhone}
            />
          </Field>
          <Btn type="submit" loading={loading} loadingText="جاري التسجيل…">
            سجّلني
          </Btn>
        </form>
        <div className="auth-foot" style={{ textAlign: "center" }}>
          هذه الصفحة تسجّل بياناتك لدى المعلّم فقط، ولا تتيح الاطلاع على أي بيانات.
        </div>
      </AuthCard>
    </AuthShell>
  );
}
