import { useParams, useNavigate, Link } from "react-router-dom";
import {
  AlertTriangle,
  SearchX,
  Clock,
  ShieldAlert,
  WifiOff,
  ServerCrash,
  TimerReset,
  PartyPopper,
  Lock,
} from "lucide-react";
import { AuthShell, AuthCard, StateView, SuccessRing, Btn, Modal, OrbitBig } from "../ui.jsx";
import { useSession } from "../../state/session.jsx";

const STATES = {
  "invalid-credentials": {
    tone: "err",
    icon: <AlertTriangle size={30} />,
    title: "بيانات الدخول غير صحيحة",
    text: "تأكّد من رقم الهاتف/البريد وكلمة المرور وحاول مرة أخرى.",
    cta: ["تسجيل الدخول", "/auth/teacher/login"],
  },
  "account-not-found": {
    tone: "err",
    icon: <SearchX size={30} />,
    title: "لم نعثر على هذا الحساب",
    text: "لا يوجد حساب مرتبط بوسيلة الاتصال هذه.",
    cta: ["إنشاء حساب مدرّس", "/auth/teacher/signup"],
  },
  "verification-failed": {
    tone: "err",
    icon: <AlertTriangle size={30} />,
    title: "تعذّر التحقق",
    text: "الرمز الذي أدخلته غير صحيح. تأكّد وحاول مجددًا.",
    cta: ["المحاولة مرة أخرى", "/auth/teacher/login"],
  },
  "verification-expired": {
    tone: "err",
    icon: <Clock size={30} />,
    title: "انتهت صلاحية الرمز",
    text: "انتهت مدة صلاحية رمز التحقق. اطلب رمزًا جديدًا.",
    cta: ["طلب رمز جديد", "/auth/teacher/login"],
  },
  "too-many-attempts": {
    tone: "err",
    icon: <ShieldAlert size={30} />,
    title: "محاولات كثيرة",
    text: "لأمان حسابك، يرجى المحاولة بعد قليل.",
    cta: ["حسنًا", "/auth"],
  },
  "network-error": {
    tone: "err",
    icon: <WifiOff size={30} />,
    title: "لا يوجد اتصال",
    text: "تعذّر الوصول إلى مدار. تحقّق من اتصالك بالإنترنت.",
    cta: ["إعادة المحاولة", "/auth"],
  },
  "server-error": {
    tone: "err",
    icon: <ServerCrash size={30} />,
    title: "حدث خطأ ما",
    text: "نعمل على حلّ المشكلة. يرجى المحاولة بعد قليل.",
    cta: ["إعادة المحاولة", "/auth"],
  },
  "session-expired": {
    tone: "info",
    icon: <TimerReset size={30} />,
    title: "انتهت جلستك",
    text: "لأمان حسابك، يرجى تسجيل الدخول مرة أخرى.",
    cta: ["تسجيل الدخول", "/auth"],
  },
  unauthorized: {
    tone: "err",
    icon: <Lock size={30} />,
    title: "لا تملك صلاحية الوصول",
    text: "حسابك لا يملك صلاحية الوصول إلى هذه الصفحة.",
    cta: ["العودة", "/auth"],
  },
  "student-not-found": {
    tone: "err",
    icon: <SearchX size={30} />,
    title: "لم نجد حساب طالب بهذا الرقم",
    text: "تأكّد من استخدام الرقم الذي سجّله لك مدرّسك.",
    cta: ["المحاولة مرة أخرى", "/auth/student"],
  },
  "registration-success": {
    tone: "ok",
    ring: true,
    title: "تم إنشاء حسابك بنجاح",
    text: "مرحبًا بك في مدار — بيئتك جاهزة للبدء.",
    cta: ["الدخول إلى مدار", "/auth/teacher/welcome"],
  },
  "password-reset-success": {
    tone: "ok",
    ring: true,
    title: "تم تحديث كلمة المرور",
    text: "يمكنك الآن تسجيل الدخول بكلمة المرور الجديدة.",
    cta: ["تسجيل الدخول", "/auth/teacher/login"],
  },
  "claim-success": {
    tone: "ok",
    ring: true,
    title: "أهلًا بك في مدار",
    text: "تم تفعيل حسابك بنجاح. تابع رحلتك التعليمية.",
    cta: ["المتابعة", "/auth/student/environments"],
  },
  "teacher-empty": {
    tone: "info",
    icon: <PartyPopper size={30} />,
    title: "مرحبًا بك في مدار",
    text: "لنبدأ ببناء بيئة عملك التعليمية.",
    cta: ["ابدأ الآن", "/"],
  },
};

export function AuthStateScreen() {
  const { key } = useParams();
  const nav = useNavigate();
  const s = STATES[key];
  if (!s)
    return (
      <AuthShell>
        <AuthCard>
          <StateView
            tone="err"
            icon={<AlertTriangle size={30} />}
            title="حالة غير معروفة"
            text="هذه الحالة غير مُعرّفة في النموذج."
          >
            <Btn onClick={() => nav("/auth/all")}>العودة إلى الفهرس</Btn>
          </StateView>
        </AuthCard>
      </AuthShell>
    );
  return (
    <AuthShell>
      <AuthCard>
        <StateView
          tone={s.tone}
          icon={s.ring ? <SuccessRing /> : s.icon}
          title={s.title}
          text={s.text}
        >
          <Btn onClick={() => nav(s.cta[1])}>{s.cta[0]}</Btn>
        </StateView>
      </AuthCard>
    </AuthShell>
  );
}

export function LogoutConfirm() {
  const nav = useNavigate();
  const { logout } = useSession(); // the session store must hear about it, or the app still thinks you are in
  const doLogout = async () => {
    await logout();
    nav("/auth", { replace: true });
  };
  return (
    <AuthShell>
      <Modal title="تسجيل الخروج؟" text="هل تريد تسجيل الخروج من حسابك؟" onClose={() => nav(-1)}>
        <Btn onClick={doLogout}>تسجيل الخروج</Btn>
        <Btn variant="ghost" onClick={() => nav(-1)}>
          إلغاء
        </Btn>
      </Modal>
    </AuthShell>
  );
}

export function LoadingDemo() {
  return (
    <AuthShell>
      <AuthCard>
        <div className="state">
          <div style={{ display: "grid", placeItems: "center", padding: "10px 0" }}>
            <OrbitBig />
          </div>
          <div className="state-t">جارٍ التحقّق…</div>
          <div className="state-x">لحظات ونكمل الدخول إلى مدار.</div>
        </div>
      </AuthCard>
    </AuthShell>
  );
}

/* ---------------- Gallery / screen index ---------------- */
const GROUPS = [
  {
    h: "عام",
    items: [
      ["الدخول", "/auth"],
      ["فهرس الشاشات", "/auth/all"],
      ["تحميل", "/auth/loading"],
      ["تأكيد الخروج", "/auth/logout"],
    ],
  },
  {
    h: "المدرّس",
    items: [
      ["تسجيل الدخول", "/auth/teacher/login"],
      ["إنشاء حساب", "/auth/teacher/signup"],
      ["استعادة كلمة المرور", "/auth/teacher/forgot"],
      ["اختيار البيئة", "/auth/teacher/environments"],
      ["بيئة جديدة", "/auth/teacher/welcome"],
    ],
  },
  {
    h: "الطالب",
    items: [
      ["تسجيل الدخول", "/auth/student"],
      ["تفعيل الحساب", "/auth/student/claim"],
      ["استعادة كلمة المرور", "/auth/student/forgot"],
      ["اختيار المعلّم", "/auth/student/environments"],
    ],
  },
  { h: "فريق مدار", items: [["دخول الفريق", "/auth/team/login"]] },
  {
    h: "حالات النجاح",
    items: [
      ["إنشاء الحساب", "/auth/state/registration-success"],
      ["تفعيل الطالب", "/auth/state/claim-success"],
      ["تحديث كلمة المرور", "/auth/state/password-reset-success"],
    ],
  },
  {
    h: "حالات الخطأ",
    items: [
      ["بيانات غير صحيحة", "/auth/state/invalid-credentials"],
      ["حساب غير موجود", "/auth/state/account-not-found"],
      ["فشل التحقق", "/auth/state/verification-failed"],
      ["انتهاء الرمز", "/auth/state/verification-expired"],
      ["محاولات كثيرة", "/auth/state/too-many-attempts"],
      ["لا يوجد اتصال", "/auth/state/network-error"],
      ["خطأ في الخادم", "/auth/state/server-error"],
      ["انتهاء الجلسة", "/auth/state/session-expired"],
      ["غير مصرّح بالوصول", "/auth/state/unauthorized"],
      ["طالب غير موجود", "/auth/state/student-not-found"],
    ],
  },
];

export function AuthGallery() {
  return (
    <div className="auth">
      <div className="gallery">
        <h1>نظام المصادقة — مدار</h1>
        <p>فهرس كامل لكل شاشات وحالات الدخول والتفعيل. اضغط أي شاشة لمعاينتها.</p>
        {GROUPS.map((g, i) => (
          <div className="gal-group" key={i}>
            <h2>{g.h}</h2>
            <div className="gal-grid">
              {g.items.map(([label, to]) => (
                <Link key={to} to={to}>
                  {label}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
