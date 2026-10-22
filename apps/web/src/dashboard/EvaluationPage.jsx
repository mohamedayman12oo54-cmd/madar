import { useEffect, useRef, useState } from "react";
import { Search, NotebookPen, Sparkles, Send } from "lucide-react";
import { Btn, Banner, Modal } from "../auth/ui.jsx";
import { evaluationApi } from "../lib/dashboardApi.js";
import { pollUntilDone } from "../lib/poll.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import { useGroups } from "./useGroups.js";
import {
  Confirm,
  Empty,
  MonthInput,
  PageHeader,
  currentMonthValue,
  fmtDateTime,
  useDebounced,
} from "./common.jsx";

const STATES = [
  ["good", "جيد"],
  ["needs_follow_up", "يحتاج متابعة"],
  ["at_risk", "معرّض للخطر"],
];
const STATE_LABEL = Object.fromEntries(STATES);
const newKey = () =>
  globalThis.crypto?.randomUUID?.() ?? `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;

function Stars({ value, onPick, disabled }) {
  return (
    <span className="stars" role="radiogroup" aria-label="التقييم من 1 إلى 5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          disabled={disabled}
          className={n <= (value || 0) ? "on" : ""}
          onClick={() => onPick(n)}
          aria-label={`${n} من 5`}
        >
          ★
        </button>
      ))}
    </span>
  );
}

function NotesModal({ row, onClose }) {
  const [notes, setNotes] = useState(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState(null);
  const load = () =>
    evaluationApi.notes
      .list(row.enrollment_id)
      .then((d) => setNotes(Array.isArray(d) ? d : d.results || []))
      .catch(() => setNotes([]));
  useEffect(() => {
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const add = async (e) => {
    e.preventDefault();
    setErr(null);
    try {
      await evaluationApi.notes.create(row.enrollment_id, text);
      setText("");
      load();
    } catch (e2) {
      setErr(
        e2 instanceof ApiError
          ? e2.fields
            ? Object.values(e2.fields).flat().join(" ")
            : e2.message
          : "تعذّر الحفظ."
      );
    }
  };
  return (
    <Modal
      size="md"
      title={`ملاحظات المعلّم — ${row.name}`}
      text="يراها الطالب ضمن تقييمه. اكتبها كتوجيه موجَّه له."
      onClose={onClose}
    >
      {notes === null ? (
        <p className="field-msg">جاري التحميل...</p>
      ) : (
        <div className="list-rows" style={{ marginBlockEnd: 12 }}>
          {notes.length === 0 && <p className="field-msg">لا توجد ملاحظات.</p>}
          {notes.map((n) => (
            <div key={n.id} className="list-row">
              <div>
                <div>{n.body}</div>
                <div className="stat-sub">{fmtDateTime(n.created_at)}</div>
              </div>
              <button
                className="mini-btn danger"
                onClick={async () => {
                  await evaluationApi.notes.remove(n.id).catch(() => {});
                  load();
                }}
              >
                حذف
              </button>
            </div>
          ))}
        </div>
      )}
      <form onSubmit={add} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <textarea
          className="inp"
          rows={3}
          maxLength={2000}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="اكتب ملاحظة…"
        />
        <Btn type="submit" disabled={!text.trim()}>
          إضافة ملاحظة
        </Btn>
      </form>
    </Modal>
  );
}

export default function EvaluationPage() {
  const { grades } = useGrades();
  const { groups } = useGroups();
  const [month, setMonth] = useState(currentMonthValue());
  const [gradeId, setGradeId] = useState("");
  const [groupId, setGroupId] = useState("");
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const [data, setData] = useState(null);
  const [notice, setNotice] = useState(null);
  const [notes, setNotes] = useState(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const aborts = useRef({});

  const load = () =>
    evaluationApi
      .sheet({ month, grade_id: gradeId, group_id: groupId, search: q })
      .then(setData)
      .catch((e) =>
        setNotice({
          tone: "err",
          text:
            e instanceof ApiError
              ? e.fields
                ? Object.values(e.fields).flat().join(" ")
                : e.message
              : "تعذّر تحميل التقييمات.",
        })
      );
  useEffect(() => {
    load();
  }, [month, gradeId, groupId, q]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => Object.values(aborts.current).forEach((c) => c.abort()), []);

  const patchRow = (id, patch) =>
    setData((d) => ({
      ...d,
      rows: d.rows.map((r) => (r.enrollment_id === id ? { ...r, ...patch } : r)),
    }));
  const fail = (e, fallback) =>
    setNotice({ tone: "err", text: e instanceof ApiError ? e.message : fallback });

  const setState = async (row, state) => {
    try {
      await evaluationApi.setState(row.enrollment_id, month, state);
      patchRow(row.enrollment_id, { state });
    } catch (e) {
      fail(e, "تعذّر حفظ الحالة.");
    }
  };
  const setRating = async (row, value) => {
    try {
      await evaluationApi.setRating(row.enrollment_id, month, value);
      patchRow(row.enrollment_id, { rating: { value, published: false } });
    } catch (e) {
      fail(e, "تعذّر حفظ التقييم.");
    }
  };
  const publish = async (row) => {
    try {
      await evaluationApi.publishRating(row.enrollment_id, month);
      patchRow(row.enrollment_id, { rating: { ...row.rating, published: true } });
      setNotice({ tone: "info", text: "تم نشر التقييم وإرسال إشعار للطالب." });
    } catch (e) {
      fail(e, "تعذّر نشر التقييم.");
    }
  };
  const publishAll = async () => {
    try {
      const r = await evaluationApi.publishAll({
        month,
        grade_id: gradeId || undefined,
        group_id: groupId || undefined,
      });
      setNotice({ tone: "info", text: `تم نشر ${r.published} تقييم.` });
      load();
    } catch (e) {
      fail(e, "تعذّر النشر.");
    }
    setConfirmAll(false);
  };

  const recommend = async (row) => {
    patchRow(row.enrollment_id, { recommendation: { status: "pending" } });
    try {
      const op = await evaluationApi.recommend(row.enrollment_id, month, newKey());
      aborts.current[row.enrollment_id]?.abort();
      const controller = new AbortController();
      aborts.current[row.enrollment_id] = controller;
      const out = await pollUntilDone(() => evaluationApi.operation(op.id), {
        isDone: (o) => o.status === "completed" || o.status === "failed",
        signal: controller.signal,
        onUpdate: (o) =>
          patchRow(row.enrollment_id, {
            recommendation: {
              operation_id: o.id,
              status: o.status,
              suggested_state: o.suggested_state,
              rationale: o.result || o.error,
            },
          }),
      });
      if (out.status === "timeout")
        patchRow(row.enrollment_id, {
          recommendation: {
            status: "failed",
            rationale: "استغرق الطلب وقتًا أطول من المتوقع. حاول لاحقًا.",
          },
        });
    } catch (e) {
      patchRow(row.enrollment_id, {
        recommendation: {
          status: "failed",
          rationale: e instanceof ApiError ? e.message : "تعذّر طلب الاقتراح.",
        },
      });
    }
  };

  const draftCount = data?.rows.filter((r) => r.rating && !r.rating.published).length || 0;
  return (
    <>
      <PageHeader infoKey="evaluation" title="التقييم الشهري">
        <MonthInput value={month} onChange={setMonth} />
        <Btn variant="ghost" disabled={!draftCount} onClick={() => setConfirmAll(true)}>
          <Send size={15} /> نشر كل المسودات ({draftCount})
        </Btn>
      </PageHeader>
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      <div className="dash-filters">
        <div className="dash-search">
          <Search size={16} />
          <input
            placeholder="ابحث بالاسم"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select className="inp" value={gradeId} onChange={(e) => setGradeId(e.target.value)}>
          <option value="">كل الصفوف</option>
          {grades.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <select className="inp" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
          <option value="">كل المجموعات</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
      </div>
      {!data && <p className="field-msg">جاري تحميل البيانات...</p>}
      {data && data.rows.length === 0 && (
        <Empty title="لا يوجد طلاب" text="لا يوجد طلاب نشطون مطابقون لهذه الاختيارات." />
      )}
      {data && data.rows.length > 0 && (
        <div className="list-rows">
          {data.rows.map((r) => {
            const ev = r.evidence;
            const rec = r.recommendation;
            return (
              <div key={r.enrollment_id} className="dash-card">
                <div className="dash-section-head" style={{ marginBlockEnd: 8 }}>
                  <h2 style={{ fontSize: "1rem" }}>
                    {r.name} <span className="stat-sub">{r.grade}</span>
                  </h2>
                  <button className="mini-btn" onClick={() => setNotes(r)}>
                    <NotebookPen size={13} /> ملاحظات
                  </button>
                </div>
                <div className="stat-sub">
                  هذا الشهر: حضر {ev.present} • غاب {ev.absent} • ذاكر {ev.studied} • لم يذاكر{" "}
                  {ev.not_studied}
                </div>
                <div className="dash-filters" style={{ marginBlock: "12px 0" }}>
                  <label className="stat-sub">
                    الحالة{" "}
                    <select
                      className="inp sel-inline"
                      value={r.state || ""}
                      onChange={(e) => e.target.value && setState(r, e.target.value)}
                    >
                      <option value="">— لم تُحدَّد —</option>
                      {STATES.map(([v, l]) => (
                        <option key={v} value={v}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </label>
                  <span>
                    <span className="stat-sub">التقييم </span>
                    <Stars value={r.rating?.value} onPick={(n) => setRating(r, n)} />
                    {r.rating && (
                      <span
                        className={"chip-s " + (r.rating.published ? "good" : "warn")}
                        style={{ marginInlineStart: 8 }}
                      >
                        {r.rating.published ? "منشور" : "مسودة"}
                      </span>
                    )}
                    {r.rating && !r.rating.published && (
                      <button
                        className="mini-btn"
                        style={{ marginInlineStart: 8 }}
                        onClick={() => publish(r)}
                      >
                        نشر للطالب
                      </button>
                    )}
                  </span>
                  <button
                    className="mini-btn"
                    disabled={rec?.status === "pending" || rec?.status === "processing"}
                    onClick={() => recommend(r)}
                  >
                    <Sparkles size={13} /> اقتراح ذكي للحالة
                  </button>
                </div>
                {rec && (
                  <div className="dash-note" style={{ marginBlockStart: 12, marginBlockEnd: 0 }}>
                    {(rec.status === "pending" || rec.status === "processing") &&
                      "جارٍ إعداد الاقتراح…"}
                    {rec.status === "failed" && <>تعذّر إعداد اقتراح: {rec.rationale}</>}
                    {rec.status === "completed" && (
                      <>
                        <strong>اقتراح استشاري: {STATE_LABEL[rec.suggested_state] || "—"}</strong>
                        <div style={{ whiteSpace: "pre-line" }}>{rec.rationale}</div>
                        <div className="row-actions" style={{ marginBlockStart: 8 }}>
                          <button
                            className="mini-btn"
                            onClick={() => rec.suggested_state && setState(r, rec.suggested_state)}
                          >
                            اعتماد هذا الاقتراح
                          </button>
                          <span className="stat-sub">القرار لك — لا يُطبَّق شيء تلقائيًا.</span>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {notes && <NotesModal row={notes} onClose={() => setNotes(null)} />}
      {confirmAll && (
        <Confirm
          title="نشر كل التقييمات؟"
          confirmLabel="نشر"
          text={`سيُنشر ${draftCount} تقييم ويصل لكل طالب إشعار. لا يمكن سحب الإشعار بعد إرساله.`}
          onConfirm={publishAll}
          onClose={() => setConfirmAll(false)}
        />
      )}
    </>
  );
}
