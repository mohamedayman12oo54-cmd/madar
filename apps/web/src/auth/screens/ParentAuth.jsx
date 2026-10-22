import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { phoneError } from "../../lib/phone.js";
import { AuthShell, AuthCard, Head, Field, TextInput, PhoneInput, Btn, Banner } from "../ui.jsx";
import { ApiError } from "../../lib/api.js";
import { parentApi, saveParentSession } from "../../lib/parentApi.js";

/** Guardian sign-in: the phone number the teacher recorded for the guardian plus
 *  the student code of the child. No password, no OTP and no account to activate
 *  — it works as soon as the child has activated their own account. */
export function ParentLogin() {
  const nav = useNavigate();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [fe, setFe] = useState({});
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e?.preventDefault();
    const f = {};
    const pe = phoneError(phone);
    if (pe) f.phone = pe;
    if (code.replace(/[^a-z0-9]/gi, "").length < 4) f.code = "أدخل كود الطالب الخاص بابنك.";
    setFe(f);
    setErr(null);
    if (Object.keys(f).length) return;
    setLoading(true);
    try {
      const data = await parentApi.login(phone, code.trim());
      saveParentSession(data);
      nav("/parent", { replace: true });
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر الاتصال بالخادم، حاول مرة أخرى.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell>
      <AuthCard back="/auth">
        <Head
          title="دخول ولي الأمر"
          sub="ادخل برقم هاتفك المسجّل لدى المدرّس وكود الطالب الخاص بابنك لمتابعة حضوره وتسميعه ومدفوعاته وتقييمه."
        />
        <form className="auth-body" onSubmit={submit} noValidate>
          {err && <Banner tone="err">{err}</Banner>}
          <Field
            label="رقم هاتف ولي الأمر"
            required
            error={fe.phone}
            hint="الرقم الذي سجّله المدرّس عند إضافة الطالب."
          >
            <PhoneInput value={phone} onChange={(e) => setPhone(e.target.value)} error={fe.phone} />
          </Field>
          <Field
            label="كود الطالب"
            required
            error={fe.code}
            hint="كود من ٦ خانات مع ابنك — نفس الكود الذي يفعّل به حسابه."
          >
            <TextInput
              className="code-inp"
              value={code}
              maxLength={12}
              autoCapitalize="characters"
              autoComplete="off"
              spellCheck={false}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="مثال: K7M2QX"
              error={fe.code}
            />
          </Field>
          <Btn type="submit" loading={loading} loadingText="جاري الدخول…">
            دخول
          </Btn>
        </form>
        <div className="auth-foot" style={{ textAlign: "center" }}>
          المتابعة تتاح بعد أن يفعّل الطالب حسابه على مدار.
        </div>
      </AuthCard>
    </AuthShell>
  );
}
