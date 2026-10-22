import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { phoneError } from "../../lib/phone.js";
import { fmtDateTime } from "../../lib/dates.js";
import { checkinApi } from "../../lib/checkinApi.js";
import { ApiError } from "../../lib/api.js";
import {
  AuthShell,
  AuthCard,
  Head,
  Field,
  PhoneInput,
  Otp,
  Btn,
  Banner,
  StateView,
  SuccessRing,
  OrbitBig,
} from "../ui.jsx";
import { CircleAlert } from "lucide-react";

/** Student self check-in. The QR the teacher shows opens this page; the student types the phone
 *  number of their Madar account and the 6-digit code the teacher announced. It can do ONE thing:
 *  record the student as present in that session. */
export function CheckinPage() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [bad, setBad] = useState(null);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [fe, setFe] = useState({});
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(null);

  useEffect(() => {
    let live = true;
    checkinApi
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

  const submit = async (e) => {
    e?.preventDefault();
    const f = {};
    const pe = phoneError(phone);
    if (pe) f.phone = pe;
    if (code.length !== 6) f.code = "أدخل الكود المكوّن من ٦ أرقام.";
    setFe(f);
    setErr(null);
    if (Object.keys(f).length) return;
    setLoading(true);
    try {
      setDone(await checkinApi.submit(token, phone, code));
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 404) setBad(e2.message);
      else setErr(e2 instanceof ApiError ? e2.message : "تعذّر الاتصال بالخادم، حاول مرة أخرى.");
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
            title="تعذّر تسجيل الحضور"
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
            title={done.result === "already" ? "حضورك مسجّل بالفعل" : "تم تسجيل حضورك"}
            text={`${done.name} — ${done.group} · ${done.environment}`}
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
        <Head
          title="تسجيل الحضور"
          sub={`${info.environment} — ${info.group} · ${fmtDateTime(info.scheduled_at)}`}
        />
        <form className="auth-body" onSubmit={submit} noValidate>
          {err && <Banner tone="err">{err}</Banner>}
          <Field
            label="رقم هاتفك على مدار"
            required
            error={fe.phone}
            hint="الرقم الذي تدخل به إلى حسابك."
          >
            <PhoneInput value={phone} onChange={(e) => setPhone(e.target.value)} error={fe.phone} />
          </Field>
          <Field
            label="كود الحصة"
            required
            error={fe.code}
            hint="٦ أرقام يعلنها المعلّم داخل الحصة."
          >
            <Otp value={code} onChange={setCode} error={fe.code} />
          </Field>
          <Btn type="submit" loading={loading} loadingText="جاري التسجيل…">
            سجّل حضوري
          </Btn>
        </form>
        <div className="auth-foot" style={{ textAlign: "center" }}>
          هذه الصفحة تسجّل حضورك فقط، ولا تتيح الاطلاع على أي بيانات.
        </div>
      </AuthCard>
    </AuthShell>
  );
}
