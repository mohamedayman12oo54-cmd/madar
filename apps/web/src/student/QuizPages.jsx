import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  ClipboardCheck,
  FileQuestion,
  Send,
  XCircle,
} from "lucide-react";
import { Banner, Btn } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty, fmtDateTime } from "../dashboard/common.jsx";
import "./quiz.css";
import { clearDraft, readDraft, writeDraft } from "../lib/quizDraft.js";

/* ==========================================================================
   Helpers
   ========================================================================== */

const LETTERS = ["أ", "ب", "ج", "د", "هـ", "و"];

/** Numbers and fractions must stay left-to-right inside an RTL sentence,
 *  otherwise "6 / 8" is drawn as "8 / 6". */
const Fraction = ({ value, total }) => (
  <bdi className="num">
    {value} / {total}
  </bdi>
);

const percentOf = (score, total) => (total ? Math.round((score / total) * 100) : 0);
const isSolved = (quiz) => quiz.score !== null && quiz.score !== undefined;

function verdictFor(percent) {
  if (percent >= 90)
    return { tone: "great", title: "ممتاز! أداء رائع", text: "استمر على هذا المستوى." };
  if (percent >= 75)
    return { tone: "good", title: "جيد جدًا", text: "قريب من الدرجة الكاملة، راجع ما أخطأت فيه." };
  if (percent >= 50)
    return { tone: "ok", title: "جيد", text: "راجع الأخطاء أدناه لتتحسّن في المرة القادمة." };
  return { tone: "low", title: "تحتاج مراجعة", text: "أعد مشاهدة الدرس ثم جرّب اختبارًا جديدًا." };
}

const errorText = (e, fallback) =>
  e instanceof ApiError
    ? e.fields
      ? Object.values(e.fields).flat().join(" ")
      : e.message
    : fallback;

/* ==========================================================================
   Small building blocks
   ========================================================================== */

function ScoreRing({ score, total, size = "md" }) {
  const percent = percentOf(score, total);
  return (
    <div
      className={`qz-ring qz-ring-${size}`}
      role="img"
      aria-label={`${score} من ${total} (${percent}%)`}
    >
      <svg viewBox="0 0 36 36" aria-hidden="true">
        <circle className="qz-ring-track" cx="18" cy="18" r="15.915" pathLength="100" />
        <circle
          className="qz-ring-fill"
          cx="18"
          cy="18"
          r="15.915"
          pathLength="100"
          strokeDasharray={`${percent} 100`}
        />
      </svg>
      <div className="qz-ring-text">
        <strong className="num">{percent}%</strong>
        {size === "lg" && (
          <span>
            <Fraction value={score} total={total} />
          </span>
        )}
      </div>
    </div>
  );
}

function QuizBack() {
  return (
    <Link className="qz-back" to="/learn/quizzes">
      <ArrowRight size={18} aria-hidden="true" />
      العودة لاختباراتي
    </Link>
  );
}

function QuizHeader({ title }) {
  return (
    <header className="qz-head">
      <QuizBack />
      <h1 className="qz-title">{title}</h1>
    </header>
  );
}

/* ==========================================================================
   Quiz list
   ========================================================================== */

const FILTERS = [
  { key: "all", label: "الكل" },
  { key: "todo", label: "لم تُحل" },
  { key: "done", label: "تم حلها" },
];

function QuizRow({ quiz }) {
  const solved = isSolved(quiz);
  const total = quiz.total ?? quiz.questions;
  const tone = solved ? verdictFor(percentOf(quiz.score, total)).tone : "";
  return (
    <Link to={`/learn/quizzes/${quiz.id}`} className={"qz-row" + (tone ? ` is-${tone}` : "")}>
      {solved ? (
        <ScoreRing score={quiz.score} total={total} size="sm" />
      ) : (
        <span className="qz-row-icon" aria-hidden="true">
          <FileQuestion size={22} />
        </span>
      )}
      <span className="qz-row-main">
        <strong>{quiz.title || "اختبار"}</strong>
        <span className="qz-row-meta">
          <span>{fmtDateTime(quiz.created_at)}</span>
          <span aria-hidden="true">•</span>
          <span>{quiz.questions} أسئلة</span>
        </span>
      </span>
      <span className="qz-row-end">
        {solved ? (
          <span className="chip-s good">
            <Fraction value={quiz.score} total={total} />
          </span>
        ) : (
          <span className="chip-s warn">ابدأ الآن</span>
        )}
        <ChevronLeft size={18} aria-hidden="true" className="qz-row-chevron" />
      </span>
    </Link>
  );
}

function FilterTabs({ label, options, value, onChange }) {
  return (
    <div className="qz-filter" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          role="tab"
          aria-selected={value === o.key}
          className={value === o.key ? "is-active" : ""}
          onClick={() => onChange(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function QuizzesPage() {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    studentApi.quizzes
      .list()
      .then((d) => setItems(d.results))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل الاختبارات."));
  }, []);

  const stats = useMemo(() => {
    const solved = (items || []).filter(isSolved);
    const points = solved.reduce((sum, q) => sum + (q.total ? q.score / q.total : 0), 0);
    return {
      total: items?.length ?? 0,
      solved: solved.length,
      average: solved.length ? Math.round((points / solved.length) * 100) : null,
    };
  }, [items]);

  const visible = useMemo(() => {
    if (filter === "todo") return (items || []).filter((q) => !isSolved(q));
    if (filter === "done") return (items || []).filter(isSolved);
    return items || [];
  }, [items, filter]);

  return (
    <>
      <PageHeader infoKey="student_quizzes" title="اختباراتي" />
      {err && <Banner tone="err">{err}</Banner>}
      {!items && !err && <p className="field-msg">جاري التحميل...</p>}

      {items && items.length === 0 && (
        <Empty
          title="لا توجد اختبارات بعد"
          text="اطلب اختبارًا على أي فيديو من صفحة «الفيديوهات»."
        />
      )}

      {items && items.length > 0 && (
        <>
          <div className="qz-stats">
            <div>
              <strong className="num">{stats.total}</strong>
              <span>اختبار</span>
            </div>
            <div>
              <strong className="num">{stats.solved}</strong>
              <span>تم حلها</span>
            </div>
            <div>
              <strong className="num">{stats.average === null ? "—" : `${stats.average}%`}</strong>
              <span>متوسط الدرجات</span>
            </div>
          </div>

          <FilterTabs
            label="تصفية الاختبارات"
            options={FILTERS}
            value={filter}
            onChange={setFilter}
          />

          {visible.length === 0 ? (
            <p className="qz-none">لا توجد اختبارات في هذا التصنيف.</p>
          ) : (
            <div className="qz-list">
              {visible.map((q) => (
                <QuizRow key={q.id} quiz={q} />
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}

/* ==========================================================================
   Taking a quiz: one question at a time, then a review step
   ========================================================================== */

function QuestionStep({ question, index, total, answer, onPick, headingRef }) {
  const name = `q${index}`;
  return (
    <section className="qz-card" aria-labelledby={`${name}-title`}>
      <p className="qz-qno">
        سؤال <bdi className="num">{index + 1}</bdi> من <bdi className="num">{total}</bdi>
      </p>
      <h2 id={`${name}-title`} className="qz-q" tabIndex={-1} ref={headingRef}>
        {question.q}
      </h2>
      <div className="qz-options" role="radiogroup" aria-labelledby={`${name}-title`}>
        {question.options.map((option, oi) => {
          const selected = answer === oi;
          return (
            <label key={oi} className={"qz-opt" + (selected ? " is-selected" : "")}>
              <input
                type="radio"
                className="qz-opt-input"
                name={name}
                checked={selected}
                onChange={() => onPick(oi)}
              />
              <span className="qz-opt-mark" aria-hidden="true">
                {selected ? <Check size={16} strokeWidth={3} /> : (LETTERS[oi] ?? oi + 1)}
              </span>
              <span className="qz-opt-text">{option}</span>
            </label>
          );
        })}
      </div>
    </section>
  );
}

function QuestionDots({ answers, step, onGo }) {
  const refs = useRef([]);
  useEffect(() => {
    refs.current[step]?.scrollIntoView?.({ inline: "center", block: "nearest" });
  }, [step]);
  return (
    <nav className="qz-dots" aria-label="التنقل بين الأسئلة">
      {answers.map((a, i) => (
        <button
          key={i}
          type="button"
          ref={(el) => {
            refs.current[i] = el;
          }}
          className={
            "qz-dot" + (a !== null ? " is-answered" : "") + (i === step ? " is-current" : "")
          }
          aria-current={i === step ? "step" : undefined}
          aria-label={`السؤال ${i + 1}${a !== null ? " — تمت الإجابة" : " — بلا إجابة"}`}
          onClick={() => onGo(i)}
        >
          {i + 1}
        </button>
      ))}
    </nav>
  );
}

function ReviewStep({ answers, saving, error, onGo, onSubmit }) {
  const missing = answers.map((a, i) => (a === null ? i : -1)).filter((i) => i >= 0);
  return (
    <section className="qz-card" aria-labelledby="qz-review-title">
      <span className="qz-review-icon" aria-hidden="true">
        <ClipboardCheck size={26} />
      </span>
      <h2 id="qz-review-title" className="qz-q">
        مراجعة قبل التسليم
      </h2>
      <p className="qz-review-sub">
        أجبت عن <bdi className="num">{answers.length - missing.length}</bdi> من{" "}
        <bdi className="num">{answers.length}</bdi> أسئلة. اضغط على أي رقم للرجوع إليه.
      </p>

      <div className="qz-review-grid">
        {answers.map((a, i) => (
          <button
            key={i}
            type="button"
            className={"qz-dot qz-dot-lg" + (a !== null ? " is-answered" : "")}
            aria-label={`السؤال ${i + 1}${a !== null ? " — تمت الإجابة" : " — بلا إجابة"}`}
            onClick={() => onGo(i)}
          >
            {i + 1}
          </button>
        ))}
      </div>

      {missing.length > 0 && (
        <div className="qz-warn" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>
            {missing.length === 1 ? "سؤال واحد بلا إجابة" : `${missing.length} أسئلة بلا إجابة`} —
            ستُحسب خاطئة إذا سلّمت الآن.
          </span>
        </div>
      )}
      {error && <Banner tone="err">{error}</Banner>}

      <div className="qz-review-actions">
        {missing.length > 0 && (
          <Btn variant="secondary" onClick={() => onGo(missing[0])}>
            الذهاب لأول سؤال بلا إجابة
          </Btn>
        )}
        <Btn loading={saving} loadingText="جارٍ التصحيح…" onClick={onSubmit}>
          <Send size={18} aria-hidden="true" />
          تسليم الإجابات
        </Btn>
      </div>
    </section>
  );
}

function QuizTaker({ quiz, onSubmitted }) {
  const count = quiz.questions.length;
  const [answers, setAnswers] = useState(
    () => readDraft(quiz.id, count) ?? quiz.questions.map(() => null)
  );
  const [step, setStep] = useState(0); // 0..count-1 = questions, count = review
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const headingRef = useRef(null);
  const top = useRef(null);
  const lastStep = useRef(0);

  const reviewing = step === count;
  const answered = answers.filter((a) => a !== null).length;

  useEffect(() => writeDraft(quiz.id, answers), [quiz.id, answers]);

  // Only when the step really changes: scroll to the top of it and move
  // keyboard / screen-reader focus onto the question.
  useEffect(() => {
    if (lastStep.current === step) return;
    lastStep.current = step;
    top.current?.scrollIntoView?.({ block: "start", behavior: "smooth" });
    headingRef.current?.focus({ preventScroll: true });
  }, [step]);

  const pick = useCallback(
    (oi) => setAnswers((list) => list.map((x, i) => (i === step ? oi : x))),
    [step]
  );

  // Number keys choose an option (1 = أ, 2 = ب …) for hardware keyboards.
  useEffect(() => {
    if (reviewing) return undefined;
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const n = Number(e.key);
      if (Number.isInteger(n) && n >= 1 && n <= quiz.questions[step].options.length) pick(n - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [reviewing, step, quiz.questions, pick]);

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const result = await studentApi.quizzes.submit(quiz.id, answers);
      clearDraft(quiz.id);
      onSubmitted(result);
    } catch (e) {
      setError(errorText(e, "تعذّر إرسال إجاباتك."));
    } finally {
      setSaving(false);
    }
  };

  const percent = percentOf(answered, count);

  return (
    <div className="qz" ref={top}>
      <QuizHeader title={quiz.title || "اختبار"} />

      <div className="qz-progress" aria-live="polite">
        <div className="qz-progress-row">
          <span>
            {reviewing ? (
              "المراجعة النهائية"
            ) : (
              <>
                أجبت عن <bdi className="num">{answered}</bdi> من <bdi className="num">{count}</bdi>
              </>
            )}
          </span>
          <strong className="num">{percent}%</strong>
        </div>
        <div
          className="progress"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={count}
          aria-valuenow={answered}
        >
          <i style={{ width: `${percent}%` }} />
        </div>
      </div>

      <QuestionDots answers={answers} step={step} onGo={setStep} />

      {reviewing ? (
        <ReviewStep
          answers={answers}
          saving={saving}
          error={error}
          onGo={setStep}
          onSubmit={submit}
        />
      ) : (
        <QuestionStep
          question={quiz.questions[step]}
          index={step}
          total={count}
          answer={answers[step]}
          onPick={pick}
          headingRef={headingRef}
        />
      )}

      <div className="qz-nav">
        <Btn variant="secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>
          <ArrowRight size={18} aria-hidden="true" />
          السابق
        </Btn>
        {!reviewing && (
          <Btn onClick={() => setStep(step + 1)}>
            {step === count - 1 ? "مراجعة وتسليم" : "التالي"}
            <ArrowLeft size={18} aria-hidden="true" />
          </Btn>
        )}
      </div>
    </div>
  );
}

/* ==========================================================================
   Result + answer review
   ========================================================================== */

function optionState(question, index) {
  if (index === question.answer_index) return "right";
  if (index === question.chosen) return "wrong";
  return "";
}

const STATUS = {
  right: { label: "إجابة صحيحة", Icon: CheckCircle2 },
  wrong: { label: "إجابة خاطئة", Icon: XCircle },
  skip: { label: "لم تُجب", Icon: AlertTriangle },
};

function ReviewCard({ question, number }) {
  const unanswered = question.chosen === null || question.chosen === undefined;
  const status = unanswered
    ? "skip"
    : question.chosen === question.answer_index
      ? "right"
      : "wrong";
  const { label, Icon } = STATUS[status];

  return (
    <article className={`qz-card qz-review is-${status}`}>
      <div className="qz-review-head">
        <span className="qz-qno">
          سؤال <bdi className="num">{number}</bdi>
        </span>
        <span className={`qz-status is-${status}`}>
          <Icon size={15} aria-hidden="true" />
          {label}
        </span>
      </div>
      <h3 className="qz-q">{question.q}</h3>
      <ul className="qz-options">
        {question.options.map((option, oi) => {
          const state = optionState(question, oi);
          return (
            <li key={oi} className={"qz-opt is-static" + (state ? ` ${state}` : "")}>
              <span className="qz-opt-mark" aria-hidden="true">
                {state === "right" ? (
                  <Check size={16} strokeWidth={3} />
                ) : state === "wrong" ? (
                  <XCircle size={16} />
                ) : (
                  (LETTERS[oi] ?? oi + 1)
                )}
              </span>
              <span className="qz-opt-text">{option}</span>
              {state === "right" && <span className="qz-opt-tag">الإجابة الصحيحة</span>}
              {state === "wrong" && <span className="qz-opt-tag">إجابتك</span>}
            </li>
          );
        })}
      </ul>
      {question.explanation && (
        <div className="qz-explain">
          <strong>التوضيح</strong>
          <p>{question.explanation}</p>
        </div>
      )}
    </article>
  );
}

function QuizResult({ quiz }) {
  const [only, setOnly] = useState("all");
  const verdict = verdictFor(percentOf(quiz.score, quiz.total));

  const rows = quiz.questions.map((q, i) => ({ q, number: i + 1 }));
  const wrong = rows.filter(({ q }) => q.chosen !== q.answer_index);
  const shown = only === "wrong" ? wrong : rows;

  const filters = [
    { key: "all", label: "كل الأسئلة" },
    { key: "wrong", label: `الأخطاء (${wrong.length})` },
  ];

  return (
    <div className="qz">
      <QuizHeader title={quiz.title || "اختبار"} />

      <section className={`qz-result is-${verdict.tone}`} aria-label="نتيجتك">
        <ScoreRing score={quiz.score} total={quiz.total} size="lg" />
        <div className="qz-result-text">
          <h2>{verdict.title}</h2>
          <p>{verdict.text}</p>
        </div>
        <dl className="qz-result-stats">
          <div>
            <dt>صحيحة</dt>
            <dd className="num">{quiz.score}</dd>
          </div>
          <div>
            <dt>خاطئة</dt>
            <dd className="num">{quiz.total - quiz.score}</dd>
          </div>
          <div>
            <dt>الأسئلة</dt>
            <dd className="num">{quiz.total}</dd>
          </div>
        </dl>
      </section>

      <FilterTabs label="عرض الإجابات" options={filters} value={only} onChange={setOnly} />

      {shown.length === 0 ? (
        <p className="qz-none">لا توجد أخطاء — إجاباتك كلها صحيحة 🎉</p>
      ) : (
        shown.map(({ q, number }) => <ReviewCard key={number} question={q} number={number} />)
      )}

      <div className="qz-nav qz-nav-end">
        <Link className="abtn abtn-primary" to="/learn/quizzes">
          العودة لاختباراتي
        </Link>
      </div>
    </div>
  );
}

/* ==========================================================================
   Single quiz route
   ========================================================================== */

export function QuizPage() {
  const { id } = useParams();
  const [quiz, setQuiz] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setQuiz(null);
    setErr(null);
    studentApi.quizzes
      .get(id)
      .then(setQuiz)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل الاختبار."));
  }, [id]);

  if (err && !quiz) {
    return (
      <div className="qz">
        <QuizBack />
        <Banner tone="err">{err}</Banner>
      </div>
    );
  }
  if (!quiz) {
    return (
      <div className="qz">
        <QuizBack />
        <p className="field-msg">جاري التحميل...</p>
      </div>
    );
  }
  return quiz.submitted ? (
    <QuizResult quiz={quiz} />
  ) : (
    <QuizTaker key={quiz.id} quiz={quiz} onSubmitted={setQuiz} />
  );
}
