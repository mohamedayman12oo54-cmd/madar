// Phase 1: no domain data exists yet (Grade/Group/Session/... are Phase 2+),
// so this deliberately shows nothing fabricated — real numbers (student
// count, today's sessions, attendance, payments, ...) replace this section
// by section as their backend endpoints land, per the "never calculate
// security-sensitive information only on the client / never fake dashboard
// statistics" requirement.
import { useSession } from "../state/session.jsx";
import { useEnvironment } from "../state/environment.jsx";
import ComingSoon from "./ComingSoon.jsx";

export default function OverviewPage() {
  const { user } = useSession();
  const env = useEnvironment();

  return (
    <>
      <div className="dash-empty" style={{ margin: "0 0 26px", maxWidth: "none", textAlign: "start", alignItems: "flex-start" }}>
        <h2 style={{ marginBottom: 0 }}>مرحبًا، {user?.name || "معلّم مدار"} 👋</h2>
        <p style={{ margin: 0 }}>
          أنت الآن داخل بيئة <strong style={{ color: "var(--navy)" }}>{env.environment?.name}</strong>.
          ستظهر هنا نظرة عامة حقيقية على طلابك ومجموعاتك وجلساتك ومدفوعاتك بمجرد ربطها بالواجهة الخلفية.
        </p>
      </div>
      <ComingSoon
        title="النظرة العامة قادمة قريبًا"
        text="عدد الطلاب، المجموعات النشطة، جلسات اليوم، والحضور والمدفوعات ستُعرض هنا بمجرد اكتمال البيانات الفعلية في الواجهة الخلفية — لن نعرض أرقامًا وهمية."
      />
    </>
  );
}
