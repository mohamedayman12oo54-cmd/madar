import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import {
  CalendarCheck,
  BookOpenCheck,
  Wallet,
  Gauge,
  Star,
  Bell,
  LogOut,
  GraduationCap,
  TriangleAlert,
  MessageSquareText,
  CalendarClock,
  TrendingUp,
  PlayCircle,
  Sparkles,
  Printer,
  Trophy,
  CircleCheck,
  Banknote,
} from "lucide-react";
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
import "../dashboard/dashboard.css"; // the shared chips live here
import "../student/student.css";
import ReplyBox from "./ReplyBox.jsx";
import TrendChart from "./TrendChart.jsx";
import "./parent.css";
import "./print.css";

const STATE_LABEL = { good: "جيد", needs_follow_up: "يحتاج متابعة", at_risk: "معرّض للخطر" };
const STATE_TONE = { good: "good", needs_follow_up: "warn", at_risk: "bad" };
const EXAM_STATE = {
  in_progress: ["جارٍ الآن", "warn"],
  missed: ["لم يمتحن", "bad"],
  not_taken: ["لم يبدأ بعد", "warn"],
};
const NOTIFICATIONS_SHOWN = 6;
// A score reads as good / needs-attention at a glance; the thresholds are only a visual cue, not a grade.
const percentTone = (p) => (p >= 75 ? "good" : p >= 50 ? "warn" : "bad");
const attendanceTone = (p) => (p >= 85 ? "good" : p >= 70 ? "warn" : "bad");
const fmtNum = (n) => (Number.isInteger(n) ? String(n) : String(Math.round(n * 10) / 10));
// Digits around a slash get reordered by right-to-left text ("7 / 10" shows as "10 / 7"): isolate them.
const ltr = (t) => <bdi dir="ltr">{t}</bdi>;
const ratio = (part, whole) => (whole ? Math.round((part * 100) / whole) : null);

function Stars({ value }) {
  return (
    <span aria-label={`التقييم ${value} من 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} style={{ color: n <= value ? "#d19a00" : "var(--line-2)", fontSize: "1.2rem" }}>
          ★
        </span>
      ))}
    </span>
  );
}

/** What deserves the guardian's attention right now, most urgent first. Display only: nothing is decided here. */
function attention(d, freshWarnings) {
  const out = [];
  const pay = d.payments.this_month;
  if (pay.month && pay.status !== "paid") out.push(["bad", `مصروفات ${fmtMonth(pay.month)} غير مسددة`]);
  if (freshWarnings > 0) out.push(["bad", `${freshWarnings} تحذير جديد من المعلّم`]);
  const state = d.evaluation[0]?.state;
  if (state === "at_risk") out.push(["bad", "التقييم الأخير: معرّض للخطر"]);
  else if (state === "needs_follow_up") out.push(["warn", "التقييم الأخير: يحتاج متابعة"]);
  const rate = ratio(d.attendance.present, d.attendance.total);
  if (rate != null && rate < 70) out.push(["warn", `نسبة الحضور ${rate}%`]);
  if (d.exams.average_percent != null && d.exams.average_percent < 50) {
    out.push(["warn", `متوسط الامتحانات ${fmtNum(d.exams.average_percent)}%`]);
  }
  return out;
}

/** Read-only follow-up for one child (plus replying to the teacher's messages). */
export default function ParentPortal() {
  const nav = useNavigate();
  const [session, setSession] = useState(() => getParentSession());
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  // Messages that were still unread when the page loaded: they keep their "جديد" badge for this visit even
  // though opening the page marks them read.
  const [fresh, setFresh] = useState(() => new Set());
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
    nav("/", { replace: true });
  };

  const hasToken = Boolean(token);
  useEffect(() => {
    if (!hasToken) return undefined;
    let alive = true;
    setD(null);
    setErr(null);
    parentApi
      .overview(tokenRef.current)
      .then((x) => {
        if (!alive) return;
        setD(x);
        const unread = x.messages.filter((m) => !m.read_at).map((m) => m.id);
        setFresh(new Set(unread));
        // Showing the messages IS reading them. A failure here must never hide the page.
        unread.forEach((id) => parentApi.markRead(tokenRef.current, id).catch(() => {}));
      })
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

  const onReplySent = (messageId, reply) =>
    setD((prev) => ({
      ...prev,
      messages: prev.messages.map((x) =>
        x.id === messageId
          ? { ...x, replies: [...x.replies, reply], can_reply: x.replies.length + 1 < 3 }
          : x
      ),
    }));

  return (
    <div className="stu">
      <header className="stu-top no-print">
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

      <main className="stu-body pp">
        {err && <Banner tone="err">{err}</Banner>}
        {!d && !err && (
          <div className="pp-skel" aria-busy="true">
            <span className="pp-sr">جاري تحميل البيانات...</span>
            <div className="h" />
            <div className="k" />
            <div className="p" />
          </div>
        )}
        {d && (
          <Report
            d={d}
            session={session}
            active={active}
            fresh={fresh}
            tokenRef={tokenRef}
            onPickChild={(i) => setSession(setActiveChild(i))}
            onReplySent={onReplySent}
          />
        )}
      </main>
    </div>
  );
}

function Report({ d, session, active, fresh, onPickChild, onReplySent, tokenRef }) {
  const pay = d.payments;
  const latestEval = d.evaluation[0];
  const att = d.attendance;
  const rec = d.recitation;
  const attRate = ratio(att.present, att.total);
  const recRate = ratio(rec.studied, rec.total);
  const freshWarnings = d.messages.filter((m) => m.kind === "warning" && fresh.has(m.id)).length;
  const alerts = attention(d, freshWarnings);
  const paid = pay.this_month.status === "paid";

  return (
    <>
      <section className="pp-hero" aria-label="ملخص">
        <div className="pp-hero-top">
          <div>
            <div className="pp-name">متابعة {d.student.name}</div>
            <div className="pp-meta">
              {d.student.teacher_environment} — {d.student.grade}
            </div>
            <div className="pp-meta print-only">تقرير بتاريخ {fmtDate(new Date().toISOString())}</div>
          </div>
          <button type="button" className="mini-btn pp-print no-print" onClick={() => window.print()}>
            <Printer size={14} /> طباعة / حفظ PDF
          </button>
        </div>

        {session.children.length > 1 && (
          <div className="pp-children no-print" role="tablist" aria-label="الأبناء">
            {session.children.map((c, i) => (
              <button
                key={i}
                type="button"
                role="tab"
                aria-selected={i === active}
                onClick={() => onPickChild(i)}
              >
                {c.student_name}
              </button>
            ))}
          </div>
        )}

        <div className="pp-attn" role="status">
          <div className="pp-attn-title">{alerts.length ? "يحتاج انتباهك" : "الحالة العامة"}</div>
          <ul>
            {alerts.length ? (
              alerts.map(([tone, text]) => (
                <li key={text} className={tone}>
                  <TriangleAlert size={14} /> {text}
                </li>
              ))
            ) : (
              <li className="good">
                <CircleCheck size={14} /> كل شيء على ما يرام
              </li>
            )}
          </ul>
        </div>
      </section>

      <div className="pp-kpis">
        <Kpi
          icon={<CalendarCheck size={15} />}
          label="الحضور"
          tone={attRate != null ? attendanceTone(attRate) : ""}
          value={attRate != null ? `${attRate}%` : "—"}
          sub={`حضر ${att.present} • غاب ${att.absent}`}
        />
        <Kpi
          icon={<BookOpenCheck size={15} />}
          label="التسميع"
          tone={recRate != null ? attendanceTone(recRate) : ""}
          value={recRate != null ? `${recRate}%` : "—"}
          sub={`ذاكر ${rec.studied} • لم يذاكر ${rec.not_studied}`}
        />
        <Kpi
          icon={<Wallet size={15} />}
          label={`دفع ${fmtMonth(pay.this_month.month)}`}
          tone={paid ? "good" : "bad"}
          value={<span className={"chip-s " + (paid ? "good" : "bad")}>{paid ? "مدفوع" : "غير مدفوع"}</span>}
          sub={fmtMoney(pay.this_month.amount)}
        />
        <Kpi
          icon={<Gauge size={15} />}
          label="الحالة"
          tone={latestEval?.state ? STATE_TONE[latestEval.state] : ""}
          value={
            latestEval?.state ? (
              <span className={"chip-s " + STATE_TONE[latestEval.state]}>
                {STATE_LABEL[latestEval.state] || latestEval.state_label}
              </span>
            ) : (
              "—"
            )
          }
          sub={latestEval ? fmtMonth(latestEval.month) : "لا يوجد تقييم بعد"}
        />
        <Kpi
          icon={<Star size={15} />}
          label="آخر تقييم"
          value={latestEval?.rating ? <Stars value={latestEval.rating} /> : "—"}
          sub={latestEval?.rating ? fmtMonth(latestEval.month) : "لم يُنشر بعد"}
        />
        <Kpi
          icon={<GraduationCap size={15} />}
          label="متوسط الامتحانات"
          tone={d.exams.average_percent != null ? percentTone(d.exams.average_percent) : ""}
          value={d.exams.average_percent != null ? `${fmtNum(d.exams.average_percent)}%` : "—"}
          sub={`${d.exams.finished} من ${d.exams.total} امتحان`}
        />
        {d.rank?.position != null && (
          <Kpi
            icon={<Trophy size={15} />}
            label="الترتيب"
            value={d.rank.position}
            sub={`من ${d.rank.of} في متوسط الامتحانات بين زملاء مجموعته`}
          />
        )}
      </div>

      <div className="pp-cols">
        <div className="pp-col">
          <Panel
            title="رسائل المعلّم"
            icon={<MessageSquareText size={16} />}
            meta={fresh.size ? <span className="chip-s warn">{fresh.size} جديدة</span> : null}
            empty="لا توجد رسائل من المعلّم."
            isEmpty={!d.messages.length}
          >
            {d.messages.length > 0 && (
              <div className="pp-msgs">
                {d.messages.map((m) => (
                  <article key={m.id} className={"pp-msg " + m.kind}>
                    <div className="pp-msg-head">
                      <div className="pp-msg-title">
                        {fresh.has(m.id) && <span className="chip-s warn pp-new">جديد</span>}
                        {m.kind === "warning" && <TriangleAlert size={15} />}
                        {m.title}
                      </div>
                      <span className={"chip-s " + (m.kind === "warning" ? "bad" : "")}>{m.kind_label}</span>
                    </div>
                    <div className="pp-msg-body">{m.body}</div>
                    <div className="pp-msg-time">{fmtDateTime(m.created_at)}</div>
                    {m.replies.map((r) => (
                      <div key={r.id} className="pp-reply">
                        <small>ردّك • {fmtDateTime(r.created_at)}</small>
                        <div style={{ whiteSpace: "pre-wrap" }}>{r.body}</div>
                      </div>
                    ))}
                    {m.can_reply && (
                      <ReplyBox
                        onSend={(body) => parentApi.reply(tokenRef.current, m.id, body)}
                        onSent={(reply) => onReplySent(m.id, reply)}
                      />
                    )}
                  </article>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="التطور خلال ٦ أشهر" icon={<TrendingUp size={16} />}>
            <TrendChart trend={d.trend} />
          </Panel>

          <Panel
            title="درجات الامتحانات"
            icon={<GraduationCap size={16} />}
            empty="لا توجد امتحانات بعد."
            rows={d.exams.results}
            render={(x) => (
              <Row
                key={x.id}
                title={x.title}
                sub={x.closes_at ? `آخر موعد: ${fmtDateTime(x.closes_at)}` : null}
                bar={x.state === "finished" ? { percent: x.percent, tone: percentTone(x.percent) } : null}
                tag={
                  x.state === "finished"
                    ? [
                        <>
                          {ltr(`${fmtNum(x.score)} / ${fmtNum(x.max_score)}`)} • {ltr(`${fmtNum(x.percent)}%`)}
                        </>,
                        percentTone(x.percent),
                      ]
                    : EXAM_STATE[x.state]
                }
              />
            )}
          />

          <Panel
            title="متابعة الفيديوهات"
            icon={<PlayCircle size={16} />}
            meta={<span className="chip-s">أكمل {d.videos.completed} من {d.videos.total}</span>}
            empty="لا توجد فيديوهات منشورة له بعد."
            rows={d.videos.recent}
            render={(v) => (
              <Row
                key={v.id}
                title={v.title}
                sub={v.last_watched_at ? `آخر مشاهدة: ${fmtDateTime(v.last_watched_at)}` : "لم يشاهده بعد"}
                bar={{ percent: v.completed ? 100 : v.percent, tone: v.completed ? "good" : "warn" }}
                tag={v.completed ? ["أكمله", "good"] : v.percent > 0 ? [`${v.percent}%`, "warn"] : ["لم يبدأ", "bad"]}
              />
            )}
          />

          <Panel
            title="كويزات الذكاء الاصطناعي"
            icon={<Sparkles size={16} />}
            meta={
              d.quizzes.average_percent != null ? (
                <span className="chip-s">المتوسط {ltr(`${fmtNum(d.quizzes.average_percent)}%`)}</span>
              ) : null
            }
            empty="لم يحل كويزات بعد."
            rows={d.quizzes.recent}
            render={(q) => (
              <Row
                key={q.submitted_at + q.title}
                title={q.title}
                sub={fmtDateTime(q.submitted_at)}
                tag={[ltr(`${q.score} / ${q.total}`), percentTone(q.percent)]}
              />
            )}
          />
        </div>

        <div className="pp-col">
          <Panel
            title="مواعيد الحصص"
            icon={<CalendarClock size={16} />}
            empty="لم تُحدد مواعيد للحصص بعد."
            rows={d.schedule.weekly}
            wrap="pp-slots"
            render={(w) => (
              <div key={w.group + w.weekday + w.start_time} className="pp-slot">
                <span className="pp-slot-day">{w.weekday_label}</span>{" "}
                <span className="pp-slot-time">
                  {w.start_time}
                  {w.end_time ? ` – ${w.end_time}` : ""}
                </span>
                <span className="chip-s">{w.group}</span>
              </div>
            )}
          />

          {d.schedule.upcoming.length > 0 && (
            <Panel
              title="الحصص القادمة"
              icon={<CalendarClock size={16} />}
              rows={d.schedule.upcoming}
              render={(u) => (
                <Row
                  key={u.scheduled_at + u.group}
                  title={fmtDateTime(u.scheduled_at)}
                  tag={u.status === "open" ? ["مفتوحة الآن", "good"] : [u.group, ""]}
                />
              )}
            />
          )}

          <Panel
            title="المدفوعات"
            icon={<Banknote size={16} />}
            empty="لا توجد أشهر مسجلة."
            rows={pay.history}
            render={(p) => (
              <Row
                key={p.month}
                title={fmtMonth(p.month)}
                sub={`${fmtMoney(p.amount)}${p.paid_at ? ` • ${fmtDateTime(p.paid_at)}` : ""}`}
                tag={p.status === "paid" ? ["مدفوع", "good"] : ["غير مدفوع", "bad"]}
              />
            )}
          />

          <Panel
            title="آخر حصص الحضور"
            icon={<CalendarCheck size={16} />}
            empty="لا توجد سجلات حضور بعد."
            isEmpty={!att.recent.length}
          >
            <div className="pp-pills">
              {att.recent.map((r) => (
                <span key={r.date + r.status} className={"pp-pill " + (r.status === "present" ? "good" : "bad")}>
                  {fmtDate(r.date)} • {r.status === "present" ? "حضر" : "غاب"}
                </span>
              ))}
            </div>
          </Panel>

          <Panel
            title="آخر حصص التسميع"
            icon={<BookOpenCheck size={16} />}
            empty="لا توجد سجلات تسميع بعد."
            isEmpty={!rec.recent.length}
          >
            <div className="pp-pills">
              {rec.recent.map((r) => (
                <span key={r.date + r.status} className={"pp-pill " + (r.status === "studied" ? "good" : "bad")}>
                  {fmtDate(r.date)} • {r.status === "studied" ? "ذاكر" : "لم يذاكر"}
                </span>
              ))}
            </div>
          </Panel>

          <Panel
            title="الإشعارات"
            icon={<Bell size={16} />}
            empty="لا توجد إشعارات."
            rows={d.notifications.slice(0, NOTIFICATIONS_SHOWN)}
            render={(n) => (
              <Row
                key={n.id}
                title={n.title}
                sub={[n.body, fmtDateTime(n.created_at)].filter(Boolean).join(" • ")}
              />
            )}
          />
        </div>
      </div>
    </>
  );
}

function Kpi({ icon, label, value, sub, tone = "" }) {
  return (
    <div className={"pp-kpi " + tone}>
      <div className="pp-kpi-head">
        <span className="pp-ic">{icon}</span>
        {label}
      </div>
      <div className="pp-kpi-val">{value}</div>
      <div className="pp-kpi-sub">{sub}</div>
    </div>
  );
}

/** One titled card. Give it `rows` + `render` (a list) or children (a custom body). When there is nothing to
 *  show it prints the `empty` line instead of a hollow box; custom bodies say so with `isEmpty`. */
function Panel({ title, icon, meta, empty, isEmpty, rows, render, wrap = "pp-rows", children }) {
  const none = isEmpty ?? (rows ? rows.length === 0 : false);
  return (
    <section className="pp-panel">
      <div className="pp-panel-head">
        {icon && <span className="pp-ic">{icon}</span>}
        <h2>{title}</h2>
        {meta}
      </div>
      {none && empty ? (
        <p className="pp-empty">{empty}</p>
      ) : rows ? (
        <div className={wrap}>{rows.map(render)}</div>
      ) : (
        children
      )}
    </section>
  );
}

function Row({ title, sub, tag, bar }) {
  return (
    <div className="pp-row">
      <div className="pp-row-main">
        <div className="pp-row-title">{title}</div>
        {sub && <div className="pp-row-sub">{sub}</div>}
        {bar && (
          <div
            className={"pp-bar " + bar.tone}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(bar.percent)}
          >
            <i style={{ width: `${Math.min(100, Math.max(0, bar.percent))}%` }} />
          </div>
        )}
      </div>
      {tag && <span className={"chip-s " + tag[1]}>{tag[0]}</span>}
    </div>
  );
}
