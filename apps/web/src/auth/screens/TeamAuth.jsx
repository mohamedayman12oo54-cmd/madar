import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { AuthShell, AuthCard, Head, Field, TextInput, PasswordInput, Btn, Banner } from "../ui.jsx";

export function TeamLogin() {
  const nav = useNavigate();
  const [id, setId] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    if (!id.trim() || !pw) { setErr("أدخل بيانات الدخول للمتابعة."); return; }
    setErr(null); setLoading(true);
    setTimeout(() => {
      setLoading(false);
      if (pw === "wrong") { setErr("بيانات الدخول غير صحيحة، حاول مرة أخرى."); return; }
      nav("/"); // → Knowledge Base / Content Management (خارج نطاق هذا النموذج)
    }, 1000);
  };
  return (
    <AuthShell>
      <AuthCard back="/auth">
        <div style={{ display: "flex", justifyContent: "center", marginBlockEnd: "10px" }}>
          <span className="ci" style={{ width: 44, height: 44, borderRadius: 13, background: "var(--fill)", color: "var(--navy)", display: "grid", placeItems: "center" }}>
            <ShieldCheck size={22} />
          </span>
        </div>
        <Head title="دخول فريق مدار" sub="إدارة المحتوى والمعرفة" />
        <form className="auth-body" onSubmit={submit} noValidate>
          {err && <Banner tone="err">{err}</Banner>}
          <Field label="معرّف الدخول"><TextInput ltr value={id} onChange={(e) => setId(e.target.value)} placeholder="team@madar" /></Field>
          <Field label="كلمة المرور"><PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} placeholder="••••••••" /></Field>
          <Btn type="submit" loading={loading} loadingText="جاري تسجيل الدخول…">تسجيل الدخول</Btn>
          <p className="pw-hint" style={{ textAlign: "center" }}>
            دخول داخلي — لا يتيح الوصول إلى سجلات المعلّمين أو الطلاب.
          </p>
        </form>
      </AuthCard>
    </AuthShell>
  );
}
