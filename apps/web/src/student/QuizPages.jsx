import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Banner, Btn } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty, fmtDateTime } from "../dashboard/common.jsx";

export function QuizzesPage() {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { studentApi.quizzes.list().then((d) => setItems(d.results)).catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل الاختبارات.")); }, []);
  return (
    <>
      <PageHeader infoKey="student_quizzes" title="اختباراتي" />
      {err && <Banner tone="err">{err}</Banner>}
      {!items && !err && <p className="field-msg">جاري التحميل...</p>}
      {items && items.length === 0 && <Empty title="لا توجد اختبارات بعد" text="اطلب اختبارًا على أي فيديو من صفحة «الفيديوهات»." />}
      <div className="list-rows">{items?.map((q) => (
        <Link key={q.id} to={`/learn/quizzes/${q.id}`} className="list-row dash-card-btn">
          <div><strong>{q.title || "اختبار"}</strong><div className="stat-sub">{fmtDateTime(q.created_at)} • {q.questions} أسئلة</div></div>
          {q.score === null ? <span className="chip-s warn">لم يُحل بعد</span> : <span className="chip-s good">{q.score} / {q.total}</span>}
        </Link>))}</div>
    </>
  );
}

export function QuizPage() {
  const { id } = useParams();
  const [quiz, setQuiz] = useState(null);
  const [answers, setAnswers] = useState([]);
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setQuiz(null); setErr(null);
    studentApi.quizzes.get(id).then((q) => { setQuiz(q); setAnswers(q.questions.map((x) => (q.submitted ? x.chosen ?? null : null))); })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل الاختبار."));
  }, [id]);

  const submit = async () => {
    setSaving(true); setErr(null);
    try { setQuiz(await studentApi.quizzes.submit(id, answers)); }
    catch (e) { setErr(e instanceof ApiError ? (e.fields ? Object.values(e.fields).flat().join(" ") : e.message) : "تعذّر إرسال إجاباتك."); }
    finally { setSaving(false); }
  };

  if (err && !quiz) return <><PageHeader infoKey="student_quizzes" title="اختبار" /><Banner tone="err">{err}</Banner><Link className="dash-linkish" to="/learn/quizzes">العودة لاختباراتي</Link></>;
  if (!quiz) return <><PageHeader infoKey="student_quizzes" title="اختبار" /><p className="field-msg">جاري التحميل...</p></>;

  const answered = answers.filter((a) => a !== null).length;
  return (
    <>
      <PageHeader infoKey="student_quizzes" title={quiz.title || "اختبار"} />
      {err && <Banner tone="err">{err}</Banner>}
      {quiz.submitted && <div className="stu-q"><div className="stu-sub" style={{ textAlign: "center", margin: 0 }}>نتيجتك</div><div className="stu-score">{quiz.score} / {quiz.total}</div></div>}
      {quiz.questions.map((q, qi) => (
        <fieldset key={qi} className="stu-q" disabled={quiz.submitted} style={{ border: "1px solid var(--line)" }}>
          <h3>{qi + 1}. {q.q}</h3>
          {q.options.map((opt, oi) => {
            const state = quiz.submitted ? (oi === q.answer_index ? " right" : q.chosen === oi ? " wrong" : "") : "";
            return (
              <label key={oi} className={"stu-opt" + state}>
                <input type="radio" name={`q${qi}`} checked={answers[qi] === oi} onChange={() => setAnswers((a) => a.map((x, i) => (i === qi ? oi : x)))} />
                <span>{opt}</span>
              </label>
            );
          })}
          {quiz.submitted && q.explanation && <div className="stat-sub">{q.explanation}</div>}
        </fieldset>
      ))}
      {!quiz.submitted ? (
        <Btn loading={saving} loadingText="جارٍ التصحيح…" onClick={submit}>تسليم الإجابات ({answered} من {quiz.questions.length})</Btn>
      ) : <Link className="dash-linkish" to="/learn/quizzes">العودة لاختباراتي</Link>}
    </>
  );
}
