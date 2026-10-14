import { phoneError } from "../../lib/phone.js";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PartyPopper } from "lucide-react";
import {
  AuthShell, AuthCard, Head, Field, TextInput, PhoneInput, PasswordInput, Btn, Banner, Otp, Timer,
  Stepper, StateView, SuccessRing, EnvCard, PasswordChecklist, passwordValid, ChannelPicker,
} from "../ui.jsx";
import { authApi, envApi, fieldErrorsFrom } from "../api.js";
import { ApiError } from "../../lib/api.js";
import { useSession } from "../../state/session.jsx";
import { useEnvironment } from "../../state/environment.jsx";

const emailOk = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

export function TeacherLogin() {
  const nav = useNavigate();
  const session = useSession();
  const [id, setId] = useState(""); const [pw, setPw] = useState("");
  const [err, setErr] = useState(null); const [fe, setFe] = useState({}); const [loading, setLoading] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    const f = {};
    if (!id.trim()) f.id = "هذا الحقل مطلوب.";
    if (!pw) f.pw = "هذا الحقل مطلوب.";
    setFe(f); if (Object.keys(f).length) return;
    setErr(null); setLoading(true);
    try {
      const data = await authApi.teacherLogin(id.trim(), pw);
      session.login(data);
      nav("/auth/teacher/environments");
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر الاتصال بالخادم، حاول مرة أخرى.");
    } finally {
      setLoading(false);
    }
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
  const session = useSession();
  const [step, setStep] = useState(0); const [loading, setLoading] = useState(false);
  const [otp, setOtp] = useState(""); const [otpErr, setOtpErr] = useState(null);
  const [f, setF] = useState({ name: "", email: "", phone: "", pw: "", pw2: "", channel: "phone" });
  const [maskedTarget, setMaskedTarget] = useState("");
  const [fe, setFe] = useState({});
  const [pendingId, setPendingId] = useState(null);
  const [envForm, setEnvForm] = useState({ name: "", subject_stage: "" });
  const on = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  const validate1 = () => {
    const x = {};
    if (!f.name.trim()) x.name = "هذا الحقل مطلوب.";
    if (!emailOk(f.email)) x.email = "أدخل بريدًا إلكترونيًا صحيحًا.";
    { const pe = phoneError(f.phone); if (pe) x.phone = pe; }
    if (!passwordValid(f.pw)) x.pw = "كلمة المرور لا تحقق المتطلبات المطلوبة.";
    if (f.pw2 !== f.pw) x.pw2 = "كلمتا المرور غير متطابقتين.";
    setFe(x); return Object.keys(x).length === 0;
  };
  const next1 = async () => {
    if (!validate1()) return;
    setLoading(true);
    try {
      const data = await authApi.teacherSignupStart({
        name: f.name, email: f.email, phone: f.phone, password: f.pw, password2: f.pw2,
        otp_channel: f.channel, // "phone" (SMS) | "email" — the teacher's choice
      });
      setPendingId(data.pending_id);
      setMaskedTarget(data.target_masked || "");
      setStep(1);
    } catch (e) {
      const mapped = e instanceof ApiError ? fieldErrorsFrom(e) : null;
      setFe(mapped || { pw: e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم." });
    } finally {
      setLoading(false);
    }
  };
  const verify = async () => {
    if (otp.length < 6) { setOtpErr("أدخل الرمز المكوّن من ٦ خانات."); return; }
    setOtpErr(null); setLoading(true);
    try {
      await authApi.otpVerify("teacher-signup", pendingId, otp);
      setStep(2);
    } catch (e) {
      setOtpErr(e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم.");
    } finally {
      setLoading(false);
    }
  };
  const resend = async () => {
    try { await authApi.otpResend("teacher-signup", pendingId); } catch { /* stay on screen either way */ }
  };
  const finishEnv = async () => {
    if (!envForm.name.trim()) { setFe({ envName: "هذا الحقل مطلوب." }); return; }
    setFe({}); setLoading(true);
    try {
      const data = await authApi.teacherSignupEnvironment({
        pending_id: pendingId, name: envForm.name, subject_stage: envForm.subject_stage,
      });
      session.login(data);
      setStep(3);
    } catch (e) {
      setFe({ envName: e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم." });
    } finally {
      setLoading(false);
    }
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
            <Field label="رقم الهاتف" required error={fe.phone}><PhoneInput value={f.phone} onChange={on("phone")} error={fe.phone} /></Field>
            <Field label="كلمة المرور" required error={fe.pw}>
              <PasswordInput value={f.pw} onChange={on("pw")} placeholder="أدخل كلمة المرور" error={fe.pw} />
              <PasswordChecklist value={f.pw} />
            </Field>
            <Field label="تأكيد كلمة المرور" required error={fe.pw2}><PasswordInput value={f.pw2} onChange={on("pw2")} placeholder="أعد إدخال كلمة المرور" error={fe.pw2} /></Field>
            <ChannelPicker value={f.channel} onChange={(c) => setF((s) => ({ ...s, channel: c }))} label="أرسل رمز التحقق إلى" />
            <Btn loading={loading} loadingText="جاري المتابعة…" onClick={next1}>متابعة</Btn>
          </div>
        </>)}
        {step === 1 && (<>
          <Head title="تأكيد الحساب" sub={`أدخل رمز التحقق المرسل ${f.channel === "email" ? "إلى بريدك الإلكتروني" : "برسالة SMS إلى رقم هاتفك"}${maskedTarget ? ` (${maskedTarget})` : ""}.`} />
          <div className="auth-body">
            <Otp value={otp} onChange={setOtp} error={!!otpErr} />
            {otpErr && <Banner tone="err">{otpErr}</Banner>}
            <Btn loading={loading} loadingText="جاري التحقق…" onClick={verify}>تأكيد</Btn>
            <Timer seconds={45} onResend={resend} />
          </div>
        </>)}
        {step === 2 && (<>
          <Head title="إعداد البيئة التعليمية" sub="خطوة سريعة لتهيئة بيئتك — يمكنك تعديلها لاحقًا." />
          <div className="auth-body">
            {fe.envName && <Banner tone="err">{fe.envName}</Banner>}
            <Field label="اسم بيئتك التعليمية"><TextInput value={envForm.name} onChange={(e) => setEnvForm((s) => ({ ...s, name: e.target.value }))} placeholder="مثال: مجموعات الأستاذ أحمد" /></Field>
            <Field label="المادة أو المرحلة" hint="اختياري"><TextInput value={envForm.subject_stage} onChange={(e) => setEnvForm((s) => ({ ...s, subject_stage: e.target.value }))} placeholder="مثال: الرياضيات — الثانوية" /></Field>
            <Btn loading={loading} loadingText="جاري الإنهاء…" onClick={finishEnv}>إنهاء الإعداد</Btn>
          </div>
        </>)}
      </AuthCard>
    </AuthShell>
  );
}

export function TeacherForgot() {
  const nav = useNavigate();
  const [step, setStep] = useState(0); const [loading, setLoading] = useState(false);
  const [identifier, setIdentifier] = useState("");
  const [otp, setOtp] = useState(""); const [pw, setPw] = useState(""); const [pw2, setPw2] = useState(""); const [err, setErr] = useState(null);
  const [pendingId, setPendingId] = useState(null);

  const step1 = async () => {
    setErr(null); setLoading(true);
    try {
      const data = await authApi.teacherForgotRequest(identifier.trim());
      setPendingId(data.pending_id);
      setStep(1);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم.");
    } finally {
      setLoading(false);
    }
  };
  const step2 = async () => {
    if (otp.length < 6) { setErr("أدخل الرمز المكوّن من ٦ خانات."); return; }
    setErr(null); setLoading(true);
    try {
      await authApi.otpVerify("teacher-reset", pendingId, otp);
      setStep(2);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم.");
    } finally {
      setLoading(false);
    }
  };
  const resend = async () => {
    try { await authApi.otpResend("teacher-reset", pendingId); } catch { /* stay on screen either way */ }
  };
  const finish = async () => {
    if (!passwordValid(pw)) { setErr("كلمة المرور لا تحقق المتطلبات المطلوبة."); return; }
    if (pw !== pw2) { setErr("كلمتا المرور غير متطابقتين."); return; }
    setErr(null); setLoading(true);
    try {
      await authApi.teacherForgotReset({ pending_id: pendingId, password: pw, password2: pw2 });
      setStep(3);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم.");
    } finally {
      setLoading(false);
    }
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
            {err && <Banner tone="err">{err}</Banner>}
            <Field label="رقم الهاتف أو البريد الإلكتروني" required><TextInput value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder="أدخل رقم الهاتف أو البريد الإلكتروني" /></Field>
            <Btn loading={loading} loadingText="جاري الإرسال…" onClick={step1}>إرسال رمز التحقق</Btn>
            <div style={{ textAlign: "center" }}><button className="link" onClick={() => nav("/auth/teacher/login")}>العودة لتسجيل الدخول</button></div>
          </div>
        </>)}
        {step === 1 && (<>
          <Head title="تأكيد رقم الهاتف" sub="أدخل رمز التحقق المرسل إليك." />
          <div className="auth-body">
            {err && <Banner tone="err">{err}</Banner>}
            <Otp value={otp} onChange={setOtp} error={!!err} />
            <Btn loading={loading} loadingText="جاري التحقق…" onClick={step2} disabled={otp.length < 6}>تأكيد</Btn>
            <Timer seconds={45} onResend={resend} />
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
  const envStore = useEnvironment();
  const [envs, setEnvs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    envApi.teacherList()
      .then((data) => {
        if (!alive) return;
        if (data.length === 1) { enter(data[0]); return; }
        setEnvs(data);
      })
      .catch((e) => { if (alive) setErr(e instanceof ApiError ? e.message : "تعذّر تحميل البيئات."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const enter = async (env) => {
    try { await envApi.teacherEnter(env.id); } catch { /* proceed regardless */ }
    // envApi.teacherEnter already validated ownership server-side (the
    // request would have 404'd otherwise) — that's the authorization this
    // selection relies on, not anything decided here.
    envStore.select(env, "owner");
    nav("/app");
  };

  return (
    <AuthShell><AuthCard back="/auth/teacher/login">
      <Head title="اختر بيئة العمل" sub="ادخل إلى إحدى بيئاتك التعليمية المصرّح لك بها." />
      <div className="auth-body">
        {loading && <Banner tone="info">جاري التحميل…</Banner>}
        {err && <Banner tone="err">{err}</Banner>}
        <div className="env-list">
          {envs.map((e) => (
            <EnvCard key={e.id} initials={e.initials} name={e.name} meta={e.meta} last={e.last} onEnter={() => enter(e)} />
          ))}
        </div>
        {!loading && !err && envs.length === 0 && (
          <p className="field-msg" style={{ justifyContent: "center", color: "var(--soft)" }}>لا توجد بيئات بعد.</p>
        )}
        <p className="field-msg" style={{ justifyContent: "center", color: "var(--soft)" }}>عند وجود بيئة واحدة فقط، يتم الدخول إليها تلقائيًا.</p>
      </div>
    </AuthCard></AuthShell>
  );
}

export function TeacherWelcome() {
  const nav = useNavigate();
  // Reached right after a fresh signup — the new environment hasn't been
  // selected client-side yet (the signup response carries no environment
  // info), so route through TeacherEnvSelect: with exactly one environment
  // to choose from, it selects it automatically and lands in /app.
  return (<AuthShell><AuthCard><StateView icon={<PartyPopper size={30} />} tone="info" title="مرحبًا بك في مدار" text="لنبدأ ببناء بيئة عملك التعليمية — طلابك ومجموعاتك وجلساتك في مكان واحد.">
    <Btn onClick={() => nav("/auth/teacher/environments")}>ابدأ الآن</Btn></StateView></AuthCard></AuthShell>);
}
