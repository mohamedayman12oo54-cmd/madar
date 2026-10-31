import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Clock, Info, ListChecks, Lock, RotateCcw, ShieldAlert, Timer, TriangleAlert } from "lucide-react";
import { Btn, Banner } from "../auth/ui.jsx";
import { PageHeader, Empty } from "../dashboard/common.jsx";
import logo from "../assets/madar-logo.png";
import { studentExamsApi as X } from "../lib/examsApi.js";
import { ApiError } from "../lib/api.js";
import { useSession } from "../state/session.jsx";
import { CHOICE_LETTERS, band, clampPct, clock, nAr, pctText, progressPct, warningInfo, warningsText } from "../lib/exam.js";
import {
  enterFullscreen, fullscreenSupported, inFullscreen, leaveFullscreen, startGuard, trapBack, watermarkStyle,
} from "./examGuard.js";
import "../dashboard/exams.css";
import "./exam.css";

const STATE_LABEL = { open: "متاح الآن", in_progress: "قيد الحل", finished: "تم التسليم", upcoming: "لم يبدأ بعد", closed: "انتهى موعده" };
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("ar-EG", { dateStyle: "medium", timeStyle: "short" }) : null);
const msg = (e) => (e instanceof ApiError ? e.message : "تعذّر الاتصال، حاول مرة أخرى.");

/* ------------------------------------------------------------------ shared bits */

/** A percentage as a ring. The colour comes from the result band (see lib/exam.js `band`). */
function Ring({ percent, size = 56, label }) {
  const p = clampPct(percent);
  const r = 52;
  const c = 2 * Math.PI * r;
  return (
    <div className={"x-ring " + band(p).cls} style={{ inlineSize: size, blockSize: size }} role="img" aria-label={label || `النسبة ${pctText(p)}`}>
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle className="x-ring-track" cx="60" cy="60" r={r} />
        <circle className="x-ring-fill" cx="60" cy="60" r={r} strokeDasharray={c} strokeDashoffset={c * (1 - p / 100)} transform="rotate(-90 60 60)" />
      </svg>
      <b>{pctText(p)}</b>
    </div>
  );
}

/** A calm inline notice (icon + sentence on one line) for the result page. */
function Note({ tone = "info", children }) {
  const I = tone === "bad" ? TriangleAlert : Info;
  return <div className={"xd-note is-" + tone} role="note"><I size={18} /><span>{children}</span></div>;
}

function Shell({ children, back = true, className = "" }) {
  return (
    <div className={"xs-shell " + className}>
      <header className="xs-top">
        <img src={logo} alt="مدار Madar" />
        {back && <Link className="xs-back" to="/learn/exams">رجوع للامتحانات</Link>}
      </header>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ the student's exam list */

function ExamCard({ r }) {
  const finished = r.state === "finished";
  const active = r.state === "open" || r.state === "in_progress";
  return (
    <article className={"xs-card is-" + r.state}>
      <div className="xs-main">
        <h3>{r.title}</h3>
        <span className={"xs-state is-" + r.state}>{STATE_LABEL[r.state]}</span>
        <div className="xs-meta">
          <span><ListChecks size={14} /> {nAr(r.question_count)} سؤال</span>
          <span><Clock size={14} /> {nAr(r.duration_minutes)} دقيقة</span>
          {r.attempts > 1 && <span><RotateCcw size={14} /> {nAr(r.attempts)} محاولات</span>}
        </div>
        {r.reopened && <span className="xs-flag">أعاد المعلّم فتح الامتحان لك</span>}
        {r.state === "upcoming" && <span className="xs-note">يبدأ {fmt(r.opens_at)}</span>}
        {r.state === "closed" && <span className="xs-note">انتهى موعد هذا الامتحان</span>}
        {active && r.closes_at && <span className="xs-note">يُغلق {fmt(r.closes_at)}</span>}
      </div>
      <div className="xs-side">
        {finished && (
          <div className="xs-best">
            <Ring percent={r.percent} size={64} label={`أعلى نتيجة ${pctText(r.percent)}`} />
            <span>{r.attempts > 1 ? "أعلى نتيجة" : "نتيجتك"}<small>{nAr(r.score)} من {nAr(r.max_score)} درجة</small></span>
          </div>
        )}
        <div className="xs-actions">
          {active && <Link className="abtn abtn-primary" to={`/learn/exams/${r.id}`}>{r.state === "in_progress" ? "استكمال الامتحان" : "ابدأ الامتحان"}</Link>}
          {finished && r.can_retake && <Link className="abtn abtn-primary" to={`/learn/exams/${r.id}?retake=1`}>ابدأ محاولة جديدة</Link>}
          {finished && <Link className="abtn abtn-ghost" to={`/learn/exams/${r.id}`}>عرض النتيجة</Link>}
        </div>
      </div>
    </article>
  );
}

/** The student's exams (no page header), so it can sit inside the content page's "امتحانات" tab as well. */
export function ExamList() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { X.list().then((d) => setRows(d.results || [])).catch((e) => setErr(msg(e))); }, []);
  return (
    <>
      {err && <Banner tone="err">{err}</Banner>}
      {!rows && !err && <p className="field-msg">جاري التحميل...</p>}
      {rows && rows.length === 0 && <Empty title="لا توجد امتحانات" text="ستظهر هنا الامتحانات التي ينشرها معلّمك." />}
      <div className="xs-list">{(rows || []).map((r) => <ExamCard key={r.id} r={r} />)}</div>
    </>
  );
}

export function ExamsPage() {
  return (
    <>
      <PageHeader title="الامتحانات" />
      <ExamList />
    </>
  );
}

/* ------------------------------------------------------------------ taking an exam */

function Countdown({ deadline, onEnd, className = "" }) {
  const [left, setLeft] = useState(() => Math.max(0, Math.floor((new Date(deadline) - Date.now()) / 1000)));
  useEffect(() => {
    const t = setInterval(() => {
      const s = Math.max(0, Math.floor((new Date(deadline) - Date.now()) / 1000));
      setLeft(s);
      if (s === 0) { clearInterval(t); onEnd?.(); }
    }, 500);
    return () => clearInterval(t);
  }, [deadline, onEnd]);
  return <span className={"xr-timer " + className + (left < 60 ? " is-low" : "")} role="timer"><Timer size={16} /> {clock(left)}</span>;
}

/** The warning budget: one pip per allowed violation, filled as they are used. */
function Strikes({ used, max }) {
  return (
    <span className={"xr-strikes" + (used ? " has-used" : "")} role="img" aria-label={`التحذيرات ${nAr(used)} من ${nAr(max)}`}>
      <ShieldAlert size={16} />
      <span className="xr-strikes-l" aria-hidden="true">التحذيرات</span>
      <span className="pips" aria-hidden="true">
        {Array.from({ length: max }, (_, i) => <i key={i} className={i < used ? "on" : ""} />)}
      </span>
    </span>
  );
}

function QuestionMap({ total, index, reached, canJump, onJump }) {
  if (total > 40) return null;
  return (
    <nav className="xr-map" aria-label="خريطة الأسئلة">
      {Array.from({ length: total }, (_, i) => {
        const done = i < reached;
        const open = canJump && i <= reached && i !== index;
        return (
          <button key={i} type="button" disabled={!open} aria-current={i === index ? "step" : undefined}
            className={"xr-dot" + (i === index ? " is-now" : done ? " is-done" : "")} onClick={() => onJump(i)}
            aria-label={`السؤال ${nAr(i + 1)}${done ? " — تمت الإجابة" : ""}`}>
            {nAr(i + 1)}
          </button>
        );
      })}
    </nav>
  );
}

/** Full-screen warning shown the moment a violation is counted. It cannot be skipped; the exam clock keeps running. */
function WarningOverlay({ info, deadline, onContinue }) {
  const btn = useRef(null);
  useEffect(() => { btn.current?.focus(); }, []);
  return (
    <div className={"xr-overlay" + (info.final ? " is-final" : "")} role="alertdialog" aria-modal="true" aria-labelledby="xw-t" aria-describedby="xw-d">
      <div className="xr-ocard">
        <div className="xr-oicon"><TriangleAlert size={30} /></div>
        <h2 id="xw-t">{info.title}</h2>
        <p className="xr-oreason">{info.reason}</p>
        <div className="xr-ocount" aria-hidden="true">
          {Array.from({ length: info.max }, (_, i) => <i key={i} className={i < info.n ? "on" : ""} />)}
        </div>
        <p className="xr-ocountlabel">المخالفة {nAr(info.n)} من {nAr(info.max)}</p>
        <p id="xw-d" className="xr-onext">{info.next}</p>
        <p className="xr-oclock">الوقت لا يتوقف: <Countdown deadline={deadline} /></p>
        <button ref={btn} type="button" className="abtn abtn-primary" onClick={onContinue}>فهمت، أكمل الامتحان</button>
      </div>
    </div>
  );
}

function NeedFullscreen({ onEnter }) {
  return (
    <div className="xr-overlay" role="alertdialog" aria-modal="true" aria-labelledby="xf-t">
      <div className="xr-ocard">
        <div className="xr-oicon is-calm"><Lock size={28} /></div>
        <h2 id="xf-t">الامتحان يعمل بالشاشة الكاملة</h2>
        <p className="xr-onext">عُد إلى الشاشة الكاملة لتكمل. الوقت لا يتوقف.</p>
        <button type="button" className="abtn abtn-primary" onClick={onEnter}>العودة للشاشة الكاملة</button>
      </div>
    </div>
  );
}

function SubmitSheet({ left, busy, onYes, onNo }) {
  return (
    <div className="xr-overlay is-sheet" role="alertdialog" aria-modal="true" aria-labelledby="xs-t">
      <div className="xr-ocard">
        <h2 id="xs-t">تسليم الامتحان الآن؟</h2>
        <p className="xr-onext">{left > 1 ? `لم تُجب بعد على ${nAr(left - 1)} ${left - 1 === 1 ? "سؤال" : "أسئلة"} بعد هذا السؤال. ` : ""}لن تستطيع تعديل إجاباتك بعد التسليم.</p>
        <div className="xr-orow">
          <Btn variant="ghost" onClick={onNo}>متابعة الامتحان</Btn>
          <Btn onClick={onYes} loading={busy}>نعم، سلّم</Btn>
        </div>
      </div>
    </div>
  );
}

const RULES = (info) => [
  "الامتحان يعمل بالشاشة الكاملة. الخروج منها أو ترك الصفحة أو تبديل التبويب مخالفة.",
  "النسخ واللصق والطباعة وقائمة النقر الأيمن واختصارات لوحة المفاتيح ممنوعة.",
  `لديك ${warningsText(info.max_violations || 3)} قبل أن يُغلق الامتحان تلقائيًا ويُسلَّم بما أجبت.`,
  info.allow_back === false ? "سؤال واحد في كل مرة، ولا يمكن الرجوع إلى سؤال سابق." : "سؤال واحد في كل مرة، ويمكنك الرجوع لتعديل إجاباتك.",
  "الوقت يحسبه الخادم ولا يتوقف إذا أغلقت الصفحة.",
  "اسمك ورقمك يظهران على الشاشة طوال الامتحان.",
];

export function ExamRunPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { user } = useSession();
  const [phase, setPhase] = useState("loading"); // loading | intro | blocked | running | done
  const [info, setInfo] = useState(null); // the exam's row from the list (title, rules, state …)
  const [retake, setRetake] = useState(false);
  const [st, setSt] = useState(null);
  const [q, setQ] = useState(null);
  const [chosen, setChosen] = useState(null);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState(null);
  const [warn, setWarn] = useState(null);
  const [toast, setToast] = useState(null);
  const [fs, setFs] = useState(inFullscreen());
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const stateRef = useRef(null);
  stateRef.current = { phase, st };

  const finish = useCallback(async () => {
    await leaveFullscreen();
    setWarn(null); setConfirming(false);
    try { setResult(await X.result(id)); } catch (e) { setResult({ error: msg(e) }); }
    setPhase("done");
  }, [id]);

  // Which screen first: the intro, the result, or "not available".
  useEffect(() => {
    X.list().then((d) => {
      const row = (d.results || []).find((r) => String(r.id) === String(id));
      if (!row) return setErr("هذا الامتحان غير متاح لك.");
      setInfo(row);
      if (row.state === "finished") {
        if (params.get("retake") === "1" && row.can_retake) { setRetake(true); return setPhase("intro"); }
        return finish();
      }
      if (row.state === "upcoming" || row.state === "closed") return setPhase("blocked");
      setPhase("intro");
    }).catch((e) => setErr(msg(e)));
  }, [id, finish, params]);

  const loadQuestion = useCallback(async (index) => {
    try {
      const data = await X.question(id, index);
      if (!Array.isArray(data?.choices)) throw new Error("bad question");
      setQ(data); setSt((s) => ({ ...s, ...data })); setChosen(data.chosen_choice_id ?? null); setErr(null);
    } catch (e) {
      if (e instanceof ApiError && ["finished", "not_started"].includes(e.code)) return finish();
      setErr(msg(e));
    }
  }, [id, finish]);

  const report = useCallback(async (type) => {
    if (stateRef.current.phase !== "running") return;
    try {
      const r = await X.violation(id, type);
      if (r.finished) return finish();
      setSt((s) => ({ ...s, ...r }));
      if (r.counted) setWarn(warningInfo({ type: r.last_violation || type, violations: r.violations, max: r.max_violations }));
    } catch { /* offline: the server still enforces time; the report is best-effort */ }
  }, [id, finish]);

  // While running: detect and report, keep the browser's Back button from leaving, and follow full screen.
  useEffect(() => {
    if (phase !== "running") return undefined;
    const stopGuard = startGuard(report);
    const stopBack = trapBack(() => setToast("لا يمكن الرجوع أثناء الامتحان. إن أردت الإنهاء استخدم «تسليم الآن»."));
    const onFs = () => setFs(inFullscreen());
    document.addEventListener("fullscreenchange", onFs);
    document.addEventListener("webkitfullscreenchange", onFs);
    return () => {
      stopGuard(); stopBack();
      document.removeEventListener("fullscreenchange", onFs);
      document.removeEventListener("webkitfullscreenchange", onFs);
    };
  }, [phase, report]);
  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const begin = async () => {
    setErr(null); setBusy(true);
    try {
      await enterFullscreen();
      const s = await X.start(id, retake);
      if (s.finished) { await finish(); return; }
      setSt((o) => ({ ...o, ...s }));
      setFs(inFullscreen());
      setPhase("running");
      await loadQuestion(s.current_index);
    } catch (e) { await leaveFullscreen(); setErr(msg(e)); } finally { setBusy(false); }
  };

  const go = async (to) => {
    setBusy(true);
    try {
      await X.answer(id, q.question_id, chosen ?? null);
      if (to >= q.total) { await X.submit(id); await finish(); return; }
      await loadQuestion(to);
    } catch (e) { setErr(msg(e)); } finally { setBusy(false); }
  };
  const submitNow = useCallback(async () => {
    setBusy(true);
    try { await X.submit(id); } catch { /* already closed */ }
    setBusy(false);
    finish();
  }, [id, finish]);
  const backToFs = async () => { await enterFullscreen(); setFs(inFullscreen()); };

  const mark = watermarkStyle(`${user?.name || ""} · ${user?.phone || ""}`);

  if (err && (phase === "loading" || phase === "blocked")) return <Shell><main className="xi"><Banner tone="err">{err}</Banner></main></Shell>;
  if (phase === "loading") return <Shell back={false}><main className="xi"><p className="field-msg">جارٍ التحميل…</p></main></Shell>;

  if (phase === "blocked")
    return (
      <Shell>
        <main className="xi">
          <div className="xi-card">
            <h1>{info.title}</h1>
            <Banner tone="info">{info.state === "upcoming" ? `لم يبدأ هذا الامتحان بعد. يبدأ ${fmt(info.opens_at)}.` : "انتهى موعد هذا الامتحان. إن فاتك لسبب خارج عن إرادتك تواصل مع معلمك."}</Banner>
            <Link className="abtn abtn-ghost" to="/learn/exams">رجوع للامتحانات</Link>
          </div>
        </main>
      </Shell>
    );

  if (phase === "intro")
    return (
      <Shell>
        <main className="xi">
          <div className="xi-card">
            {retake && <p className="xi-retake"><RotateCcw size={15} /> محاولة جديدة — تُحتسب لك أعلى درجة بين كل محاولاتك</p>}
            <h1>{info.title}</h1>
            <ul className="xi-facts">
              <li><ListChecks size={16} /> {nAr(info.question_count)} سؤال</li>
              <li><Clock size={16} /> {nAr(info.duration_minutes)} دقيقة</li>
              <li><ShieldAlert size={16} /> {warningsText(info.max_violations || 3)}</li>
            </ul>
            <div className="xi-rules"><b>قبل أن تبدأ</b><ul>{RULES(info).map((r) => <li key={r}>{r}</li>)}</ul></div>
            {!fullscreenSupported() && <Banner tone="info">متصفحك لا يدعم الشاشة الكاملة. سيستمر رصد ترك الصفحة وتبديل التبويب.</Banner>}
            {err && <Banner tone="err">{err}</Banner>}
            <Btn onClick={begin} loading={busy}>{info.state === "in_progress" ? "استكمال الامتحان" : retake ? "ابدأ المحاولة الجديدة" : "ابدأ الامتحان"}</Btn>
            <Link className="dash-linkish" to="/learn/exams">رجوع</Link>
          </div>
        </main>
      </Shell>
    );

  if (phase === "done") {
    const ok = result && !result.error;
    const b = band(result?.percent);
    return (
      <Shell>
        <main className="xd">
          {!ok ? <Banner tone="err">{result?.error || "تعذّر عرض النتيجة."}</Banner> : (
            <>
              <section className={"xd-card " + b.cls}>
                <p className="xd-title">{result.title}</p>
                <Ring percent={result.percent} size={176} label={`نتيجتك ${pctText(result.percent)}`} />
                <h1>{b.label}</h1>
                <p className="xd-score">{nAr(result.score)} من {nAr(result.max_score)} درجة</p>
                <dl className="xd-stats">
                  <div><dt>المحاولة</dt><dd>{nAr(result.attempt_number)}</dd></div>
                  <div><dt>التحذيرات</dt><dd>{nAr(result.violations)}</dd></div>
                  {result.attempts > 1 && <div><dt>أعلى نتيجة</dt><dd>{pctText(result.best_percent)}</dd></div>}
                </dl>
                {result.attempts > 1 && (
                  <p className="xd-best">{result.is_best ? "هذه أعلى درجة حصلت عليها، وهي المحسوبة لك." : `المحسوبة لك أعلى درجة: ${pctText(result.best_percent)} من محاولة سابقة.`}</p>
                )}
              </section>
              {result.end_reason === "violations" && (
                <Note tone="bad">أُغلق الامتحان تلقائيًا لأنك تجاوزت عدد التحذيرات المسموح، وسُلّمت إجاباتك. إن حدثت مشكلة فنية تواصل مع معلمك؛ يستطيع إعادة فتح الامتحان لك.</Note>
              )}
              {result.end_reason === "time" && <Note>انتهى الوقت وتم تسليم إجاباتك تلقائيًا.</Note>}
              {result.can_retake && (
                <div className="xd-retake">
                  <p>أتاح لك معلمك محاولة أخرى. تُحتسب لك أعلى درجة بين المحاولتين.</p>
                  <Btn onClick={() => { setRetake(true); setResult(null); setErr(null); setInfo((i) => ({ ...i, state: "open" })); setPhase("intro"); }}>ابدأ محاولة جديدة</Btn>
                </div>
              )}
              {result.review && (
                <div className="xd-review">
                  <h2>مراجعة الإجابات</h2>
                  {result.review.map((r, i) => (
                    <div key={i} className="xq"><b>{nAr(i + 1)}. {r.text}</b>
                      {r.choices.map((c, j) => <div key={j} className={"xrev" + (c.is_correct ? " is-right" : c.chosen ? " is-wrong" : "")}>{c.text}{c.chosen ? " ← إجابتك" : ""}</div>)}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
          <Btn variant="ghost" onClick={() => nav("/learn/exams", { replace: true })}>رجوع للامتحانات</Btn>
        </main>
      </Shell>
    );
  }

  // ---- running
  const total = q?.total || st?.total || 0;
  const index = q?.index ?? 0;
  const reached = st?.current_index ?? 0;
  const pct = progressPct(index, total);
  const last = q && q.index + 1 === q.total;
  const needFs = fullscreenSupported() && !fs && !warn && !confirming;
  return (
    <div className="xs-shell is-run">
      <div className="xr-mark" style={mark} aria-hidden="true" />
      <header className="xr-top">
        <div className="xr-title"><b>{st.title || info.title}</b>{st.number > 1 && <span>المحاولة {nAr(st.number)}</span>}</div>
        <Countdown deadline={st.deadline_at} onEnd={submitNow} />
        <Strikes used={st.violations || 0} max={st.max_violations || info.max_violations || 3} />
      </header>
      <div className="xr-progress" role="progressbar" aria-label="تقدّمك في الامتحان" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}><i style={{ inlineSize: `${pct}%` }} /></div>
      <main className="xr-main">
        <div className="xr-meter"><span>السؤال {nAr(index + 1)} من {nAr(total)}</span><b>{pctText(Math.round(pct))} مكتمل</b></div>
        {toast && <div className="xr-toast" role="status">{toast}</div>}
        {err && <Banner tone="err">{err}</Banner>}
        {q && (
          <section className="xr-card" aria-live="polite">
            <div className="xr-qhead"><span className="xr-qno">سؤال {nAr(index + 1)}</span><span className="xr-pts">{nAr(q.points)} {q.points === 1 ? "درجة" : "درجات"}</span></div>
            <p className="xr-text">{q.text}</p>
            <div className="xr-choices" role="radiogroup" aria-label="الاختيارات">
              {q.choices.map((c, i) => (
                <button key={c.id} type="button" role="radio" aria-checked={chosen === c.id} className={"xr-choice" + (chosen === c.id ? " is-on" : "")} onClick={() => setChosen(c.id)}>
                  <span className="xr-letter" aria-hidden="true">{CHOICE_LETTERS[i]}</span>
                  <span className="xr-ctext">{c.text}</span>
                </button>
              ))}
            </div>
          </section>
        )}
        <QuestionMap total={total} index={index} reached={reached} canJump={Boolean(st.allow_back)} onJump={(i) => go(i)} />
        {!st.allow_back && <p className="xr-hint"><Lock size={13} /> لا يمكن الرجوع إلى سؤال سابق بعد الانتقال.</p>}
      </main>
      <footer className="xr-actions">
        <button type="button" className="xr-quit" onClick={() => setConfirming(true)}>تسليم الآن</button>
        <div className="xr-actions-main">
          {st.allow_back && index > 0 && <Btn variant="ghost" onClick={() => go(index - 1)} disabled={busy}><ChevronRight size={16} /> السابق</Btn>}
          <Btn onClick={() => go(index + 1)} loading={busy} disabled={!q}>{last ? "إنهاء وتسليم" : <>التالي <ChevronLeft size={16} /></>}</Btn>
        </div>
      </footer>
      {warn && <WarningOverlay info={warn} deadline={st.deadline_at} onContinue={async () => { await backToFs(); setWarn(null); }} />}
      {needFs && <NeedFullscreen onEnter={backToFs} />}
      {confirming && !warn && <SubmitSheet left={total - index} busy={busy} onYes={submitNow} onNo={() => setConfirming(false)} />}
    </div>
  );
}
