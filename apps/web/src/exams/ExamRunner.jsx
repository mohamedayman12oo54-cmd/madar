import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Maximize, Send } from "lucide-react";
import { Btn } from "../auth/ui.jsx";
import { examsApi } from "../lib/examsApi.js";
import {
  KINDS,
  classifyKey,
  createRateGate,
  formatClock,
  remainingSeconds,
  watermarkLabel,
} from "../lib/examGuard.js";
import { enterFullscreen, fullscreenSupported, isFullscreen } from "./fullscreen.js";
import "./exams.css";

const LETTERS = ["أ", "ب", "ج", "د", "هـ", "و"];

/** The locked-down exam view.
 *
 *  What it does, honestly: it fills the screen, shows one question at a time, blocks copy / paste / cut /
 *  context menu / print / selection / drag / the usual developer-tool and screenshot keys, notices when
 *  the student leaves (full screen exit, another tab, another window) and reports it, covers the paper
 *  while they are away, tiles their name over the paper, and ends the exam by itself at the teacher's
 *  violation limit. What no web page can do: stop a phone camera or an operating-system screenshot tool.
 *  The server keeps the clock and the log either way. */
export default function ExamRunner({ examId, payload, resumed, student, onFinished }) {
  const { attempt, questions, title } = payload;
  const needFs = useMemo(() => fullscreenSupported(), []);
  const fetchedAt = useRef(Date.now());
  const finished = useRef(false);
  const gate = useRef(createRateGate(2500));
  const unsaved = useRef(new Map()); // question id -> choice id still to be written
  const [answers, setAnswers] = useState(() =>
    Object.fromEntries(questions.filter((q) => q.chosen != null).map((q) => [q.id, q.chosen]))
  );
  const [idx, setIdx] = useState(0);
  const [away, setAway] = useState(false);
  const [strikes, setStrikes] = useState(attempt.violations || 0);
  const [alertText, setAlertText] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [saveWarn, setSaveWarn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(() =>
    remainingSeconds({
      deadline: attempt.deadline_at,
      serverNow: payload.server_now,
      fetchedAtMs: fetchedAt.current,
    })
  );

  const finish = useCallback(
    (reason) => {
      if (finished.current) return;
      finished.current = true;
      onFinished(reason);
    },
    [onFinished]
  );

  // ---- reporting integrity signals --------------------------------------------------------------
  const report = useCallback(
    (kind) => {
      if (finished.current || !gate.current(kind)) return;
      examsApi.student
        .event(examId, kind)
        .then((r) => {
          setStrikes(r.violations);
          if (r.submitted) return finish(r.submit_reason);
          if (r.counted) {
            setAlertText(
              `سُجّلت مخالفة (${r.violations} من ${r.max_violations}). عند الوصول إلى ${r.max_violations} يُسلَّم الامتحان تلقائيًا.`
            );
          }
        })
        .catch((e) => {
          // the attempt is already over on the server (time ran out, or it was submitted elsewhere)
          if (e?.status === 404 || e?.status === 409) finish("time");
        });
    },
    [examId, finish]
  );

  // ---- the lock-down: listeners live exactly as long as the exam is on screen --------------------
  useEffect(() => {
    if (resumed) report(KINDS.RESUMED);
    const stop = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };
    const leave = (kind) => () => {
      setAway(true);
      report(kind);
    };
    const onFullscreen = () => {
      if (needFs && !isFullscreen()) {
        setAway(true);
        report(KINDS.FULLSCREEN_EXIT);
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") leave(KINDS.TAB_HIDDEN)();
    };
    const onKey = (e) => {
      const { block, event } = classifyKey(e);
      if (block) stop(e);
      if (event) report(event);
    };
    const onKeyUp = (e) => {
      if (e.key === "PrintScreen") {
        report(KINDS.SCREENSHOT);
        // best effort: replace whatever the screenshot put on the clipboard
        navigator.clipboard?.writeText?.("").catch(() => {});
      }
    };
    const onContext = (e) => {
      stop(e);
      report(KINDS.CONTEXT_MENU);
    };
    const onCopy = (e) => {
      stop(e);
      e.clipboardData?.setData("text/plain", "");
      report(KINDS.COPY);
    };
    const onPaste = (e) => {
      stop(e);
      report(KINDS.PASTE);
    };
    const onBeforeUnload = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    // the back button must not leave the exam
    window.history.pushState({ exam: true }, "", window.location.href);
    const onPop = () => window.history.pushState({ exam: true }, "", window.location.href);
    const onPrint = () => report(KINDS.PRINT);

    const blur = leave(KINDS.WINDOW_BLUR);
    document.addEventListener("fullscreenchange", onFullscreen);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", blur);
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("keyup", onKeyUp, true);
    document.addEventListener("contextmenu", onContext, true);
    document.addEventListener("copy", onCopy, true);
    document.addEventListener("cut", onCopy, true);
    document.addEventListener("paste", onPaste, true);
    document.addEventListener("dragstart", stop, true);
    document.addEventListener("selectstart", stop, true);
    window.addEventListener("beforeunload", onBeforeUnload);
    window.addEventListener("popstate", onPop);
    window.addEventListener("beforeprint", onPrint);
    return () => {
      document.removeEventListener("fullscreenchange", onFullscreen);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", blur);
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("keyup", onKeyUp, true);
      document.removeEventListener("contextmenu", onContext, true);
      document.removeEventListener("copy", onCopy, true);
      document.removeEventListener("cut", onCopy, true);
      document.removeEventListener("paste", onPaste, true);
      document.removeEventListener("dragstart", stop, true);
      document.removeEventListener("selectstart", stop, true);
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("beforeprint", onPrint);
    };
  }, [needFs, report, resumed]);

  // ---- the clock (the server's deadline, corrected for this device's clock) -----------------------
  useEffect(() => {
    const t = setInterval(() => {
      const s = remainingSeconds({
        deadline: attempt.deadline_at,
        serverNow: payload.server_now,
        fetchedAtMs: fetchedAt.current,
      });
      setLeft(s);
      if (s <= 0) {
        examsApi.student
          .submit(examId)
          .catch(() => {})
          .finally(() => finish("time"));
      }
    }, 1000);
    return () => clearInterval(t);
  }, [attempt.deadline_at, payload.server_now, examId, finish]);

  // ---- answers: written as they are chosen; failures are retried until they land -----------------
  const write = useCallback(
    (qid, cid) =>
      examsApi.student
        .answer(examId, qid, cid)
        .then(() => {
          if (unsaved.current.get(qid) === cid) unsaved.current.delete(qid);
          setSaveWarn(unsaved.current.size > 0);
        })
        .catch((e) => {
          if (e?.status === 409 || e?.status === 404) return finish("time");
          unsaved.current.set(qid, cid);
          setSaveWarn(true);
        }),
    [examId, finish]
  );
  const choose = (qid, cid) => {
    setAnswers((a) => ({ ...a, [qid]: cid }));
    unsaved.current.set(qid, cid);
    write(qid, cid);
  };
  useEffect(() => {
    const t = setInterval(() => unsaved.current.forEach((cid, qid) => write(qid, cid)), 4000);
    return () => clearInterval(t);
  }, [write]);

  const submit = async () => {
    setBusy(true);
    await Promise.all([...unsaved.current].map(([qid, cid]) => write(qid, cid)));
    try {
      await examsApi.student.submit(examId);
    } catch {
      /* the server settles the attempt when time is up even if this call never lands */
    }
    finish("manual");
  };

  const back = async () => {
    if (needFs) {
      try {
        await enterFullscreen();
      } catch {
        return;
      }
    }
    setAway(false);
  };

  const q = questions[idx];
  const answered = questions.filter((x) => answers[x.id] != null).length;
  const label = useMemo(() => watermarkLabel(student?.name, student?.phone), [student]);
  const lowClass = left <= 60 ? " crit" : left <= 300 ? " low" : "";

  return (
    <div className="ex-run" role="dialog" aria-modal="true" aria-label={title}>
      <header className="ex-run-top">
        <div className="ex-run-title">{title}</div>
        <span className={"ex-strikes" + (strikes > 0 ? " hot" : "")} aria-live="polite">
          المخالفات{" "}
          <span className="num" dir="ltr" style={{ unicodeBidi: "isolate-override" }}>
            {`${strikes} / ${attempt.max_violations}`}
          </span>
        </span>
        <span className={"ex-timer" + lowClass} role="timer" dir="ltr" aria-label="الوقت المتبقي">
          {formatClock(left)}
        </span>
      </header>

      <div className="ex-run-body">
        {label && (
          <div className="ex-wm" aria-hidden="true">
            <div className="ex-wm-grid">
              {Array.from({ length: 60 }, (_, i) => (
                <span key={i}>{label}</span>
              ))}
            </div>
          </div>
        )}

        {away ? (
          <div className="ex-cover">
            <div className="ex-cover-card">
              <AlertTriangle size={36} aria-hidden="true" />
              <h3>غادرت شاشة الامتحان</h3>
              <p>
                سُجّل ذلك على امتحانك، والوقت ما زال يعمل. ارجع الآن لتكمل. عند الوصول إلى{" "}
                <bdi>{attempt.max_violations}</bdi> مخالفات يُسلَّم الامتحان تلقائيًا.
              </p>
              <Btn onClick={back}>
                <Maximize size={16} /> العودة إلى الامتحان
              </Btn>
            </div>
          </div>
        ) : confirming ? (
          <div className="ex-cover">
            <div className="ex-cover-card">
              <Send size={34} aria-hidden="true" />
              <h3>تسليم الامتحان؟</h3>
              <p>
                أجبت عن <bdi>{answered}</bdi> من <bdi>{questions.length}</bdi> سؤالًا.
                {answered < questions.length && " الأسئلة بلا إجابة تُحسب صفرًا."} لا يمكنك التعديل
                بعد التسليم.
              </p>
              {saveWarn && (
                <p className="ex-savewarn">بعض الإجابات لم تُحفظ بعد، سنحاول حفظها قبل التسليم.</p>
              )}
              <div className="ex-add-row" style={{ justifyContent: "center" }}>
                <Btn variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>
                  عودة للأسئلة
                </Btn>
                <Btn onClick={submit} loading={busy} loadingText="جارٍ التسليم…">
                  سلّم الآن
                </Btn>
              </div>
            </div>
          </div>
        ) : (
          <div className="ex-paper" style={{ position: "relative", zIndex: 1 }}>
            {alertText && (
              <div className="banner err" role="alert">
                <AlertTriangle className="bi" size={17} />
                {alertText}
              </div>
            )}
            <div className="stat-sub">
              السؤال <bdi>{idx + 1}</bdi> من <bdi>{questions.length}</bdi> • <bdi>{q.points}</bdi>{" "}
              درجة
            </div>
            <div className="ex-qtext">{q.text}</div>
            <div role="radiogroup" aria-label="الاختيارات" style={{ display: "grid", gap: 10 }}>
              {q.choices.map((c, i) => (
                <button
                  key={c.id}
                  type="button"
                  role="radio"
                  aria-checked={answers[q.id] === c.id}
                  className="ex-opt"
                  onClick={() => choose(q.id, c.id)}
                >
                  <span className="mark" aria-hidden="true">
                    {LETTERS[i]}
                  </span>
                  <span className="txt">{c.text}</span>
                </button>
              ))}
            </div>
            {saveWarn && (
              <div className="ex-savewarn">
                تعذّر حفظ بعض الإجابات، نعيد المحاولة تلقائيًا. تأكد من اتصالك.
              </div>
            )}
            <div className="ex-nav">
              <button
                type="button"
                className="mini-btn"
                disabled={idx === 0}
                onClick={() => setIdx(idx - 1)}
              >
                <ChevronRight size={14} /> السابق
              </button>
              {idx < questions.length - 1 ? (
                <button
                  type="button"
                  className="mini-btn is-primary"
                  onClick={() => setIdx(idx + 1)}
                >
                  التالي <ChevronLeft size={14} />
                </button>
              ) : (
                <button
                  type="button"
                  className="mini-btn is-primary"
                  onClick={() => setConfirming(true)}
                >
                  <Send size={13} /> إنهاء وتسليم
                </button>
              )}
            </div>
            <div className="ex-dots" role="group" aria-label="التنقل بين الأسئلة">
              {questions.map((x, i) => (
                <button
                  key={x.id}
                  type="button"
                  className={"ex-dot" + (i === idx ? " now" : answers[x.id] != null ? " done" : "")}
                  aria-label={`السؤال ${i + 1}${answers[x.id] != null ? "، تمت الإجابة" : ""}`}
                  aria-current={i === idx ? "true" : undefined}
                  onClick={() => setIdx(i)}
                >
                  {i + 1}
                </button>
              ))}
            </div>
            <div style={{ textAlign: "center" }}>
              <button type="button" className="mini-btn" onClick={() => setConfirming(true)}>
                <Send size={13} /> تسليم الامتحان
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
