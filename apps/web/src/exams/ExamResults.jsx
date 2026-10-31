import { useEffect, useState } from "react";
import { CheckCircle2, RotateCcw, XCircle } from "lucide-react";
import { Banner, Btn, Modal } from "../auth/ui.jsx";
import { Confirm, Empty, fmtDateTime } from "../dashboard/common.jsx";
import { examsApi } from "../lib/examsApi.js";
import { ApiError } from "../lib/api.js";
import "./exams.css";

const STATUS = {
  not_started: { label: "لم يبدأ", tone: "" },
  in_progress: { label: "جارٍ", tone: "warn" },
  submitted: { label: "سلّم", tone: "good" },
};
const REASON = {
  manual: "سلّم بنفسه",
  time: "انتهى الوقت",
  violations: "سُلّم تلقائيًا بسبب المخالفات",
  "": "",
};

const Frac = ({ a, b }) => (
  <span className="num" dir="ltr" style={{ unicodeBidi: "isolate-override" }}>
    {`${a} / ${b}`}
  </span>
);

function AttemptDetail({ examId, attemptId, onClose }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    examsApi
      .attempt(examId, attemptId)
      .then(setD)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر التحميل."));
  }, [examId, attemptId]);
  return (
    <Modal size="lg" title={d ? `إجابات: ${d.attempt.name}` : "إجابات الطالب"} onClose={onClose}>
      {err && <Banner tone="err">{err}</Banner>}
      {!d && !err && <p className="field-msg">جاري التحميل…</p>}
      {d && (
        <div className="ex-review">
          <div className="ex-stats">
            <div className="ex-stat">
              <div className="k">الدرجة</div>
              <div className="v">
                {d.attempt.score === null ? (
                  "—"
                ) : (
                  <Frac a={d.attempt.score} b={d.attempt.max_score} />
                )}
              </div>
            </div>
            <div className="ex-stat">
              <div className="k">المخالفات</div>
              <div className="v">{d.attempt.violations}</div>
            </div>
            <div className="ex-stat">
              <div className="k">انتهى بسبب</div>
              <div className="v" style={{ fontSize: "0.9rem" }}>
                {REASON[d.attempt.submit_reason] || "جارٍ"}
              </div>
            </div>
          </div>
          <h4 className="form-section-title">سجل السلوك أثناء الامتحان</h4>
          {d.events.length === 0 ? (
            <p className="field-msg">لا توجد أي إشارات: لم يغادر الطالب صفحة الامتحان.</p>
          ) : (
            <ul className="ex-timeline">
              {d.events.map((e, i) => (
                <li key={i} className={e.counted ? "counted" : ""}>
                  <span>
                    {e.label}
                    {e.counted ? " — احتُسبت مخالفة" : ""}
                  </span>
                  <bdi>{fmtDateTime(e.at)}</bdi>
                </li>
              ))}
            </ul>
          )}
          <h4 className="form-section-title">الأسئلة</h4>
          {d.questions.map((q, i) => (
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
                    {mine && <span className="chip-s">إجابته</span>}
                  </div>
                );
              })}
              {q.chosen_choice_id === null && <p className="field-msg">لم يُجب عن هذا السؤال.</p>}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

export default function ExamResults({ exam, onClose }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [detail, setDetail] = useState(null);
  const [reset, setReset] = useState(null);

  const load = () =>
    examsApi
      .results(exam.id)
      .then(setD)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل النتائج."));
  useEffect(() => {
    load();
  }, [exam.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const s = d?.summary;
  return (
    <Modal
      size="lg"
      title={`نتائج: ${exam.title}`}
      onClose={onClose}
      footer={
        <Btn variant="ghost" onClick={onClose}>
          إغلاق
        </Btn>
      }
    >
      {err && <Banner tone="err">{err}</Banner>}
      {!d && !err && <p className="field-msg">جاري التحميل…</p>}
      {d && (
        <>
          <div className="ex-stats">
            <div className="ex-stat">
              <div className="k">المستهدفون</div>
              <div className="v">{s.audience}</div>
            </div>
            <div className="ex-stat">
              <div className="k">بدأوا</div>
              <div className="v">{s.started}</div>
            </div>
            <div className="ex-stat">
              <div className="k">سلّموا</div>
              <div className="v">{s.submitted}</div>
            </div>
            <div className="ex-stat">
              <div className="k">بمخالفات</div>
              <div className="v">{s.flagged}</div>
            </div>
            <div className="ex-stat">
              <div className="k">المتوسط</div>
              <div className="v">
                {s.average === null ? "—" : <Frac a={s.average} b={d.exam.total_points} />}
              </div>
            </div>
          </div>
          {d.results.length === 0 ? (
            <Empty title="لا يوجد مستهدفون" text="عدّل المستهدفين من الصف أو المجموعة." />
          ) : (
            <div className="dash-table-wrap">
              <table className="dash-table">
                <thead>
                  <tr>
                    <th>الطالب</th>
                    <th>الحالة</th>
                    <th>الدرجة</th>
                    <th>المخالفات</th>
                    <th>تسليم</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {d.results.map((r) => (
                    <tr key={r.enrollment_id}>
                      <td>
                        <strong>{r.name}</strong>
                        <div className="stat-sub">{r.groups.join("، ")}</div>
                      </td>
                      <td>
                        <span className={"chip-s " + STATUS[r.status].tone}>
                          {STATUS[r.status].label}
                        </span>
                      </td>
                      <td>{r.score === null ? "—" : <Frac a={r.score} b={r.max_score} />}</td>
                      <td>
                        <span className={"ex-flag" + (r.violations > 0 ? " hot" : "")}>
                          {r.violations}
                        </span>
                      </td>
                      <td className="stat-sub">
                        {REASON[r.submit_reason]}
                        {r.submitted_at ? ` • ${fmtDateTime(r.submitted_at)}` : ""}
                      </td>
                      <td>
                        {r.attempt_id && (
                          <div className="row-actions">
                            <button className="mini-btn" onClick={() => setDetail(r.attempt_id)}>
                              التفاصيل
                            </button>
                            <button
                              className="mini-btn"
                              onClick={() => setReset(r)}
                              title="يحذف محاولته ليبدأ من جديد"
                            >
                              <RotateCcw size={13} /> محاولة جديدة
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      {detail && (
        <AttemptDetail examId={exam.id} attemptId={detail} onClose={() => setDetail(null)} />
      )}
      {reset && (
        <Confirm
          danger
          title="السماح بمحاولة جديدة؟"
          confirmLabel="احذف المحاولة"
          text={`ستُحذف محاولة «${reset.name}» وإجاباتها وسجلّها، ويستطيع البدء من جديد ما دام الامتحان مفتوحًا. استخدمه عند انقطاع الإنترنت أو الإنذار الخاطئ.`}
          onClose={() => setReset(null)}
          onConfirm={async () => {
            await examsApi.resetAttempt(exam.id, reset.attempt_id).catch(() => {});
            setReset(null);
            load();
          }}
        />
      )}
    </Modal>
  );
}
