import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarCheck, BookOpenCheck, Wallet, Gauge, Star, Bell, QrCode } from "lucide-react";
import { Banner } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { qrImageSrc } from "../lib/qr.js";
import { PageHeader, Empty, fmtMonth } from "../dashboard/common.jsx";
import VideoCard from "./VideoCard.jsx";

export const STATE_LABEL = { good: "جيد", needs_follow_up: "يحتاج متابعة", at_risk: "معرّض للخطر" };
export const STATE_TONE = { good: "good", needs_follow_up: "warn", at_risk: "bad" };

export function Stars({ value }) {
  return (
    <span className="stars" aria-label={`التقييم ${value} من 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <span
          key={n}
          style={{ color: n <= value ? "#d19a00" : "var(--line-2)", fontSize: "1.1rem" }}
        >
          ★
        </span>
      ))}
    </span>
  );
}

export default function HomePage() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    studentApi
      .overview()
      .then(setD)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل بياناتك."));
  }, []);

  if (err)
    return (
      <>
        <PageHeader infoKey="student_home" title="الرئيسية" />
        <Banner tone="err">{err}</Banner>
      </>
    );
  if (!d)
    return (
      <>
        <PageHeader infoKey="student_home" title="الرئيسية" />
        <p className="field-msg">جاري تحميل بياناتك...</p>
      </>
    );
  const m = d.this_month;
  return (
    <>
      <PageHeader infoKey="student_home" title="الرئيسية" />
      <section className="stu-hero">
        <div className="stu-hello">مرحبًا {d.student.name} 👋</div>
        <div className="stu-sub">
          {d.environment.name} — {d.grade}
          {d.groups.length ? ` — ${d.groups.join("، ")}` : ""}
        </div>
        {d.student.badge_code && <StudentBadge code={d.student.badge_code} name={d.student.name} />}
      </section>
      {d.unread_notifications > 0 && (
        <Link to="/learn/notifications" className="dash-note" style={{ display: "block" }}>
          <Bell size={15} /> لديك {d.unread_notifications} إشعار غير مقروء
        </Link>
      )}
      <div className="dash-cards">
        <div className="dash-card">
          <div className="k">
            <CalendarCheck size={14} /> الحضور هذا الشهر
          </div>
          <div className="v">{m.attendance.present}</div>
          <div className="stat-sub">حضور • {m.attendance.absent} غياب</div>
        </div>
        <div className="dash-card">
          <div className="k">
            <BookOpenCheck size={14} /> التسميع هذا الشهر
          </div>
          <div className="v">{m.recitation.studied}</div>
          <div className="stat-sub">ذاكر • {m.recitation.not_studied} لم يذاكر</div>
        </div>
        <div className="dash-card">
          <div className="k">
            <Wallet size={14} /> دفع {fmtMonth(m.month)}
          </div>
          <div className="v">
            <span className={"chip-s " + (m.payment === "paid" ? "good" : "bad")}>
              {m.payment === "paid" ? "مدفوع" : "غير مدفوع"}
            </span>
          </div>
        </div>
        <div className="dash-card">
          <div className="k">
            <Gauge size={14} /> حالتي
          </div>
          <div className="v">
            {m.state ? (
              <span className={"chip-s " + STATE_TONE[m.state]}>{STATE_LABEL[m.state]}</span>
            ) : (
              "—"
            )}
          </div>
        </div>
        <div className="dash-card">
          <div className="k">
            <Star size={14} /> تقييم الشهر
          </div>
          <div className="v">{m.rating ? <Stars value={m.rating} /> : "—"}</div>
          {!m.rating && <div className="stat-sub">لم يُنشر بعد</div>}
        </div>
      </div>
      <div className="dash-section-head" style={{ marginBlockStart: 22 }}>
        <h2>آخر الفيديوهات</h2>
        <Link className="dash-linkish" to="/learn/videos">
          عرض الكل
        </Link>
      </div>
      {d.latest_videos.length === 0 ? (
        <Empty title="لا توجد فيديوهات بعد" text="ستظهر هنا الفيديوهات التي ينشرها معلمك لك." />
      ) : (
        <div className="list-rows">
          {d.latest_videos.map((v) => (
            <VideoCard key={v.id} video={v} />
          ))}
        </div>
      )}
    </>
  );
}

/** The student's own badge: the QR the teacher scans, plus the readable code
 *  as a fallback when a camera will not cooperate. It is rendered from the
 *  value the API returns, so a code the teacher rotates appears here on the
 *  next load rather than going stale. */
function StudentBadge({ code, name }) {
  const [svg, setSvg] = useState("");
  // The SVG is never injected as HTML: it is vetted and shown through an inert <img>.
  const qrSrc = qrImageSrc(svg);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    QRCode.toString(code, { type: "svg", margin: 1, width: 200, errorCorrectionLevel: "M" })
      .then((out) => alive && setSvg(out))
      .catch(() => alive && setSvg(""));
    return () => {
      alive = false;
    };
  }, [code]);

  return (
    <section className="stu-badge">
      <button type="button" className="stu-badge-toggle" onClick={() => setOpen((v) => !v)}>
        <QrCode size={16} /> {open ? "إخفاء رمزي" : "عرض رمزي للمعلّم"}
      </button>
      {open && (
        <div className="stu-badge-body">
          {qrSrc ? (
            <div className="stu-badge-qr">
              <img src={qrSrc} alt={`رمز ${name}`} width={200} height={200} />
            </div>
          ) : (
            <p className="field-msg">تعذّر عرض الرمز.</p>
          )}
          <code className="badge-code">{code}</code>
          <p className="field-msg">اعرض هذا الرمز للمعلّم لتسجيل الحضور أو التسميع أو الرسوم.</p>
        </div>
      )}
    </section>
  );
}
