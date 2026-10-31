import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ClipboardCheck } from "lucide-react";
import { Banner } from "../auth/ui.jsx";
import { Empty, fmtDateTime } from "../dashboard/common.jsx";
import { examsApi } from "../lib/examsApi.js";
import { ApiError } from "../lib/api.js";
import { EXAM_STATUS } from "../lib/examGuard.js";
import "./exams.css";

/** The "امتحانات" tab of the student's content page. */
export default function StudentExamList() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let alive = true;
    examsApi.student
      .list()
      .then((d) => alive && setRows(d.results))
      .catch((e) => alive && setErr(e instanceof ApiError ? e.message : "تعذّر تحميل الامتحانات."));
    return () => {
      alive = false;
    };
  }, []);
  return (
    <>
      {err && <Banner tone="err">{err}</Banner>}
      {!rows && !err && <p className="field-msg">جاري التحميل...</p>}
      {rows && rows.length === 0 && (
        <Empty title="لا توجد امتحانات بعد" text="ستظهر هنا الامتحانات التي يرسلها معلمك لك." />
      )}
      <div className="list-rows">
        {rows?.map((x) => {
          const st = EXAM_STATUS[x.status];
          return (
            <article key={x.id} className="video-msg">
              <div className="video-msg-text">
                <h3>
                  {x.title} <span className={"chip-s " + st.tone}>{st.label}</span>
                </h3>
                <div className="ex-meta">
                  <span>
                    <bdi>{x.question_count}</bdi> سؤال
                  </span>
                  <span>
                    <bdi>{x.duration_minutes}</bdi> دقيقة
                  </span>
                  <span>يُغلق {fmtDateTime(x.closes_at)}</span>
                  {x.score !== null && (
                    <span>
                      الدرجة{" "}
                      <span className="num" dir="ltr" style={{ unicodeBidi: "isolate-override" }}>
                        {`${x.score} / ${x.max_score}`}
                      </span>
                    </span>
                  )}
                  {x.results_pending && <span>الدرجة بعد الإغلاق</span>}
                </div>
              </div>
              <Link to={`/learn/exams/${x.id}`} className="mini-btn is-primary video-msg-go">
                <ClipboardCheck size={13} />{" "}
                {x.status === "open" ? "ابدأ" : x.status === "in_progress" ? "أكمل" : "فتح"}
              </Link>
            </article>
          );
        })}
      </div>
    </>
  );
}
