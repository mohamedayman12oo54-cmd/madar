import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Users, UsersRound, GraduationCap, CalendarClock, Wallet, BellRing } from "lucide-react";
import { Banner } from "../auth/ui.jsx";
import { overviewApi } from "../lib/dashboardApi.js";
import { PageHeader, Empty, fmtDateTime, fmtMonth, fmtMoney, errMessage } from "./common.jsx";

const STATUS = { planned: "مخططة", open: "مفتوحة", closed: "مغلقة" };

function SessionRow({ s }) {
  return (
    <div className="list-row">
      <div>
        <strong>{s.group}</strong>
        <div className="stat-sub">{fmtDateTime(s.scheduled_at)}</div>
      </div>
      <div className="row-actions">
        <span className="chip-s">{STATUS[s.status]}</span>
        {s.status !== "planned" ? (
          <Link className="mini-btn" to={`/app/attendance?session=${s.id}`}>
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

export default function OverviewPage() {
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
        <p className="field-msg">جاري تحميل البيانات...</p>
      </>
    );

  const { students, structure, sessions, payments, notifications } = data;
  const pct = payments.students ? Math.round((payments.paid / payments.students) * 100) : 0;

  return (
    <>
      <PageHeader infoKey="overview" title="نظرة عامة" sub={data.environment.name} />
      {structure.grades === 0 && (
        <div className="dash-note">
          ابدأ من صفحة{" "}
          <Link className="dash-linkish" to="/app/groups">
            المجموعات
          </Link>
          : أنشئ صفًا دراسيًا ثم مجموعة، وبعدها أضف طلابك من صفحة{" "}
          <Link className="dash-linkish" to="/app/students">
            الطلاب
          </Link>
          .
        </div>
      )}
      <div className="dash-cards">
        <Link to="/app/students" className="dash-card dash-card-btn">
          <div className="k">
            <Users size={14} /> طلاب نشطون
          </div>
          <div className="v">{students.active}</div>
          <div className="stat-sub">{students.inactive} غير نشط</div>
        </Link>
        <Link to="/app/groups" className="dash-card dash-card-btn">
          <div className="k">
            <GraduationCap size={14} /> الصفوف
          </div>
          <div className="v">{structure.grades}</div>
        </Link>
        <Link to="/app/groups" className="dash-card dash-card-btn">
          <div className="k">
            <UsersRound size={14} /> المجموعات
          </div>
          <div className="v">{structure.groups}</div>
        </Link>
        <Link to="/app/sessions" className="dash-card dash-card-btn">
          <div className="k">
            <CalendarClock size={14} /> جلسات مفتوحة الآن
          </div>
          <div className="v">{sessions.open}</div>
        </Link>
      </div>

      <div className="dash-section-head">
        <h2>جلسات اليوم</h2>
      </div>
      {sessions.today.length === 0 ? (
        <Empty
          title="لا توجد جلسات اليوم"
          text="يمكنك توليد جلسات من المواعيد الأسبوعية من صفحة الجلسات."
        />
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

      <div className="dash-cards" style={{ marginBlockStart: 24 }}>
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
            {payments.paid} من {payments.students} دفعوا
          </div>
        </Link>
        <Link to="/app/notifications" className="dash-card dash-card-btn">
          <div className="k">
            <BellRing size={14} /> الإشعارات
          </div>
          <div className="v">{notifications.failed}</div>
          <div className="stat-sub">فشل إرسالها • {notifications.pending} قيد الإرسال</div>
        </Link>
      </div>
    </>
  );
}
