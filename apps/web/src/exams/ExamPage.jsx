import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, CheckCircle2, Lock, XCircle } from "lucide-react";
import { Banner, Btn } from "../auth/ui.jsx";
import { PageHeader, fmtDateTime } from "../dashboard/common.jsx";
import { useSession } from "../state/session.jsx";
import { examsApi } from "../lib/examsApi.js";
import { ApiError } from "../lib/api.js";
import { EXAM_STATUS } from "../lib/examGuard.js";
import ExamRunner from "./ExamRunner.jsx";
import { enterFullscreen, exitFullscreen, fullscreenSupported } from "./fullscreen.js";
import "./exams.css";

const REASON = {
  manual: "",
  time: "انتهى الوقت فسُلّم امتحانك تلقائيًا.",
  violations: "سُلّم امتحانك تلقائيًا لأنك تجاوزت حد المخالفات.",
};

const Frac = ({ a, b }) => (
  <span className="num" dir="ltr" style={{ unicodeBidi: "isolate-override" }}>
    {`${a} / ${b}`}
  </span>
);

function Review({ review, chosenLabel = "إجابتك" }) {
  return (
    <div className="ex-review">
      <h4 className="form-section-title">مراجعة الإجابات</h4>
      {review.map((q, i) => (
        <div key={q.id} className="ex-rq">
          <p>
            <bdi>{i + 1}</bdi>. {q.text}
          </p>
          {q.choices.map((c) => {
            const right = c.id === q.correct_choice_id;
            const mine = c.id === q.chosen_choice_id;
            return (
              <div key={c.id} className={"ex-ra" + (right ? " right" : mine ? " wrong" : "")}>
                {right ? <CheckCircle2 size={15} /> : mine ? <XCircle size={15} /> : null}
                <span>{c.text}</span>
                {mine && <span className="chip-s">{chosenLabel}</span>}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

/** One exam as the student meets it: the rules and a start button, the exam itself (locked view), and
 *  afterwards the result. Questions are only ever requested after the student presses start. */
export default function ExamPage() {
  const { id } = useParams();
  const { user } = useSession();
  const [info, setInfo] = useState(null);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState(null);
  const [startErr, setStartErr] = useState(null);
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [endNote, setEndNote] = useState(null);

  const load = useCallback(async () => {
    try {
      const i = await examsApi.student.get(id);
      setInfo(i);
      setErr(null);
      if (i.status === "submitted") setResult(await examsApi.student.result(id));
    } catch (e) {
      setErr(e instanceof ApiError && e.status !== 404 ? e.message : "هذا الامتحان غير متاح لك.");
    }
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);

  const begin = async () => {
    setStartErr(null);
    setBusy(true);
    // Full screen can only be requested from a tap, so it comes first.
    if (fullscreenSupported()) {
      try {
        await enterFullscreen();
      } catch {
        setStartErr(
          "يجب السماح بوضع ملء الشاشة لبدء الامتحان. اضغط «ابدأ» مرة أخرى ووافق عند الطلب."
        );
        setBusy(false);
        return;
      }
    }
    try {
      const d = await examsApi.student.start(id);
      if (d.attempt.submitted) {
        await exitFullscreen();
        await load();
      } else {
        setRun({ payload: d, resumed: info.status === "in_progress" });
      }
    } catch (e) {
      await exitFullscreen();
      setStartErr(e instanceof ApiError ? e.message : "تعذّر بدء الامتحان.");
    } finally {
      setBusy(false);
    }
  };

  const finished = useCallback(
    async (reason) => {
      setRun(null);
      setEndNote(REASON[reason] || "");
      await exitFullscreen();
      await load();
    },
    [load]
  );

  if (run) {
    return (
      <ExamRunner
        examId={id}
        payload={run.payload}
        resumed={run.resumed}
        student={{ name: user?.name, phone: user?.phone }}
        onFinished={finished}
      />
    );
  }

  const st = info && EXAM_STATUS[info.status];
  return (
    <>
      <PageHeader infoKey="student_exams" title={info?.title || "الامتحان"}>
        <Link to="/learn/videos" className="mini-btn">
          <ArrowRight size={13} /> كل المحتوى
        </Link>
      </PageHeader>
      {err && <Banner tone="err">{err}</Banner>}
      {!info && !err && <p className="field-msg">جاري التحميل...</p>}
      {info && (
        <div className="ex-card">
          <div>
            <span className={"chip-s " + (st?.tone || "")}>{st?.label}</span>
          </div>
          {info.description && (
            <p style={{ margin: 0, lineHeight: 1.9, whiteSpace: "pre-wrap" }}>{info.description}</p>
          )}
          <div className="ex-facts">
            <div className="ex-fact">
              <div className="k">المدة</div>
              <div className="v">
                <bdi>{info.duration_minutes}</bdi> دقيقة
              </div>
            </div>
            <div className="ex-fact">
              <div className="k">عدد الأسئلة</div>
              <div className="v">
                <bdi>{info.question_count}</bdi>
              </div>
            </div>
            <div className="ex-fact">
              <div className="k">الدرجة الكلية</div>
              <div className="v">
                <bdi>{info.total_points}</bdi>
              </div>
            </div>
            <div className="ex-fact">
              <div className="k">يُغلق</div>
              <div className="v" style={{ fontSize: "0.85rem" }}>
                {fmtDateTime(info.closes_at)}
              </div>
            </div>
          </div>

          {endNote && <Banner tone="info">{endNote}</Banner>}
          {startErr && <Banner tone="err">{startErr}</Banner>}

          {(info.status === "open" || info.status === "in_progress") && (
            <>
              <ul className="ex-rules">
                <li>
                  تكون محاولتك واحدة فقط، والوقت يعمل من لحظة البدء ولا يتوقف إن أغلقت الصفحة.
                </li>
                <li>يفتح الامتحان بملء الشاشة. ممنوع النسخ واللصق والطباعة وأخذ لقطات للشاشة.</li>
                <li>
                  أي خروج من الشاشة أو انتقال لتبويب أو نافذة أخرى يُسجَّل مخالفة، ويُسلَّم امتحانك
                  تلقائيًا عند <bdi>{info.max_violations}</bdi> مخالفات.
                </li>
                <li>اسمك مكتوب بخط خفيف على الأسئلة، وأي صورة تُسرَّب تدل عليك.</li>
                <li>إجاباتك تُحفظ أولًا بأول، ولا تفقد ما أجبت إن انقطع الاتصال.</li>
              </ul>
              <Btn onClick={begin} loading={busy} loadingText="جارٍ التحضير…">
                <Lock size={16} />{" "}
                {info.status === "in_progress" ? "أكمل الامتحان" : "ابدأ الامتحان"}
              </Btn>
            </>
          )}
          {info.status === "upcoming" && (
            <Banner tone="info">يفتح الامتحان في {fmtDateTime(info.opens_at)}.</Banner>
          )}
          {info.status === "missed" && (
            <Banner tone="err">انتهى موعد هذا الامتحان ولم تبدأه.</Banner>
          )}

          {info.status === "submitted" && result && (
            <>
              {result.score !== null ? (
                <div className="ex-score">
                  <div className="stat-sub">درجتك</div>
                  <div className="big">
                    <Frac a={result.score} b={result.max_score} />
                  </div>
                </div>
              ) : (
                <Banner tone="info">
                  تم تسليم امتحانك. ستظهر الدرجة بعد انتهاء موعد الامتحان.
                </Banner>
              )}
              {result.violations > 0 && (
                <p className="stat-sub" style={{ margin: 0 }}>
                  سُجّلت عليك <bdi>{result.violations}</bdi> مخالفة أثناء الامتحان، ويراها معلمك.
                </p>
              )}
              {result.review && <Review review={result.review} />}
              {result.score !== null && !result.review && (
                <p className="stat-sub" style={{ margin: 0 }}>
                  قد يعرض لك معلمك الإجابات الصحيحة بعد إغلاق الامتحان.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
