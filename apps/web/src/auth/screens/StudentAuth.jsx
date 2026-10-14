import { phoneError } from "../../lib/phone.js";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  AuthShell, AuthCard, Head, Field, TextInput, PhoneInput, PasswordInput, Btn, Banner, Otp, Timer,
  StateView, SuccessRing, EnvCard, PasswordChecklist, passwordValid, ChannelPicker, emailLooksValid,
} from "../ui.jsx";
import { authApi, envApi } from "../api.js";
import { ApiError } from "../../lib/api.js";
import { useSession } from "../../state/session.jsx";
import { useEnvironment } from "../../state/environment.jsx";

/* ---------------- Student Login (returning: phone + password) ---------------- */
export function StudentLogin() {
  const nav = useNavigate();
  const session = useSession();
  // Arriving from a successful activation: the phone is pre-filled (when the
  // student activated with it) and a short confirmation is shown.
  const { state: navState } = useLocation();
  const justActivated = !!navState?.activated;
  const [phone, setPhone] = useState(navState?.phone || ""); const [pw, setPw] = useState("");
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
        {justActivated && !err && (
          <Banner tone="info">
            تم تفعيل حسابك. سجّل الدخول برقم هاتفك{navState?.phoneHint ? ` (المنتهي بـ ${navState.phoneHint})` : ""} وكلمة المرور التي أنشأتها.
          </Banner>
        )}
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

/* ---------------- Student Claim (activate teacher-created identity) ----------------
   1. choose HOW to verify (SMS to the phone, or email) + give the contact
   2. give the STUDENT CODE the teacher handed out (proves the student exists
      and belongs to a teacher; it is checked by the server BEFORE any code is
      sent, so nothing is delivered to arbitrary numbers/addresses)
   3. enter the OTP   4. create a password   5. back to the login page. */
export function StudentClaim() {
  const nav = useNavigate();
  const [phase, setPhase] = useState("entry"); // entry | otp | setpw | success
  const [channel, setChannel] = useState("phone");
  const [phone, setPhone] = useState(""); const [email, setEmail] = useState(""); const [studentCode, setStudentCode] = useState("");
  const [otp, setOtp] = useState(""); const [otpErr, setOtpErr] = useState(null);
  const [pw, setPw] = useState(""); const [pw2, setPw2] = useState(""); const [pwErr, setPwErr] = useState(null);
  const [fe, setFe] = useState({}); const [err, setErr] = useState(null); const [loading, setLoading] = useState(false);
  const [pendingId, setPendingId] = useState(null); const [maskedTarget, setMaskedTarget] = useState("");
  const [phoneHint, setPhoneHint] = useState("");
  const offline = "تعذّر الاتصال بالخادم، حاول مرة أخرى.";

  const send = async () => {
    const f = {};
    if (channel === "phone") { const pe = phoneError(phone); if (pe) f.phone = pe; }
    else if (!emailLooksValid(email)) f.email = "أدخل بريدًا إلكترونيًا صحيحًا.";
    if (studentCode.replace(/[^a-z0-9]/gi, "").length < 4) f.studentCode = "أدخل كود الطالب الذي أعطاه لك معلّمك.";
    setFe(f); setErr(null);
    if (Object.keys(f).length) return;
    setLoading(true);
    try {
      const data = await authApi.studentClaimRequest({
        channel, student_code: studentCode.trim(),
        ...(channel === "phone" ? { phone } : { email: email.trim() }),
      });
      setPendingId(data.pending_id);
      setMaskedTarget(data.target_masked || "");
      setOtp(""); setOtpErr(null);
      setPhase("otp");
    } catch (e) {
      if (e instanceof ApiError && e.code === "email_in_use") setFe({ email: e.message });
      else setErr(e instanceof ApiError ? e.message : offline);
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
      setOtpErr(e instanceof ApiError ? e.message : offline);
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
      // Activation does NOT sign the student in: they are sent to the normal
      // login page and sign in with phone + the password just created.
      const data = await authApi.studentClaimActivate({ pending_id: pendingId, password: pw, password2: pw2 });
      setPhoneHint((data.phone_hint || "").replace(/[^0-9]/g, ""));
      setPhase("success");
    } catch (e) {
      setPwErr(e instanceof ApiError ? e.message : offline);
    } finally {
      setLoading(false);
    }
  };

  if (phase === "entry")
    return (<AuthShell><AuthCard back="/auth/student">
      <Head title="تفعيل حساب الطالب" sub="اختر وسيلة التحقق، وأدخل كود الطالب الذي أعطاه لك معلّمك في الحصة." />
      <div className="auth-body">
        {err && <Banner tone="err">{err}</Banner>}
        <ChannelPicker value={channel} onChange={(c) => { setChannel(c); setFe({}); setErr(null); }} label="كيف تريد تفعيل حسابك؟" />
        {channel === "phone"
          ? <Field label="رقم الهاتف" required error={fe.phone} hint="الرقم الذي سجّله لك معلّمك — سيصلك عليه رمز التحقق."><PhoneInput value={phone} onChange={(e) => setPhone(e.target.value)} error={fe.phone} /></Field>
          : <Field label="البريد الإلكتروني (Gmail)" required error={fe.email} hint="سيصلك رمز التحقق على هذا البريد.">
              <TextInput ltr type="email" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@gmail.com" error={fe.email} />
            </Field>}
        <Field label="كود الطالب" required error={fe.studentCode} hint="كود من ٦ خانات يعطيه لك معلّمك — يثبت أنك طالب مسجّل عنده.">
          <TextInput className="code-inp" value={studentCode} maxLength={12} autoCapitalize="characters" autoComplete="off" spellCheck={false}
            onChange={(e) => setStudentCode(e.target.value.toUpperCase())} placeholder="مثال: K7M2QX" error={fe.studentCode} />
        </Field>
        <Btn loading={loading} loadingText="جاري التحقق…" onClick={send}>إرسال رمز التحقق</Btn>
      </div>
    </AuthCard></AuthShell>);

  if (phase === "otp")
    return (<AuthShell><AuthCard>
      <Head title={channel === "email" ? "تأكيد البريد الإلكتروني" : "تأكيد رقم الهاتف"}
        sub={`أدخل رمز التحقق المرسل ${channel === "email" ? "إلى بريدك" : "برسالة SMS إلى رقمك"}${maskedTarget ? ` (${maskedTarget})` : ""}.`} />
      <div className="auth-body">
        <Otp value={otp} onChange={setOtp} error={!!otpErr} />
        {otpErr && <Banner tone="err">{otpErr}</Banner>}
        <Btn loading={loading} loadingText="جاري التحقق…" onClick={verify}>تأكيد</Btn>
        <Timer seconds={45} onResend={resend} />
        <div style={{ textAlign: "center" }}>
          <button type="button" className="link" onClick={() => { setPhase("entry"); setOtp(""); setOtpErr(null); }}>تغيير وسيلة التحقق أو البيانات</button>
        </div>
      </div>
    </AuthCard></AuthShell>);

  if (phase === "setpw")
    return (<AuthShell><AuthCard>
      <Head title="أنشئ كلمة مرور لحسابك" sub="ستدخل بها لاحقًا برقم هاتفك المسجّل في مدار." />
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

  // success -> login page (phone prefilled only when it was typed by the student)
  return (<AuthShell><AuthCard><StateView icon={<SuccessRing />} tone="ok" title="تم تفعيل حسابك بنجاح"
    text={`سجّل الدخول الآن برقم هاتفك${phoneHint ? ` (المنتهي بـ ${phoneHint})` : ""} وكلمة المرور التي أنشأتها.`}>
    <Btn onClick={() => nav("/auth/student", { replace: true, state: { activated: true, phone: channel === "phone" ? phone : "", phoneHint } })}>تسجيل الدخول</Btn>
  </StateView></AuthCard></AuthShell>);
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
