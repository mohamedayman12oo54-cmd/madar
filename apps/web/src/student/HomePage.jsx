import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarCheck, BookOpenCheck, Wallet, Gauge, Star, Bell } from "lucide-react";
import { Banner } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty } from "../dashboard/common.jsx";

export const STATE_LABEL = { good: "جيد", needs_follow_up: "يحتاج متابعة", at_risk: "معرّض للخطر" };
export const STATE_TONE = { good: "good", needs_follow_up: "warn", at_risk: "bad" };

export function Stars({ value }) {
  return <span className="stars" aria-label={`التقييم ${value} من 5`}>{[1, 2, 3, 4, 5].map((n) => <span key={n} style={{ color: n <= value ? "#d19a00" : "var(--line-2)", fontSize: "1.1rem" }}>★</span>)}</span>;
}

export default function HomePage() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { studentApi.overview().then(setD).catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل بياناتك.")); }, []);

  if (err) return <><PageHeader infoKey="student_home" title="الرئيسية" /><Banner tone="err">{err}</Banner></>;
  if (!d) return <><PageHeader infoKey="student_home" title="الرئيسية" /><p className="field-msg">جاري تحميل بياناتك...</p></>;
  const m = d.this_month;
  return (
    <>
      <PageHeader infoKey="student_home" title="الرئيسية" />
      <div className="stu-hello">مرحبًا {d.student.name} 👋</div>
      <div className="stu-sub">{d.environment.name} — {d.grade}{d.groups.length ? ` — ${d.groups.join("، ")}` : ""}</div>
      {d.unread_notifications > 0 && (
        <Link to="/learn/notifications" className="dash-note" style={{ display: "block" }}><Bell size={15} /> لديك {d.unread_notifications} إشعار غير مقروء</Link>
      )}
      <div className="dash-cards">
        <div className="dash-card"><div className="k"><CalendarCheck size={14} /> الحضور هذا الشهر</div>
          <div className="v">{m.attendance.present}</div><div className="stat-sub">حضور • {m.attendance.absent} غياب</div></div>
        <div className="dash-card"><div className="k"><BookOpenCheck size={14} /> التسميع هذا الشهر</div>
          <div className="v">{m.recitation.studied}</div><div className="stat-sub">ذاكر • {m.recitation.not_studied} لم يذاكر</div></div>
        <div className="dash-card"><div className="k"><Wallet size={14} /> دفع {m.month}</div>
          <div className="v"><span className={"chip-s " + (m.payment === "paid" ? "good" : "bad")}>{m.payment === "paid" ? "مدفوع" : "غير مدفوع"}</span></div></div>
        <div className="dash-card"><div className="k"><Gauge size={14} /> حالتي</div>
          <div className="v">{m.state ? <span className={"chip-s " + STATE_TONE[m.state]}>{STATE_LABEL[m.state]}</span> : "—"}</div></div>
        <div className="dash-card"><div className="k"><Star size={14} /> تقييم الشهر</div>
          <div className="v">{m.rating ? <Stars value={m.rating} /> : "—"}</div>{!m.rating && <div className="stat-sub">لم يُنشر بعد</div>}</div>
      </div>
      <div className="dash-section-head" style={{ marginBlockStart: 22 }}><h2>آخر الفيديوهات</h2><Link className="dash-linkish" to="/learn/videos">عرض الكل</Link></div>
      {d.latest_videos.length === 0 ? <Empty title="لا توجد فيديوهات بعد" text="ستظهر هنا الفيديوهات التي ينشرها معلمك لك." /> : (
        <div className="list-rows">{d.latest_videos.map((v) => <Link key={v.id} to="/learn/videos" className="list-row dash-card-btn"><strong>{v.title}</strong></Link>)}</div>
      )}
    </>
  );
}
