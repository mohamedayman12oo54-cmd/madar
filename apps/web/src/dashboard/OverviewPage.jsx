import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  BellRing,
  CalendarClock,
  Check,
  CircleDashed,
  GraduationCap,
  ScanLine,
  Users,
  UsersRound,
  Wallet,
} from "lucide-react";
import { Banner } from "../auth/ui.jsx";
import { overviewApi } from "../lib/dashboardApi.js";
import { useSession } from "../state/session.jsx";
import { PageHeader, Empty, fmtDateTime, fmtMonth, fmtMoney, errMessage } from "./common.jsx";

const STATUS = { planned: ["مخططة", ""], open: ["مفتوحة الآن", "good"], closed: ["مغلقة", ""] };

// Counts keep Western digits: the Arabic-Indic zero is a bare dot ("٠") and reads like a rendering bug on an empty account.
const n = (v) => Number(v ?? 0).toLocaleString("en-US");

const todayLabel = () =>
  new Intl.DateTimeFormat("ar-EG", { weekday: "long", day: "numeric", month: "long" }).format(new Date());

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "صباح الخير" : h < 18 ? "مساء الخير" : "مساء النور";
}

function SessionRow({ s }) {
  const [label, tone] = STATUS[s.status] || [s.status, ""];
  return (
    <div className={"list-row session-row" + (s.status === "open" ? " is-live" : "")}>
      <div>
        <strong>{s.group}</strong>
        <div className="stat-sub">{fmtDateTime(s.scheduled_at)}</div>
      </div>
      <div className="row-actions">
        <span className={"chip-s " + tone}>{label}</span>
        {s.status !== "planned" ? (
          <Link className="mini-btn is-primary" to={`/app/attendance?session=${s.id}`}>
            الحضور والتسميع
          </Link>
        ) : (
          <Link className="mini-btn" to="/app/sessions">
            إدارة الجلسة
          </Link>
        )}
      </div>
    </div>
  );
}

function Stat({ to, icon: Icon, label, value, sub, tone }) {
  return (
    <Link to={to} className={"dash-card dash-card-btn stat-tile " + (tone || "")}>
      <div className="k">
        <Icon size={14} /> {label}
      </div>
      <div className="v">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </Link>
  );
}

/** First-run guide: appears only while a step is still open, and every step links to where it is done. */
function GettingStarted({ data }) {
  const { students, structure, sessions } = data;
  const steps = [
    { done: structure.grades > 0, label: "أنشئ صفًا دراسيًا", hint: "مثل «الصف الثالث الثانوي» مع قيمة المصروفات", to: "/app/groups" },
    { done: structure.groups > 0, label: "أنشئ مجموعة ومواعيدها", hint: "المجموعة تجمع طلابًا يحضرون معًا", to: "/app/groups" },
    { done: students.active + students.inactive > 0, label: "أضف طلابك", hint: "يدويًا أو برابط/QR تسجيل ذاتي", to: "/app/students" },
    { done: sessions.today.length + sessions.upcoming.length + sessions.open > 0, label: "جهّز أول جلسة", hint: "ولّدها من المواعيد الأسبوعية", to: "/app/sessions" },
  ];
  const doneCount = steps.filter((x) => x.done).length;
  if (doneCount === steps.length) return null;
  return (
    <section className="start-card" aria-label="ابدأ مع مدار">
      <header>
        <div>
          <h2>ابدأ مع مدار</h2>
          <p>{n(doneCount)} من {n(steps.length)} خطوات مكتملة</p>
        </div>
        <div className="progress" aria-hidden="true">
          <i style={{ width: `${(doneCount / steps.length) * 100}%` }} />
        </div>
      </header>
      <ol>
        {steps.map(({ done, label, hint, to }, i) => (
          <li key={i} className={done ? "done" : ""}>
            <Link to={to}>
              <span className="mark" aria-hidden="true">{done ? <Check size={15} /> : <CircleDashed size={15} />}</span>
              <span>
                <b>{label}</b>
                <small>{hint}</small>
              </span>
              {!done && <ArrowLeft size={16} aria-hidden="true" />}
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default function OverviewPage() {
  const { user } = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    overviewApi
      .get()
      .then(setData)
      .catch((e) => setError(errMessage(e, "تعذّر تحميل النظرة العامة.")));
  }, []);

  if (error)
    return (
      <>
        <PageHeader infoKey="overview" title="نظرة عامة" />
        <Banner tone="err">{error}</Banner>
      </>
    );
  if (!data)
    return (
      <>
        <PageHeader infoKey="overview" title="نظرة عامة" />
        <div className="dash-skel" role="status" aria-label="جاري تحميل البيانات">
          <i /><i /><i /><i />
        </div>
      </>
    );

  const { students, structure, sessions, payments, notifications } = data;
  const pct = payments.students ? Math.round((payments.paid / payments.students) * 100) : 0;
  const first = (user?.name || "").trim().split(/\s+/).slice(0, 2).join(" ");

  return (
    <>
      <PageHeader infoKey="overview" title="نظرة عامة" />
      <section className="ov-hero">
        <div>
          <p className="ov-hero-date">{todayLabel()}</p>
          <h2>
            {greeting()}
            {first ? `، ${first}` : ""}
          </h2>
          <p className="ov-hero-sub">{data.environment.name}</p>
        </div>
        <div className="ov-hero-actions">
          {sessions.open > 0 ? (
            <Link className="abtn abtn-primary" to="/app/sessions">
              <CalendarClock size={17} /> {sessions.open === 1 ? "جلسة مفتوحة الآن" : `${n(sessions.open)} جلسات مفتوحة الآن`}
            </Link>
          ) : (
            <Link className="abtn abtn-primary" to="/app/sessions">
              <CalendarClock size={17} /> الجلسات
            </Link>
          )}
          <Link className="abtn abtn-secondary" to="/app/scan">
            <ScanLine size={17} /> مسح رمز طالب
          </Link>
        </div>
      </section>

      <GettingStarted data={data} />

      <div className="dash-cards stat-grid">
        <Stat to="/app/students" icon={Users} label="طلاب نشطون" value={n(students.active)} sub={`${n(students.inactive)} غير نشط`} />
        <Stat to="/app/groups" icon={GraduationCap} label="الصفوف" value={n(structure.grades)} />
        <Stat to="/app/groups" icon={UsersRound} label="المجموعات" value={n(structure.groups)} />
        <Stat to="/app/sessions" icon={CalendarClock} label="جلسات مفتوحة الآن" value={n(sessions.open)} tone={sessions.open ? "live" : ""} />
      </div>

      <div className="overview-cols">
        <div>
          <div className="dash-section-head">
            <h2>جلسات اليوم</h2>
            <Link className="mini-btn" to="/app/sessions">كل الجلسات</Link>
          </div>
          {sessions.today.length === 0 ? (
            <Empty title="لا توجد جلسات اليوم" text="يمكنك توليد جلسات من المواعيد الأسبوعية من صفحة الجلسات." />
          ) : (
            <div className="list-rows">
              {sessions.today.map((s) => (
                <SessionRow key={s.id} s={s} />
              ))}
            </div>
          )}

          {sessions.upcoming.length > 0 && (
            <>
              <div className="dash-section-head" style={{ marginBlockStart: 24 }}>
                <h2>الجلسات القادمة</h2>
              </div>
              <div className="list-rows">
                {sessions.upcoming.map((s) => (
                  <SessionRow key={s.id} s={s} />
                ))}
              </div>
            </>
          )}
        </div>

        <aside className="overview-side">
          <Link to="/app/financials" className="dash-card dash-card-btn">
            <div className="k">
              <Wallet size={14} /> مدفوعات {fmtMonth(payments.month)}
            </div>
            <div className="v">{fmtMoney(payments.collected_total)}</div>
            <div className="stat-sub">
              من {fmtMoney(payments.expected_total)} — المتبقي {fmtMoney(payments.outstanding_total)}
            </div>
            <div className="progress" aria-label={`${pct}% دفعوا`}>
              <i style={{ width: `${pct}%` }} />
            </div>
            <div className="stat-sub">
              {n(payments.paid)} من {n(payments.students)} دفعوا
            </div>
          </Link>
          <Link to="/app/notifications" className={"dash-card dash-card-btn" + (notifications.failed ? " needs-care" : "")}>
            <div className="k">
              <BellRing size={14} /> الإشعارات
            </div>
            <div className="v">{n(notifications.failed)}</div>
            <div className="stat-sub">فشل إرسالها • {n(notifications.pending)} قيد الإرسال</div>
          </Link>
        </aside>
      </div>
    </>
  );
}
