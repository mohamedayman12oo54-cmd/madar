import { phoneError } from "../../lib/phone.js";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SearchX } from "lucide-react";
import {
  AuthShell, AuthCard, Head, Field, PhoneInput, PasswordInput, Btn, Banner, Otp, Timer,
  StateView, SuccessRing, EnvCard, PasswordChecklist, passwordValid,
} from "../ui.jsx";
import { authApi, envApi } from "../api.js";
import { ApiError } from "../../lib/api.js";
import { useSession } from "../../state/session.jsx";
import { useEnvironment } from "../../state/environment.jsx";

/* ---------------- Student Login (returning: phone + password) ---------------- */
export function StudentLogin() {
  const nav = useNavigate();
  const session = useSession();
  const [phone, setPhone] = useState(""); const [pw, setPw] = useState("");
  const [fe, setFe] = useState({}); const [err, setErr] = useState(null); const [loading, setLoading] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    const f = {};
    { const pe = phoneError(phone); if (pe) f.phone = pe; }
    if (!pw) f.pw = "هذا الحقل مطلوب.";
    setFe(f); if (Object.keys(f).length) return;
    setErr(null); setLoading(true);
    try {
      const data = await authApi.studentLogin(phone, pw);
      // session.login (not the bare token saver): it also updates the in-memory
      // session, otherwise ProtectedRoute still sees "anonymous" and bounces
      // the student straight back to this login page.
      session.login(data);
      nav("/auth/student/environments");
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر الاتصال بالخادم، حاول مرة أخرى.");
    } finally {
      setLoading(false);
    }
  };
  return (
    <AuthShell><AuthCard back="/auth">
      <Head title="تسجيل دخول الطالب" sub="ادخل إلى حسابك لمتابعة رحلتك التعليمية." />
      <form className="auth-body" onSubmit={submit} noValidate>
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="رقم الهاتف" required error={fe.phone}><PhoneInput value={phone} onChange={(e) => setPhone(e.target.value)} error={fe.phone} /></Field>
        <Field label="كلمة المرور" required error={fe.pw}><PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} placeholder="أدخل كلمة المرور" error={fe.pw} /></Field>
        <div style={{ marginBlockStart: -6 }}><button type="button" className="link" onClick={() => nav("/auth/student/forgot")}>نسيت كلمة المرور؟</button></div>
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
  const session = useSession();
  const [phase, setPhase] = useState("entry"); // entry | otp | setpw | success | notfound
  const [phone, setPhone] = useState(""); const [otp, setOtp] = useState(""); const [otpErr, setOtpErr] = useState(null);
  const [pw, setPw] = useState(""); const [pw2, setPw2] = useState(""); const [pwErr, setPwErr] = useState(null);
  const [fe, setFe] = useState({}); const [loading, setLoading] = useState(false);
  const [pendingId, setPendingId] = useState(null);

  const send = async () => {
    { const pe = phoneError(phone); if (pe) { setFe({ phone: pe }); return; } }
    setFe({}); setLoading(true);
    try {
      const data = await authApi.studentClaimRequest(phone);
      setPendingId(data.pending_id);
      setPhase("otp");
    } catch (e) {
      if (e instanceof ApiError && e.code === "not_found") { setPhase("notfound"); return; }
      setFe({ phone: e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم." });
    } finally {
      setLoading(false);
    }
  };
  const verify = async () => {
    if (otp.length < 6) { setOtpErr("أدخل الرمز المكوّن من ٦ خانات."); return; }
    setOtpErr(null); setLoading(true);
    try {
      await authApi.otpVerify("student-claim", pendingId, otp);
      setPhase("setpw");
    } catch (e) {
      setOtpErr(e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم.");
    } finally {
      setLoading(false);
    }
  };
  const resend = async () => {
    try { await authApi.otpResend("student-claim", pendingId); } catch { /* stay on screen either way */ }
  };
  const finish = async () => {
    if (!passwordValid(pw)) { setPwErr("كلمة المرور لا تحقق المتطلبات المطلوبة."); return; }
    if (pw !== pw2) { setPwErr("كلمتا المرور غير متطابقتين."); return; }
    setPwErr(null); setLoading(true);
    try {
      const data = await authApi.studentClaimActivate({ pending_id: pendingId, password: pw, password2: pw2 });
      session.login(data);
      setPhase("success");
    } catch (e) {
      setPwErr(e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم.");
    } finally {
      setLoading(false);
    }
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
        <Timer seconds={45} onResend={resend} />
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

/* ---------------- Student Forgot Password ---------------- */
export function StudentForgot() {
  const nav = useNavigate();
  const [step, setStep] = useState(0); const [loading, setLoading] = useState(false);
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState(""); const [pw, setPw] = useState(""); const [pw2, setPw2] = useState(""); const [err, setErr] = useState(null);
  const [pendingId, setPendingId] = useState(null);

  const step1 = async () => {
    { const pe = phoneError(phone); if (pe) { setErr(pe); return; } }
    setErr(null); setLoading(true);
    try {
      const data = await authApi.studentForgotRequest(phone);
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
      await authApi.otpVerify("student-reset", pendingId, otp);
      setStep(2);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم.");
    } finally {
      setLoading(false);
    }
  };
  const resend = async () => {
    try { await authApi.otpResend("student-reset", pendingId); } catch { /* stay on screen either way */ }
  };
  const finish = async () => {
    if (!passwordValid(pw)) { setErr("كلمة المرور لا تحقق المتطلبات المطلوبة."); return; }
    if (pw !== pw2) { setErr("كلمتا المرور غير متطابقتين."); return; }
    setErr(null); setLoading(true);
    try {
      await authApi.studentForgotReset({ pending_id: pendingId, password: pw, password2: pw2 });
      setStep(3);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم.");
    } finally {
      setLoading(false);
    }
  };
  if (step === 3)
    return (<AuthShell><AuthCard><StateView icon={<SuccessRing />} tone="ok" title="تم تغيير كلمة المرور بنجاح" text="يمكنك الآن تسجيل الدخول بكلمة المرور الجديدة.">
      <Btn onClick={() => nav("/auth/student")}>تسجيل الدخول</Btn></StateView></AuthCard></AuthShell>);
  return (
    <AuthShell>
      <AuthCard back={step === 0 ? "/auth/student" : undefined}>
        {step === 0 && (<>
          <Head title="استعادة كلمة المرور" sub="أدخل رقم هاتفك وسنساعدك على استعادة الوصول إلى حسابك." />
          <div className="auth-body">
            {err && <Banner tone="err">{err}</Banner>}
            <Field label="رقم الهاتف" required><PhoneInput value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
            <Btn loading={loading} loadingText="جاري الإرسال…" onClick={step1}>إرسال رمز التحقق</Btn>
            <div style={{ textAlign: "center" }}><button className="link" onClick={() => nav("/auth/student")}>العودة لتسجيل الدخول</button></div>
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

export function StudentEnvSelect() {
  const nav = useNavigate();
  const envStore = useEnvironment();
  const [envs, setEnvs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    envApi.studentList()
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
    try {
      await envApi.studentEnter(env.id); // server validates the student really belongs here
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setErr("هذه البيئة لم تعد متاحة لحسابك. تواصل مع معلّمك.");
        return;
      }
      // network hiccup: fall through — the route guard re-checks server-side
    }
    // Without this the environment store stays "none" and ProtectedRoute
    // sends the student back here forever.
    envStore.select(env, "student");
    nav("/learn", { replace: true });
  };

  return (<AuthShell><AuthCard>
    <Head title="اختر بيئة التعلّم" sub="لديك أكثر من معلّم — اختر البيئة التي تريد الدخول إليها." />
    <div className="auth-body">
      {loading && <Banner tone="info">جاري التحميل…</Banner>}
      {err && <Banner tone="err">{err}</Banner>}
      <div className="env-list">
        {envs.map((e) => (
          <EnvCard key={e.id} initials={e.initials} name={e.name} meta={e.meta} last={e.last} onEnter={() => enter(e)} />
        ))}
      </div>
      {!loading && !err && envs.length === 0 && (
        <p className="field-msg" style={{ justifyContent: "center", color: "var(--soft)" }}>لا توجد بيئات مرتبطة بحسابك بعد.</p>
      )}
      <p className="field-msg" style={{ justifyContent: "center", color: "var(--soft)" }}>تعمل ضمن بيئة واحدة في كل مرة — لا تُدمج بيانات المعلّمين مطلقًا.</p>
    </div>
  </AuthCard></AuthShell>);
}
