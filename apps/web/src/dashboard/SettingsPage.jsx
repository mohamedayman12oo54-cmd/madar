import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Field, TextInput, PasswordInput, PasswordChecklist, passwordValid, Btn, Banner } from "../auth/ui.jsx";
import { settingsApi } from "../lib/dashboardApi.js";
import { ApiError } from "../lib/api.js";
import { formatPhone } from "../lib/phone.js";
import { useSession } from "../state/session.jsx";
import { useEnvironment } from "../state/environment.jsx";
import { Confirm, PageHeader } from "./common.jsx";

const fieldsText = (e, fb) => (e instanceof ApiError ? (e.fields ? Object.values(e.fields).flat().join(" ") : e.message) : fb);

function Section({ title, children }) {
  return <section className="dash-card" style={{ marginBlockEnd: 18 }}><h3 style={{ marginBlockEnd: 12 }}>{title}</h3>{children}</section>;
}

function ProfileSection() {
  const { user, refresh } = useSession();
  const [name, setName] = useState(user?.name || "");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const save = async (e) => {
    e.preventDefault(); setMsg(null);
    if (name.trim().length < 2) { setMsg({ tone: "err", text: "الاسم يجب أن يكون حرفين على الأقل." }); return; }
    setBusy(true);
    try { await settingsApi.updateName(name.trim()); await refresh?.(); setMsg({ tone: "info", text: "تم حفظ الاسم." }); }
    catch (e2) { setMsg({ tone: "err", text: fieldsText(e2, "تعذّر الحفظ.") }); }
    finally { setBusy(false); }
  };
  return (
    <Section title="بياناتي">
      {msg && <Banner tone={msg.tone}>{msg.text}</Banner>}
      <form onSubmit={save} className="dash-form">
        <Field label="الاسم"><TextInput value={name} onChange={(e) => setName(e.target.value)} maxLength={150} /></Field>
        <Field label="البريد الإلكتروني" hint="هوية دخول — تغييره يحتاج تحققًا برمز OTP وهذه الخاصية غير متاحة بعد."><TextInput ltr value={user?.email || ""} disabled readOnly /></Field>
        <Field label="رقم الهاتف" hint="هوية دخول — تغييره يحتاج تحققًا برمز OTP وهذه الخاصية غير متاحة بعد."><TextInput ltr value={user?.phone ? formatPhone(user.phone) : ""} disabled readOnly /></Field>
        <Btn type="submit" loading={busy} loadingText="جارٍ الحفظ…">حفظ الاسم</Btn>
      </form>
    </Section>
  );
}

function EnvironmentSection() {
  const env = useEnvironment();
  const [data, setData] = useState(null);
  const [name, setName] = useState("");
  const [stage, setStage] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { settingsApi.environment().then((d) => { setData(d); setName(d.name); setStage(d.subject_stage || ""); }).catch(() => setMsg({ tone: "err", text: "تعذّر تحميل بيانات البيئة." })); }, []);
  const save = async (e) => {
    e.preventDefault(); setMsg(null); setBusy(true);
    try { const d = await settingsApi.renameEnvironment({ name: name.trim(), subject_stage: stage.trim() }); setData(d); await env.revalidate?.(); setMsg({ tone: "info", text: "تم حفظ بيانات البيئة." }); }
    catch (e2) { setMsg({ tone: "err", text: fieldsText(e2, "تعذّر الحفظ.") }); }
    finally { setBusy(false); }
  };
  return (
    <Section title="بيئتي التعليمية">
      {msg && <Banner tone={msg.tone}>{msg.text}</Banner>}
      {data && <form onSubmit={save} className="dash-form">
        <Field label="اسم البيئة" required><TextInput value={name} onChange={(e) => setName(e.target.value)} maxLength={150} /></Field>
        <Field label="المادة / المرحلة"><TextInput value={stage} onChange={(e) => setStage(e.target.value)} maxLength={150} /></Field>
        <Field label="العام الدراسي الحالي" hint="يُحدَّد تلقائيًا ويُسجَّل عند إنشاء كل تسجيل."><TextInput ltr value={data.academic_year || ""} disabled readOnly /></Field>
        <Btn type="submit" loading={busy} loadingText="جارٍ الحفظ…" disabled={name.trim().length < 2}>حفظ</Btn>
      </form>}
    </Section>
  );
}

export function SecuritySection({ loginPath = "/auth/teacher/login" }) {
  const nav = useNavigate();
  const { logout } = useSession();
  const env = useEnvironment();
  const [cur, setCur] = useState(""); const [pw, setPw] = useState(""); const [pw2, setPw2] = useState("");
  const [fe, setFe] = useState({}); const [msg, setMsg] = useState(null); const [busy, setBusy] = useState(false); const [confirm, setConfirm] = useState(false);
  const change = async (e) => {
    e.preventDefault(); setMsg(null);
    const errors = {};
    if (!cur) errors.current_password = "أدخل كلمة المرور الحالية.";
    if (!passwordValid(pw)) errors.password = "كلمة المرور لا تستوفي الشروط.";
    if (pw !== pw2) errors.password2 = "كلمتا المرور غير متطابقتين.";
    if (Object.keys(errors).length) { setFe(errors); return; }
    setFe({}); setBusy(true);
    try { await settingsApi.changePassword(cur, pw, pw2); setCur(""); setPw(""); setPw2(""); setMsg({ tone: "info", text: "تم تغيير كلمة المرور وتسجيل الخروج من الأجهزة الأخرى." }); }
    catch (e2) { if (e2 instanceof ApiError && e2.fields) setFe(e2.fields); else setMsg({ tone: "err", text: fieldsText(e2, "تعذّر تغيير كلمة المرور.") }); }
    finally { setBusy(false); }
  };
  const everywhere = async () => {
    try { await settingsApi.signOutEverywhere(); } catch { /* the session is revoked server-side either way */ }
    env.clear(); await logout(); nav(loginPath, { replace: true });
  };
  return (
    <Section title="الأمان">
      {msg && <Banner tone={msg.tone}>{msg.text}</Banner>}
      <form onSubmit={change} className="dash-form" noValidate>
        <Field label="كلمة المرور الحالية" required error={fe.current_password}><PasswordInput value={cur} onChange={(e) => setCur(e.target.value)} error={fe.current_password} autoComplete="current-password" /></Field>
        <Field label="كلمة المرور الجديدة" required error={fe.password}><PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} error={fe.password} autoComplete="new-password" /></Field>
        <PasswordChecklist value={pw} />
        <Field label="تأكيد كلمة المرور الجديدة" required error={fe.password2}><PasswordInput value={pw2} onChange={(e) => setPw2(e.target.value)} error={fe.password2} autoComplete="new-password" /></Field>
        <Btn type="submit" loading={busy} loadingText="جارٍ التغيير…">تغيير كلمة المرور</Btn>
      </form>
      <hr style={{ margin: "18px 0", border: 0, borderTop: "1px solid var(--line)" }} />
      <p className="stat-sub" style={{ marginBlockEnd: 10 }}>إذا شككت أن أحدًا دخل حسابك، سجّل الخروج من كل الأجهزة (بما فيها هذا الجهاز) ثم غيّر كلمة المرور.</p>
      <Btn variant="ghost" onClick={() => setConfirm(true)}>تسجيل الخروج من كل الأجهزة</Btn>
      {confirm && <Confirm danger title="تسجيل الخروج من كل الأجهزة؟" confirmLabel="تسجيل الخروج" text="ستنتهي كل جلساتك الحالية فورًا وستحتاج إلى تسجيل الدخول من جديد." onConfirm={everywhere} onClose={() => setConfirm(false)} />}
    </Section>
  );
}

export default function SettingsPage() {
  return (<><PageHeader infoKey="settings" title="الإعدادات" /><ProfileSection /><EnvironmentSection /><SecuritySection /></>);
}
