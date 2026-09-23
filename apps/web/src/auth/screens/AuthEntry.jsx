import { useNavigate } from "react-router-dom";
import { Users, User, ShieldCheck } from "lucide-react";
import { AuthShell, AuthCard, Head, ArrowRight } from "../ui.jsx";

export default function AuthEntry() {
  const nav = useNavigate();
  const go = (p) => () => nav(p);
  return (
    <AuthShell>
      <AuthCard>
        <Head title="أهلاً بيك في مدار" sub="منصّة بسيطة تساعد المدرّسين والطلاب على إدارة رحلتهم التعليمية." />
        <div className="choices">
          <button className="choice" onClick={go("/auth/teacher/login")}>
            <span className="ci"><Users size={24} /></span>
            <span className="choice-txt"><span className="ct">أنا مدرّس</span><span className="cd">إدارة طلابك ومتابعة رحلتهم التعليمية</span></span>
            <ArrowRight className="cg" size={18} style={{ transform: "scaleX(-1)" }} />
          </button>
          <button className="choice" onClick={go("/auth/student")}>
            <span className="ci"><User size={24} /></span>
            <span className="choice-txt"><span className="ct">أنا طالب</span><span className="cd">تابع تقدّمك وتعلّم بذكاء</span></span>
            <ArrowRight className="cg" size={18} style={{ transform: "scaleX(-1)" }} />
          </button>
        </div>
        <div className="auth-foot" style={{ textAlign: "center" }}>
          <button className="link" onClick={go("/auth/team/login")}>دخول فريق مدار</button>
        </div>
      </AuthCard>
    </AuthShell>
  );
}
