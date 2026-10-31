import { useEffect, useState } from "react";
import { BarChart3, Pencil, Plus, Send, Trash2 } from "lucide-react";
import { Banner, Btn } from "../auth/ui.jsx";
import { Confirm, Empty, fmtDateTime } from "../dashboard/common.jsx";
import { examsApi } from "../lib/examsApi.js";
import { ApiError } from "../lib/api.js";
import ExamBuilder from "./ExamBuilder.jsx";
import ExamResults from "./ExamResults.jsx";
import "./exams.css";

const listOf = (d) => (Array.isArray(d) ? d : d?.results || []);
const STATE = {
  draft: { label: "مسودة", tone: "warn" },
  upcoming: { label: "لم يُفتح بعد", tone: "" },
  open: { label: "مفتوح الآن", tone: "good" },
  closed: { label: "مُغلق", tone: "" },
};

const targetsText = (t) => {
  const parts = [
    ...t.grades.map((g) => `صف: ${g.name}`),
    ...t.groups.map((g) => `مجموعة: ${g.name}`),
    t.students.length ? `${t.students.length} طالب` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" • ") : "بلا مستهدفين";
};

/** The "امتحانات" section of the educational content: write an exam, send it, read the results. */
export default function ExamsPanel({ grades, groups }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [form, setForm] = useState(null);
  const [pub, setPub] = useState(null);
  const [del, setDel] = useState(null);
  const [results, setResults] = useState(null);

  const load = () =>
    examsApi
      .list()
      .then((d) => {
        setRows(listOf(d));
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "تعذّر تحميل الامتحانات."));
  useEffect(() => {
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // the full paper (with the answer key) comes from the detail endpoint
  const openEdit = async (exam) => {
    try {
      setForm(await examsApi.get(exam.id));
    } catch (e) {
      setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر فتح الامتحان." });
    }
  };

  return (
    <>
      <div className="ex-toolbar">
        <p className="field-msg" style={{ margin: 0 }}>
          اكتب الأسئلة والإجابات الصحيحة، ثم أرسل الامتحان لصف أو مجموعة أو طلاب بعينهم.
        </p>
        <Btn onClick={() => setForm("add")}>
          <Plus size={16} /> إنشاء امتحان
        </Btn>
      </div>
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      {error && <Banner tone="err">{error}</Banner>}
      {!rows && !error && <p className="field-msg">جاري تحميل الامتحانات...</p>}
      {rows && rows.length === 0 && (
        <Empty title="لا توجد امتحانات بعد" text="أنشئ امتحانًا، ثم حدّد من يصله وأرسله." />
      )}
      <div className="list-rows">
        {rows?.map((x) => {
          const st = STATE[x.state] || STATE.draft;
          return (
            <div key={x.id} className="list-row">
              <div>
                <strong>{x.title}</strong> <span className={"chip-s " + st.tone}>{st.label}</span>
                <div className="stat-sub">{targetsText(x.targets)}</div>
                <div className="ex-meta">
                  <span>
                    <bdi>{x.question_count}</bdi> سؤال
                  </span>
                  <span>
                    <bdi>{x.total_points}</bdi> درجة
                  </span>
                  <span>
                    <bdi>{x.duration_minutes}</bdi> دقيقة
                  </span>
                  <span>يُغلق {fmtDateTime(x.closes_at)}</span>
                  {x.published && (
                    <span>
                      بدأ <bdi>{x.started_count}</bdi> • سلّم <bdi>{x.submitted_count}</bdi>
                    </span>
                  )}
                </div>
              </div>
              <div className="row-actions">
                {x.published ? (
                  <button className="mini-btn is-primary" onClick={() => setResults(x)}>
                    <BarChart3 size={13} /> النتائج
                  </button>
                ) : (
                  <button className="mini-btn is-primary" onClick={() => setPub(x)}>
                    <Send size={13} /> إرسال للطلاب
                  </button>
                )}
                <button className="mini-btn" onClick={() => openEdit(x)}>
                  <Pencil size={13} /> تعديل
                </button>
                <button
                  className="mini-btn danger"
                  aria-label={`حذف ${x.title}`}
                  onClick={() => setDel(x)}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
      {form && (
        <ExamBuilder
          key={form === "add" ? "add" : form.id}
          exam={form === "add" ? null : form}
          grades={grades}
          groups={groups}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null);
            load();
          }}
        />
      )}
      {results && <ExamResults exam={results} onClose={() => setResults(null)} />}
      {pub && (
        <Confirm
          title="إرسال الامتحان للطلاب؟"
          confirmLabel="أرسل الآن"
          text={`سيصل «${pub.title}» للمستهدفين فور الإرسال ويُشعَر الطلاب النشطون مرة واحدة. بعد الإرسال لا تتغير الأسئلة ولا المدة ولا المستهدفون.`}
          onClose={() => setPub(null)}
          onConfirm={async () => {
            try {
              const r = await examsApi.publish(pub.id);
              setNotice({ tone: "info", text: `تم الإرسال وإشعار ${r.notified} طالب.` });
            } catch (e) {
              setNotice({
                tone: "err",
                text: e instanceof ApiError ? e.message : "تعذّر الإرسال.",
              });
            }
            setPub(null);
            load();
          }}
        />
      )}
      {del && (
        <Confirm
          danger
          title="حذف الامتحان"
          confirmLabel="حذف"
          text={`سيُحذف «${del.title}» نهائيًا. لا يمكن حذف امتحان بدأه طلاب.`}
          onClose={() => setDel(null)}
          onConfirm={async () => {
            try {
              await examsApi.remove(del.id);
              setNotice(null);
            } catch (e) {
              setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر الحذف." });
            }
            setDel(null);
            load();
          }}
        />
      )}
    </>
  );
}
