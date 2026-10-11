import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { phoneError } from "../../lib/phone.js";
import { AuthShell, AuthCard, Head, Field, PhoneInput, Btn, Banner, Otp, Timer } from "../ui.jsx";
import { ApiError } from "../../lib/api.js";
import { parentApi, saveParentSession } from "../../lib/parentApi.js";

/** Guardian sign-in: the phone number the teacher recorded for the student, then
 *  a code sent to it. No password and no account to activate — it works as soon
 *  as the student has activated their own account. */
export function ParentLogin() {
  const nav = useNavigate();
  const [phase, setPhase] = useState("entry"); // entry | otp
  const [phone, setPhone] = useState(""); const [otp, setOtp] = useState("");
  const [pendingId, setPendingId] = useState(null);
  const [fe, setFe] = useState({}); const [err, setErr] = useState(null); const [loading, setLoading] = useState(false);
  const msg = (e) => (e instanceof ApiError ? e.message : "تعذّر الاتصال بالخادم، حاول مرة أخرى.");

  const send = async (e) => {
    e?.preventDefault();
    const pe = phoneError(phone);
    if (pe) { setFe({ phone: pe }); return; }
    setFe({}); setErr(null); setLoading(true);
    try {
      const data = await parentApi.request(phone);
      setPendingId(data.pending_id);
      setPhase("otp");
    } catch (e2) {
      setErr(msg(e2));
    } finally { setLoading(false); }
  };

  const verify = async () => {
    if (otp.length < 6) { setErr("أدخل الرمز المكوّن من ٦ خانات."); return; }
    setErr(null); setLoading(true);
    try {
      await parentApi.otpVerify(pendingId, otp);
      const data = await parentApi.verify(pendingId);
      saveParentSession(data);
      nav("/parent", { replace: true });
    } catch (e2) {
      setErr(msg(e2));
    } finally { setLoading(false); }
  };

  const resend = async () => { try { await parentApi.otpResend(pendingId); } catch { /* stay on screen either way */ } };

  if (phase === "otp")
    return (<AuthShell><AuthCard back>
      <Head title="تأكيد رقم الهاتف" sub="أدخل رمز التحقق المرسل إلى رقم هاتفك المسجّل لدى المدرّس." />
      <div className="auth-body">
        <Otp value={otp} onChange={setOtp} error={!!err} />
        {err && <Banner tone="err">{err}</Banner>}
        <Btn loading={loading} loadingText="جاري التحقق…" onClick={verify}>تأكيد</Btn>
        <Timer seconds={45} onResend={resend} />
      </div>
    </AuthCard></AuthShell>);

  return (
    <AuthShell><AuthCard back="/auth">
      <Head title="دخول ولي الأمر" sub="ادخل برقم هاتفك المسجّل لدى المدرّس لمتابعة حضور ابنك وتسميعه ومدفوعاته وتقييمه. لا تحتاج إلى إنشاء حساب." />
      <form className="auth-body" onSubmit={send} noValidate>
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="رقم هاتف ولي الأمر" required error={fe.phone} hint="الرقم الذي سجّله المدرّس عند إضافة الطالب.">
          <PhoneInput value={phone} onChange={(e) => setPhone(e.target.value)} error={fe.phone} />
        </Field>
        <Btn type="submit" loading={loading} loadingText="جاري الإرسال…">إرسال رمز التحقق</Btn>
      </form>
      <div className="auth-foot" style={{ textAlign: "center" }}>
        المتابعة تتاح بعد أن يفعّل الطالب حسابه على مدار.
      </div>
    </AuthCard></AuthShell>
  );
}
