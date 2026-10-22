import { Link } from "react-router-dom";
import { useSession } from "../state/session.jsx";
import { formatPhone } from "../lib/phone.js";
import { Field, TextInput } from "../auth/ui.jsx";
import { PageHeader } from "../dashboard/common.jsx";
import { SecuritySection } from "../dashboard/SettingsPage.jsx";

export default function SettingsPage() {
  const { user } = useSession();
  return (
    <>
      <PageHeader infoKey="student_settings" title="الإعدادات" />
      <section className="dash-card" style={{ marginBlockEnd: 18 }}>
        <h3 style={{ marginBlockEnd: 12 }}>حسابي</h3>
        <Field label="الاسم" hint="يحدده معلمك. لتصحيحه كلّم معلمك.">
          <TextInput value={user?.name || ""} disabled readOnly />
        </Field>
        <Field label="رقم الهاتف" hint="هوية دخولك — لا يمكن تغييره من هنا.">
          <TextInput ltr value={user?.phone ? formatPhone(user.phone) : ""} disabled readOnly />
        </Field>
        <p className="stat-sub" style={{ marginBlockStart: 10 }}>
          لديك أكثر من معلم؟{" "}
          <Link className="dash-linkish" to="/auth/student/environments">
            بدّل المعلم
          </Link>
        </p>
      </section>
      <SecuritySection loginPath="/auth/student" />
    </>
  );
}
