import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { CalendarCheck, BookOpenCheck, Wallet, Gauge, Star, Bell, LogOut } from "lucide-react";
import { Banner } from "../auth/ui.jsx";
import logo from "../assets/madar-logo.png";
import { ApiError } from "../lib/api.js";
import {
  clearParentSession,
  getParentSession,
  parentApi,
  renewParentSession,
  setActiveChild,
} from "../lib/parentApi.js";
import { startKeepAlive } from "../lib/keepalive.js";
import { fmtDate, fmtDateTime, fmtMonth } from "../lib/dates.js";
import { fmtMoney } from "../dashboard/common.jsx";
import "../dashboard/dashboard.css"; // the cards, rows and chips used below live here
import "../student/student.css";

const STATE_LABEL = { good: "جيد", needs_follow_up: "يحتاج متابعة", at_risk: "معرّض للخطر" };
const STATE_TONE = { good: "good", needs_follow_up: "warn", at_risk: "bad" };
const ATT = { present: ["حضر", "good"], absent: ["غاب", "bad"] };
const REC = { studied: ["ذاكر", "good"], not_studied: ["لم يذاكر", "bad"] };

function Stars({ value }) {
  return (
    <span aria-label={`التقييم ${value} من 5`}>
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

/** Read-only follow-up for one child. Nothing here writes anything. */
export default function ParentPortal() {
  const nav = useNavigate();
  const [session, setSession] = useState(() => getParentSession());
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const active = session?.active ?? 0;
  const token = session?.children?.[active]?.token;
  // The portal reads whichever token is current; a background renewal swaps it WITHOUT reloading the page.
  const tokenRef = useRef(token);
  tokenRef.current = token;

  // No timed sign-out: while this tab is open the guardian's session is renewed in the background.
  useEffect(
    () =>
      startKeepAlive(async () => {
        const next = await renewParentSession();
        if (next) setSession(next);
        else nav("/auth/parent", { replace: true });
      }),
    [nav]
  );

  const out = () => {
    clearParentSession();
    nav("/auth/parent", { replace: true });
  };

  const hasToken = Boolean(token);
  useEffect(() => {
    if (!hasToken) return undefined;
    let alive = true;
    setD(null);
    setErr(null);
    parentApi
      .overview(tokenRef.current)
      .then((x) => alive && setD(x))
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401) {
          clearParentSession();
          nav("/auth/parent", { replace: true });
          return;
        }
        setErr(e instanceof ApiError ? e.message : "تعذّر تحميل البيانات.");
      });
    return () => {
      alive = false;
    };
  }, [hasToken, active, nav]);

  if (!session) return <Navigate to="/auth/parent" replace />;

  const pay = d?.payments;
  const latestEval = d?.evaluation?.[0];
  return (
    <div className="stu">
      <header className="stu-top">
        <div className="brand">
          <img src={logo} alt="مدار Madar" />
        </div>
        <div className="stu-env">
          <span className="name">متابعة ولي الأمر</span>
        </div>
        <div className="stu-top-end">
          <button className="stu-icon-btn" aria-label="تسجيل الخروج" onClick={out}>
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main className="stu-body" style={{ paddingBottom: 32 }}>
        {session.children.length > 1 && (
          <div
            className="ai-suggestions"
            role="tablist"
            aria-label="الأبناء"
            style={{ marginBlockStart: 0, marginBlockEnd: 14 }}
          >
            {session.children.map((c, i) => (
              <button
                key={i}
                type="button"
                role="tab"
                aria-selected={i === active}
                className={"mini-btn" + (i === active ? " is-active" : "")}
                style={
                  i === active ? { background: "var(--navy)", color: "var(--cream)" } : undefined
                }
                onClick={() => setSession(setActiveChild(i))}
              >
                {c.student_name}
              </button>
            ))}
          </div>
        )}

        {err && <Banner tone="err">{err}</Banner>}
        {!d && !err && <p className="field-msg">جاري تحميل البيانات...</p>}
        {d && (
          <>
            <div className="stu-hello">متابعة {d.student.name}</div>
            <div className="stu-sub">
              {d.student.teacher_environment} — {d.student.grade}
            </div>

            <div className="dash-cards">
              <div className="dash-card">
                <div className="k">
                  <CalendarCheck size={14} /> الحضور
                </div>
                <div className="v">{d.attendance.present}</div>
                <div className="stat-sub">حضور • {d.attendance.absent} غياب</div>
              </div>
              <div className="dash-card">
                <div className="k">
                  <BookOpenCheck size={14} /> التسميع
                </div>
                <div className="v">{d.recitation.studied}</div>
                <div className="stat-sub">ذاكر • {d.recitation.not_studied} لم يذاكر</div>
              </div>
              <div className="dash-card">
                <div className="k">
                  <Wallet size={14} /> دفع {fmtMonth(pay.this_month.month)}
                </div>
                <div className="v">
                  <span className={"chip-s " + (pay.this_month.status === "paid" ? "good" : "bad")}>
                    {pay.this_month.status === "paid" ? "مدفوع" : "غير مدفوع"}
                  </span>
                </div>
                <div className="stat-sub">{fmtMoney(pay.this_month.amount)}</div>
              </div>
              <div className="dash-card">
                <div className="k">
                  <Gauge size={14} /> الحالة
                </div>
                <div className="v">
                  {latestEval?.state ? (
                    <span className={"chip-s " + STATE_TONE[latestEval.state]}>
                      {STATE_LABEL[latestEval.state] || latestEval.state_label}
                    </span>
                  ) : (
                    "—"
                  )}
                </div>
              </div>
              <div className="dash-card">
                <div className="k">
                  <Star size={14} /> آخر تقييم
                </div>
                <div className="v">
                  {latestEval?.rating ? <Stars value={latestEval.rating} /> : "—"}
                </div>
                {!latestEval?.rating && <div className="stat-sub">لم يُنشر بعد</div>}
              </div>
            </div>

            <Section
              title="آخر حصص الحضور"
              empty="لا توجد سجلات حضور بعد."
              rows={d.attendance.recent}
              render={(r) => (
                <Row key={r.date + r.status} when={fmtDate(r.date)} tag={ATT[r.status]} />
              )}
            />
            <Section
              title="آخر حصص التسميع"
              empty="لا توجد سجلات تسميع بعد."
              rows={d.recitation.recent}
              render={(r) => (
                <Row key={r.date + r.status} when={fmtDate(r.date)} tag={REC[r.status]} />
              )}
            />
            <Section
              title="المدفوعات"
              empty="لا توجد أشهر مسجلة."
              rows={pay.history}
              render={(p) => (
                <Row
                  key={p.month}
                  when={fmtMonth(p.month)}
                  tag={p.status === "paid" ? ["مدفوع", "good"] : ["غير مدفوع", "bad"]}
                  extra={`${fmtMoney(p.amount)}${p.paid_at ? ` • ${fmtDateTime(p.paid_at)}` : ""}`}
                />
              )}
            />
            <Section
              title="الإشعارات"
              icon={<Bell size={15} />}
              empty="لا توجد إشعارات."
              rows={d.notifications}
              render={(n) => (
                <div key={n.id} className="list-row">
                  <div>
                    <strong>{n.title}</strong>
                    {n.body && <div className="stat-sub">{n.body}</div>}
                    <div className="stat-sub">{fmtDateTime(n.created_at)}</div>
                  </div>
                </div>
              )}
            />
          </>
        )}
      </main>
    </div>
  );
}

function Row({ when, tag, extra }) {
  return (
    <div className="list-row">
      <div>
        <strong>{when}</strong>
        {extra && <div className="stat-sub">{extra}</div>}
      </div>
      {tag && <span className={"chip-s " + tag[1]}>{tag[0]}</span>}
    </div>
  );
}

function Section({ title, icon, rows, empty, render }) {
  return (
    <section style={{ marginBlockStart: 22 }}>
      <div className="dash-section-head">
        <h2>
          {icon} {title}
        </h2>
      </div>
      {rows?.length ? (
        <div className="list-rows">{rows.map(render)}</div>
      ) : (
        <p className="field-msg">{empty}</p>
      )}
    </section>
  );
}
