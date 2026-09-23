import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { SearchX } from "lucide-react";
import {
  AuthShell, AuthCard, Head, Field, PhoneInput, PasswordInput, Btn, Banner, Otp, Timer,
  StateView, SuccessRing, EnvCard, PasswordChecklist, passwordValid,
} from "../ui.jsx";

/* ---------------- Student Login (returning: phone + password) ---------------- */
export function StudentLogin() {
  const nav = useNavigate();
  const [phone, setPhone] = useState(""); const [pw, setPw] = useState("");
  const [fe, setFe] = useState({}); const [err, setErr] = useState(null); const [loading, setLoading] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const f = {};
    if (phone.replace(/\D/g, "").length < 8) f.phone = "أدخل رقم هاتف صحيح.";
    if (!pw) f.pw = "هذا الحقل مطلوب.";
    setFe(f); if (Object.keys(f).length) return;
    setErr(null); setLoading(true);
    setTimeout(() => { setLoading(false); if (pw === "wrong") { setErr("بيانات الدخول غير صحيحة، حاول مرة أخرى."); return; } nav("/auth/student/environments"); }, 1000);
  };
  return (
    <AuthShell><AuthCard back="/auth">
      <Head title="تسجيل دخول الطالب" sub="ادخل إلى حسابك لمتابعة رحلتك التعليمية." />
      <form className="auth-body" onSubmit={submit} noValidate>
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="رقم الهاتف" required error={fe.phone}><PhoneInput value={phone} onChange={(e) => setPhone(e.target.value)} error={fe.phone} /></Field>
        <Field label="كلمة المرور" required error={fe.pw}><PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} placeholder="أدخل كلمة المرور" error={fe.pw} /></Field>
        <div style={{ marginBlockStart: -6 }}><button type="button" className="link" onClick={() => nav("/auth/teacher/forgot")}>نسيت كلمة المرور؟</button></div>
        <Btn type="submit" loading={loading} loadingText="جاري تسجيل الدخول…">تسجيل الدخول</Btn>
      </form>
      <div className="auth-foot" style={{ textAlign: "center" }}>
        أول مرة تستخدم مدار؟ <button className="link" onClick={() => nav("/auth/student/claim")}>تفعيل حسابي</button>
      </div>
    </AuthCard></AuthShell>
  );
}

/* ---------------- Student Claim (activate teacher-created identity) ---------------- */
export function StudentClaim() {
  const nav = useNavigate();
  const [phase, setPhase] = useState("entry"); // entry | otp | setpw | success | notfound
  const [phone, setPhone] = useState(""); const [otp, setOtp] = useState(""); const [otpErr, setOtpErr] = useState(null);
  const [pw, setPw] = useState(""); const [pw2, setPw2] = useState(""); const [pwErr, setPwErr] = useState(null);
  const [fe, setFe] = useState({}); const [loading, setLoading] = useState(false);

  const send = () => {
    if (phone.replace(/\D/g, "").length < 8) { setFe({ phone: "أدخل رقم هاتف صحيح." }); return; }
    setFe({}); setLoading(true); setTimeout(() => { setLoading(false); setPhase("otp"); }, 900);
  };
  const verify = () => {
    if (otp.length < 6) { setOtpErr("أدخل الرمز المكوّن من ٦ خانات."); return; }
    setOtpErr(null); setLoading(true);
    setTimeout(() => {
      setLoading(false);
      if (otp === "000000") { setOtpErr("رمز التحقق غير صحيح."); return; }
      if (phone.trim().endsWith("0")) { setPhase("notfound"); return; }
      setPhase("setpw");
    }, 1000);
  };
  const finish = () => {
    if (!passwordValid(pw)) { setPwErr("كلمة المرور لا تحقق المتطلبات المطلوبة."); return; }
    if (pw !== pw2) { setPwErr("كلمتا المرور غير متطابقتين."); return; }
    setPwErr(null); setLoading(true); setTimeout(() => { setLoading(false); setPhase("success"); }, 1000);
  };

  if (phase === "entry")
    return (<AuthShell><AuthCard back="/auth/student">
      <Head title="تفعيل حساب الطالب" sub="إذا قام مدرّسك بإنشاء حساب لك، يمكنك تفعيله باستخدام رقم الهاتف المسجّل لدى المدرّس." />
      <div className="auth-body">
        <Field label="رقم الهاتف" required error={fe.phone}><PhoneInput value={phone} onChange={(e) => setPhone(e.target.value)} error={fe.phone} /></Field>
        <Btn loading={loading} loadingText="جاري المتابعة…" onClick={send}>متابعة</Btn>
      </div>
    </AuthCard></AuthShell>);

  if (phase === "otp")
    return (<AuthShell><AuthCard back>
      <Head title="تأكيد رقم الهاتف" sub="أدخل رمز التحقق المرسل إلى رقم هاتفك." />
      <div className="auth-body">
        <Otp value={otp} onChange={setOtp} error={!!otpErr} />
        {otpErr && <Banner tone="err">{otpErr}</Banner>}
        <Btn loading={loading} loadingText="جاري التحقق…" onClick={verify}>تأكيد</Btn>
        <Timer seconds={45} />
      </div>
    </AuthCard></AuthShell>);

  if (phase === "setpw")
    return (<AuthShell><AuthCard>
      <Head title="أنشئ كلمة مرور لحسابك" sub="لتأمين حسابك واستخدامه في الدخول لاحقًا." />
      <div className="auth-body">
        {pwErr && <Banner tone="err">{pwErr}</Banner>}
        <Field label="كلمة المرور" required>
          <PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} placeholder="أدخل كلمة المرور" />
          <PasswordChecklist value={pw} />
        </Field>
        <Field label="تأكيد كلمة المرور" required><PasswordInput value={pw2} onChange={(e) => setPw2(e.target.value)} placeholder="أعد إدخال كلمة المرور" /></Field>
        <Btn loading={loading} loadingText="جاري التفعيل…" onClick={finish}>تفعيل حسابي</Btn>
      </div>
    </AuthCard></AuthShell>);

  if (phase === "success")
    return (<AuthShell><AuthCard><StateView icon={<SuccessRing />} tone="ok" title="تم تفعيل حسابك بنجاح" text="أهلًا بك في مدار — يمكنك الآن متابعة رحلتك التعليمية.">
      <Btn onClick={() => nav("/auth/student/environments")}>الدخول إلى مدار</Btn></StateView></AuthCard></AuthShell>);

  return (<AuthShell><AuthCard>
    <StateView icon={<SearchX size={30} />} tone="err" title="لم نجد حساب طالب مرتبطًا بهذا الرقم" text="تأكّد من استخدام رقم الهاتف الذي سجّله لك مدرّسك.">
      <Btn onClick={() => setPhase("entry")}>المحاولة مرة أخرى</Btn>
      <Btn variant="ghost" onClick={() => nav("/auth")}>تواصل مع الدعم</Btn>
    </StateView>
  </AuthCard></AuthShell>);
}

export function StudentEnvSelect() {
  const nav = useNavigate();
  return (<AuthShell><AuthCard>
    <Head title="اختر بيئة التعلّم" sub="لديك أكثر من معلّم — اختر البيئة التي تريد الدخول إليها." />
    <div className="auth-body">
      <div className="env-list">
        <EnvCard initials="أ" name="أستاذ أحمد" meta="العام الدراسي ٢٠٢٦ / ٢٠٢٧" onEnter={() => nav("/")} />
        <EnvCard initials="م" name="أستاذ محمد" meta="العام الدراسي ٢٠٢٦ / ٢٠٢٧" onEnter={() => nav("/")} />
      </div>
      <p className="field-msg" style={{ justifyContent: "center", color: "var(--soft)" }}>تعمل ضمن بيئة واحدة في كل مرة — لا تُدمج بيانات المعلّمين مطلقًا.</p>
    </div>
  </AuthCard></AuthShell>);
}
