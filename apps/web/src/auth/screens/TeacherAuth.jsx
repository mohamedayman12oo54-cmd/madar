import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PartyPopper } from "lucide-react";
import {
  AuthShell, AuthCard, Head, Field, TextInput, PasswordInput, Btn, Banner, Otp, Timer,
  Stepper, StateView, SuccessRing, EnvCard, PasswordChecklist, passwordValid,
} from "../ui.jsx";

const emailOk = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

export function TeacherLogin() {
  const nav = useNavigate();
  const [id, setId] = useState(""); const [pw, setPw] = useState("");
  const [err, setErr] = useState(null); const [fe, setFe] = useState({}); const [loading, setLoading] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const f = {};
    if (!id.trim()) f.id = "هذا الحقل مطلوب.";
    if (!pw) f.pw = "هذا الحقل مطلوب.";
    setFe(f); if (Object.keys(f).length) return;
    setErr(null); setLoading(true);
    setTimeout(() => { setLoading(false); if (pw === "wrong") { setErr("بيانات الدخول غير صحيحة، حاول مرة أخرى."); return; } nav("/auth/teacher/environments"); }, 1100);
  };
  return (
    <AuthShell>
      <AuthCard back="/auth">
        <Head title="تسجيل دخول المدرّس" sub="ادخل إلى حسابك لإدارة بيئتك التعليمية." />
        <form className="auth-body" onSubmit={submit} noValidate>
          {err && <Banner tone="err">{err}</Banner>}
          <Field label="رقم الهاتف أو البريد الإلكتروني" required error={fe.id}>
            <TextInput value={id} onChange={(e) => setId(e.target.value)} placeholder="أدخل رقم الهاتف أو البريد الإلكتروني" error={fe.id} />
          </Field>
          <Field label="كلمة المرور" required error={fe.pw}>
            <PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} placeholder="أدخل كلمة المرور" error={fe.pw} />
          </Field>
          <div style={{ marginBlockStart: -6 }}><button type="button" className="link" onClick={() => nav("/auth/teacher/forgot")}>هل نسيت كلمة المرور؟</button></div>
          <Btn type="submit" loading={loading} loadingText="جاري تسجيل الدخول…">تسجيل الدخول</Btn>
        </form>
        <div className="auth-foot" style={{ textAlign: "center" }}>
          ليس لديك حساب؟ <button className="link" onClick={() => nav("/auth/teacher/signup")}>إنشاء حساب مدرّس</button>
        </div>
      </AuthCard>
    </AuthShell>
  );
}

export function TeacherSignup() {
  const nav = useNavigate();
  const [step, setStep] = useState(0); const [loading, setLoading] = useState(false);
  const [otp, setOtp] = useState(""); const [otpErr, setOtpErr] = useState(null);
  const [f, setF] = useState({ name: "", email: "", phone: "", pw: "", pw2: "" });
  const [fe, setFe] = useState({});
  const on = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const validate1 = () => {
    const x = {};
    if (!f.name.trim()) x.name = "هذا الحقل مطلوب.";
    if (!emailOk(f.email)) x.email = "أدخل بريدًا إلكترونيًا صحيحًا.";
    if (f.phone.replace(/\D/g, "").length < 8) x.phone = "أدخل رقم هاتف صحيح.";
    if (!passwordValid(f.pw)) x.pw = "كلمة المرور لا تحقق المتطلبات المطلوبة.";
    if (f.pw2 !== f.pw) x.pw2 = "كلمتا المرور غير متطابقتين.";
    setFe(x); return Object.keys(x).length === 0;
  };
  const next1 = () => { if (!validate1()) return; setLoading(true); setTimeout(() => { setLoading(false); setStep(1); }, 1000); };
  const verify = () => {
    if (otp.length < 6) { setOtpErr("أدخل الرمز المكوّن من ٦ خانات."); return; }
    setOtpErr(null); setLoading(true);
    setTimeout(() => { setLoading(false); if (otp === "000000") { setOtpErr("رمز التحقق غير صحيح."); return; } setStep(2); }, 1000);
  };

  if (step === 3)
    return (<AuthShell><AuthCard><StateView icon={<SuccessRing />} tone="ok" title="تم إنشاء حسابك بنجاح" text="مرحبًا بك في مدار — بيئتك التعليمية جاهزة للبدء.">
      <Btn onClick={() => nav("/auth/teacher/welcome")}>الدخول إلى مدار</Btn></StateView></AuthCard></AuthShell>);

  return (
    <AuthShell>
      <AuthCard back={step === 0 ? "/auth/teacher/login" : undefined}>
        <Stepper total={3} current={step} />
        {step === 0 && (<>
          <Head title="إنشاء الحساب" sub="أدخل بياناتك لإنشاء حساب مدرّس." />
          <div className="auth-body">
            <Field label="الاسم الكامل" required error={fe.name}><TextInput value={f.name} onChange={on("name")} placeholder="أدخل اسمك الكامل" error={fe.name} /></Field>
            <Field label="البريد الإلكتروني" required error={fe.email}><TextInput ltr value={f.email} onChange={on("email")} placeholder="you@example.com" error={fe.email} /></Field>
            <Field label="رقم الهاتف" required error={fe.phone}><TextInput ltr value={f.phone} onChange={on("phone")} placeholder="1XXXXXXXXX" error={fe.phone} /></Field>
            <Field label="كلمة المرور" required error={fe.pw}>
              <PasswordInput value={f.pw} onChange={on("pw")} placeholder="أدخل كلمة المرور" error={fe.pw} />
              <PasswordChecklist value={f.pw} />
            </Field>
            <Field label="تأكيد كلمة المرور" required error={fe.pw2}><PasswordInput value={f.pw2} onChange={on("pw2")} placeholder="أعد إدخال كلمة المرور" error={fe.pw2} /></Field>
            <Btn loading={loading} loadingText="جاري المتابعة…" onClick={next1}>متابعة</Btn>
          </div>
        </>)}
        {step === 1 && (<>
          <Head title="تأكيد الحساب" sub="أدخل رمز التحقق المرسل إلى وسيلة الاتصال الخاصة بك." />
          <div className="auth-body">
            <Otp value={otp} onChange={setOtp} error={!!otpErr} />
            {otpErr && <Banner tone="err">{otpErr}</Banner>}
            <Btn loading={loading} loadingText="جاري التحقق…" onClick={verify}>تأكيد</Btn>
            <Timer seconds={45} />
          </div>
        </>)}
        {step === 2 && (<>
          <Head title="إعداد البيئة التعليمية" sub="خطوة سريعة لتهيئة بيئتك — يمكنك تعديلها لاحقًا." />
          <div className="auth-body">
            <Field label="اسم بيئتك التعليمية"><TextInput placeholder="مثال: مجموعات الأستاذ أحمد" /></Field>
            <Field label="المادة أو المرحلة" hint="اختياري"><TextInput placeholder="مثال: الرياضيات — الثانوية" /></Field>
            <Btn loading={loading} loadingText="جاري الإنهاء…" onClick={() => { setLoading(true); setTimeout(() => { setLoading(false); setStep(3); }, 900); }}>إنهاء الإعداد</Btn>
          </div>
        </>)}
      </AuthCard>
    </AuthShell>
  );
}

export function TeacherForgot() {
  const nav = useNavigate();
  const [step, setStep] = useState(0); const [loading, setLoading] = useState(false);
  const [otp, setOtp] = useState(""); const [pw, setPw] = useState(""); const [pw2, setPw2] = useState(""); const [err, setErr] = useState(null);
  const step2 = () => { setLoading(true); setTimeout(() => { setLoading(false); setStep((s) => s + 1); }, 1000); };
  const finish = () => {
    if (!passwordValid(pw)) { setErr("كلمة المرور لا تحقق المتطلبات المطلوبة."); return; }
    if (pw !== pw2) { setErr("كلمتا المرور غير متطابقتين."); return; }
    setErr(null); setLoading(true); setTimeout(() => { setLoading(false); setStep(3); }, 1000);
  };
  if (step === 3)
    return (<AuthShell><AuthCard><StateView icon={<SuccessRing />} tone="ok" title="تم تغيير كلمة المرور بنجاح" text="يمكنك الآن تسجيل الدخول بكلمة المرور الجديدة.">
      <Btn onClick={() => nav("/auth/teacher/login")}>تسجيل الدخول</Btn></StateView></AuthCard></AuthShell>);
  return (
    <AuthShell>
      <AuthCard back={step === 0 ? "/auth/teacher/login" : undefined}>
        <Stepper total={3} current={step} />
        {step === 0 && (<>
          <Head title="استعادة كلمة المرور" sub="أدخل بيانات حسابك وسنساعدك على استعادة الوصول إليه." />
          <div className="auth-body">
            <Field label="رقم الهاتف أو البريد الإلكتروني" required><TextInput placeholder="أدخل رقم الهاتف أو البريد الإلكتروني" /></Field>
            <Btn loading={loading} loadingText="جاري الإرسال…" onClick={step2}>إرسال رمز التحقق</Btn>
            <div style={{ textAlign: "center" }}><button className="link" onClick={() => nav("/auth/teacher/login")}>العودة لتسجيل الدخول</button></div>
          </div>
        </>)}
        {step === 1 && (<>
          <Head title="تأكيد رقم الهاتف" sub="أدخل رمز التحقق المرسل إليك." />
          <div className="auth-body">
            <Otp value={otp} onChange={setOtp} />
            <Btn loading={loading} loadingText="جاري التحقق…" onClick={step2} disabled={otp.length < 6}>تأكيد</Btn>
            <Timer seconds={45} />
          </div>
        </>)}
        {step === 2 && (<>
          <Head title="إنشاء كلمة مرور جديدة" />
          <div className="auth-body">
            {err && <Banner tone="err">{err}</Banner>}
            <Field label="كلمة المرور الجديدة" required>
              <PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} placeholder="أدخل كلمة المرور الجديدة" />
              <PasswordChecklist value={pw} />
            </Field>
            <Field label="تأكيد كلمة المرور" required><PasswordInput value={pw2} onChange={(e) => setPw2(e.target.value)} placeholder="أعد إدخال كلمة المرور" /></Field>
            <Btn loading={loading} loadingText="جاري التغيير…" onClick={finish}>تغيير كلمة المرور</Btn>
          </div>
        </>)}
      </AuthCard>
    </AuthShell>
  );
}

export function TeacherEnvSelect() {
  const nav = useNavigate();
  return (
    <AuthShell><AuthCard back="/auth/teacher/login">
      <Head title="اختر بيئة العمل" sub="ادخل إلى إحدى بيئاتك التعليمية المصرّح لك بها." />
      <div className="auth-body">
        <div className="env-list">
          <EnvCard initials="٣ث" name="مجموعات الصف الثالث الثانوي" meta="العام الدراسي ٢٠٢٦ / ٢٠٢٧" last="آخر دخول: أمس" onEnter={() => nav("/auth/teacher/welcome")} />
          <EnvCard initials="٢ث" name="مجموعات الصف الثاني الثانوي" meta="العام الدراسي ٢٠٢٦ / ٢٠٢٧" last="آخر دخول: قبل ٣ أيام" onEnter={() => nav("/auth/teacher/welcome")} />
        </div>
        <p className="field-msg" style={{ justifyContent: "center", color: "var(--soft)" }}>عند وجود بيئة واحدة فقط، يتم الدخول إليها تلقائيًا.</p>
      </div>
    </AuthCard></AuthShell>
  );
}

export function TeacherWelcome() {
  const nav = useNavigate();
  return (<AuthShell><AuthCard><StateView icon={<PartyPopper size={30} />} tone="info" title="مرحبًا بك في مدار" text="لنبدأ ببناء بيئة عملك التعليمية — طلابك ومجموعاتك وجلساتك في مكان واحد.">
    <Btn onClick={() => nav("/")}>ابدأ الآن</Btn></StateView></AuthCard></AuthShell>);
}
