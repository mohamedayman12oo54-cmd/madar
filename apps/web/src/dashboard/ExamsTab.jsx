import { Fragment, useCallback, useEffect, useState } from "react";
import { Plus, Pencil, Trash2, Send, BarChart3, X, Check, RotateCcw } from "lucide-react";
import { Field, TextInput, Btn, Banner, Modal } from "../auth/ui.jsx";
import { examsApi } from "../lib/examsApi.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import { useGroups } from "./useGroups.js";
import { Confirm, Empty, MultiSelect, toggleId } from "./common.jsx";
import "./exams.css";

const listOf = (d) => (Array.isArray(d) ? d : d?.results || []);
const blankChoice = (ok = false) => ({ text: "", is_correct: ok });
const blankQuestion = () => ({ text: "", points: 1, choices: [blankChoice(true), blankChoice(), blankChoice(), blankChoice()] });
const trueFalse = () => ({ text: "", points: 1, choices: [{ text: "صح", is_correct: true }, { text: "خطأ", is_correct: false }] });
const toLocalInput = (iso) => (iso ? new Date(new Date(iso).getTime() - new Date(iso).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "");
const fromLocalInput = (v) => (v ? new Date(v).toISOString() : null);
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("ar-EG", { dateStyle: "medium", timeStyle: "short" }) : "—");

const REASON = { submitted: "سلّم بنفسه", time: "انتهى الوقت", violations: "أُغلق بسبب مخالفات" };
const VIOLATION = { blur: "ترك الصفحة", hidden: "تبديل التبويب", fullscreen_exit: "خرج من الشاشة الكاملة", copy: "محاولة نسخ", paste: "محاولة لصق", contextmenu: "قائمة النقر الأيمن", print: "طباعة / لقطة شاشة", shortcut: "اختصار ممنوع" };

function QuestionEditor({ q, index, onChange, onRemove, error }) {
  const set = (patch) => onChange({ ...q, ...patch });
  const setChoice = (i, patch) => set({ choices: q.choices.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  const markCorrect = (i) => set({ choices: q.choices.map((c, j) => ({ ...c, is_correct: j === i })) });
  const removeChoice = (i) => {
    const rest = q.choices.filter((_, j) => j !== i);
    if (!rest.some((c) => c.is_correct) && rest.length) rest[0] = { ...rest[0], is_correct: true };
    set({ choices: rest });
  };
  return (
    <div className="xq">
      <div className="xq-head">
        <b>سؤال {index + 1}</b>
        <label className="xq-points">
          الدرجة
          <input className="inp" type="number" min="1" max="100" value={q.points} onChange={(e) => set({ points: Number(e.target.value) || 1 })} />
        </label>
        <button type="button" className="dash-linkish" onClick={onRemove}>حذف السؤال</button>
      </div>
      <textarea className="inp" rows={2} placeholder="نص السؤال" value={q.text} onChange={(e) => set({ text: e.target.value })} maxLength={1500} />
      <div className="xq-choices" role="radiogroup" aria-label="الاختيارات — حدّد الإجابة الصحيحة">
        {q.choices.map((c, i) => (
          <div key={i} className={"xq-choice" + (c.is_correct ? " is-correct" : "")}>
            <button type="button" role="radio" aria-checked={c.is_correct} className="xq-radio" onClick={() => markCorrect(i)} title="الإجابة الصحيحة">
              {c.is_correct && <Check size={13} />}
            </button>
            <input className="inp" placeholder={`الاختيار ${i + 1}`} value={c.text} onChange={(e) => setChoice(i, { text: e.target.value })} maxLength={400} />
            {q.choices.length > 2 && (
              <button type="button" className="xq-x" aria-label="حذف الاختيار" onClick={() => removeChoice(i)}><X size={14} /></button>
            )}
          </div>
        ))}
      </div>
      {q.choices.length < 6 && (
        <button type="button" className="dash-linkish" onClick={() => set({ choices: [...q.choices, blankChoice()] })}>+ اختيار</button>
      )}
      {error && <p className="field-err">{error}</p>}
    </div>
  );
}

function ExamFormModal({ exam, grades, groups, onClose, onSaved }) {
  const [v, setV] = useState({
    title: exam?.title || "", description: exam?.description || "", duration_minutes: exam?.duration_minutes || 30,
    shuffle_questions: exam?.shuffle_questions ?? true, shuffle_choices: exam?.shuffle_choices ?? true,
    allow_back: exam?.allow_back ?? false, reveal_answers: exam?.reveal_answers ?? false,
    max_violations: exam?.max_violations || 3, opens_at: toLocalInput(exam?.opens_at), closes_at: toLocalInput(exam?.closes_at),
  });
  const [gradeIds, setGradeIds] = useState(exam?.grade_ids || []);
  const [groupIds, setGroupIds] = useState(exam?.group_ids || []);
  const [qs, setQs] = useState(exam?.questions?.length ? exam.questions.map((q) => ({ text: q.text, points: q.points, choices: q.choices.map((c) => ({ text: c.text, is_correct: c.is_correct })) })) : [blankQuestion()]);
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);
  const gradeName = Object.fromEntries(grades.map((g) => [g.id, g.name]));
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e }));

  const save = async () => {
    setErr(null);
    for (const [i, q] of qs.entries()) {
      if (!q.text.trim()) return setErr(`اكتب نص السؤال ${i + 1}.`);
      if (q.choices.some((c) => !c.text.trim())) return setErr(`املأ كل اختيارات السؤال ${i + 1}.`);
    }
    if (!v.title.trim()) return setErr("اكتب عنوان الامتحان.");
    setSaving(true);
    try {
      const body = {
        ...v, title: v.title.trim(), duration_minutes: Number(v.duration_minutes), max_violations: Number(v.max_violations),
        opens_at: fromLocalInput(v.opens_at), closes_at: fromLocalInput(v.closes_at),
        grade_ids: gradeIds, group_ids: groupIds, enrollment_ids: exam?.enrollment_ids || [], questions: qs,
      };
      const saved = exam ? await examsApi.update(exam.id, body) : await examsApi.create(body);
      onSaved(saved);
    } catch (e) {
      const f = e instanceof ApiError ? e.fields : null;
      setErr(f ? Object.values(f).flat().join(" ") : e instanceof ApiError ? e.message : "تعذّر الحفظ.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal size="lg" title={exam ? "تعديل الامتحان" : "امتحان جديد"} onClose={onClose}
      footer={<><Btn variant="ghost" onClick={onClose}>إلغاء</Btn><Btn onClick={save} loading={saving}>حفظ</Btn></>}>
      {err && <Banner tone="err">{err}</Banner>}
      <div className="xf-grid">
        <Field label="عنوان الامتحان" className="form-wide"><TextInput value={v.title} onChange={set("title")} /></Field>
        <Field label="المدة (بالدقائق)"><input className="inp" type="number" min="1" max="300" value={v.duration_minutes} onChange={set("duration_minutes")} /></Field>
        <Field label="عدد التحذيرات قبل إغلاق الامتحان"><input className="inp" type="number" min="1" max="10" value={v.max_violations} onChange={set("max_violations")} /></Field>
        <Field label="يفتح في (اختياري)"><input className="inp" type="datetime-local" value={v.opens_at} onChange={set("opens_at")} /></Field>
        <Field label="يُغلق في (اختياري)"><input className="inp" type="datetime-local" value={v.closes_at} onChange={set("closes_at")} /></Field>
      </div>

      <div className="audience-row">
        <Field label="الصفوف المستهدفة">
          <MultiSelect label="الصفوف" items={grades.map((g) => ({ id: g.id, name: g.name }))} selected={gradeIds}
            onToggle={(id) => setGradeIds((l) => toggleId(l, id))} onClear={() => setGradeIds([])} placeholder="اختر الصف…" searchPlaceholder="ابحث عن صف…" />
        </Field>
        <Field label="المجموعات المستهدفة">
          <MultiSelect label="المجموعات" items={groups.map((g) => ({ id: g.id, name: g.name, hint: gradeName[g.grade_id] }))} selected={groupIds}
            onToggle={(id) => setGroupIds((l) => toggleId(l, id))} onClear={() => setGroupIds([])} placeholder="اختر المجموعة…" searchPlaceholder="ابحث عن مجموعة…" />
        </Field>
      </div>

      <fieldset className="xf-opts">
        <legend>إعدادات منع الغش</legend>
        <label><input type="checkbox" checked={v.shuffle_questions} onChange={set("shuffle_questions")} /> ترتيب الأسئلة مختلف لكل طالب</label>
        <label><input type="checkbox" checked={v.shuffle_choices} onChange={set("shuffle_choices")} /> ترتيب الاختيارات مختلف لكل طالب</label>
        <label><input type="checkbox" checked={!v.allow_back} onChange={(e) => setV((s) => ({ ...s, allow_back: !e.target.checked }))} /> لا يمكن الرجوع لسؤال سابق</label>
        <label><input type="checkbox" checked={v.reveal_answers} onChange={set("reveal_answers")} /> يرى الطالب الإجابات الصحيحة بعد التسليم</label>
      </fieldset>

      <div className="xq-list">
        {qs.map((q, i) => (
          <QuestionEditor key={i} q={q} index={i} onChange={(nq) => setQs((l) => l.map((x, j) => (j === i ? nq : x)))}
            onRemove={() => setQs((l) => (l.length > 1 ? l.filter((_, j) => j !== i) : l))} />
        ))}
      </div>
      <div className="xq-add">
        <Btn variant="ghost" onClick={() => setQs((l) => [...l, blankQuestion()])}><Plus size={15} /> سؤال اختيار من متعدد</Btn>
        <Btn variant="ghost" onClick={() => setQs((l) => [...l, trueFalse()])}><Plus size={15} /> سؤال صح / خطأ</Btn>
      </div>
    </Modal>
  );
}

const pct = (n) => Number(n ?? 0).toLocaleString("ar-EG", { maximumFractionDigits: 1 });

function AttemptLine({ a }) {
  return (
    <div className="xr-attempt">
      <b>المحاولة {pct(a.number)}</b>
      <span>
        {a.status === "finished" ? `${pct(a.score)}/${pct(a.max_score)} (${pct(a.percent)}٪) • ${REASON[a.end_reason] || ""}` : "جارية الآن"}
      </span>
      <span>{a.violations ? `${pct(a.violations)} مخالفة` : "بلا مخالفات"}</span>
      {a.violations > 0 && (
        <span className="xr-log">
          {(a.violation_log || []).map((x, i) => <span key={i} className="chip-s">{VIOLATION[x.type] || x.type} • {fmt(x.at)}</span>)}
        </span>
      )}
    </div>
  );
}

function ResultsModal({ exam, onClose }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);
  const [ask, setAsk] = useState(null);
  const [notice, setNotice] = useState(null);
  const load = useCallback(() => examsApi.results(exam.id).then(setData).catch(() => setData({ results: [], error: true })), [exam.id]);
  useEffect(() => { load(); }, [load]);

  const reopen = async (r) => {
    setAsk(null);
    try {
      const res = await examsApi.reopen(exam.id, r.enrollment_id);
      setNotice({ tone: "ok", text: res.already ? `الامتحان مفتوح لـ ${r.name} بالفعل.` : `أُعيد فتح الامتحان لـ ${r.name} وتم إشعاره. تُحتسب له أعلى درجة بين محاولاته.` });
      load();
    } catch (e) {
      setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّرت إعادة الفتح." });
    }
  };

  return (
    <Modal size="lg" title={`نتائج: ${exam.title}`} onClose={onClose}>
      {!data && <p>جارٍ التحميل…</p>}
      {data?.error && <Banner tone="err">تعذّر تحميل النتائج.</Banner>}
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      {data && !data.error && (
        <>
          <p className="xr-sum">أنهى {pct(data.finished)} من {pct(data.total)}{data.average_percent != null && <> • المتوسط {pct(data.average_percent)}٪</>} • الدرجة المحسوبة لكل طالب هي أعلى محاولة</p>
          <div className="xr-wrap">
            <table className="xr-table">
              <thead><tr><th>الطالب</th><th>الحالة</th><th>أعلى درجة</th><th>المحاولات</th><th>المخالفات</th><th>إجراء</th></tr></thead>
              <tbody>
                {data.results.map((r) => {
                  const last = r.attempts[r.attempts.length - 1];
                  return (
                    <Fragment key={r.enrollment_id}>
                      <tr>
                        <td>{r.name}</td>
                        <td>
                          {r.status === "not_started" ? "لم يبدأ" : r.status === "in_progress" ? "جارٍ الآن" : (
                            <span className={"chip-s " + (last.end_reason === "violations" ? "bad" : "")}>{REASON[last.end_reason]}</span>
                          )}
                        </td>
                        <td>{r.percent != null ? `${pct(r.score)}/${pct(r.max_score)} (${pct(r.percent)}٪)` : "—"}</td>
                        <td>{r.attempt_count ? <button className="dash-linkish" onClick={() => setOpen(open === r.enrollment_id ? null : r.enrollment_id)}>{pct(r.attempt_count)}</button> : "٠"}</td>
                        <td>{r.violations ? pct(r.violations) : "٠"}</td>
                        <td>
                          {r.reopened ? <span className="chip-s warn">مفتوح له</span>
                            : r.can_reopen ? <button className="mini-btn" onClick={() => setAsk(r)}><RotateCcw size={13} /> إعادة فتح</button> : null}
                        </td>
                      </tr>
                      {open === r.enrollment_id && (
                        <tr><td colSpan={6} className="xr-attempts">{r.attempts.map((a) => <AttemptLine key={a.number} a={a} />)}</td></tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
      {ask && (
        <Confirm title="إعادة فتح الامتحان" confirmLabel="إعادة الفتح"
          text={`سيحصل «${ask.name}» على محاولة جديدة ويصله إشعار. تبقى محاولته السابقة محفوظة، وتُحتسب له أعلى درجة بين محاولاته.`}
          onClose={() => setAsk(null)} onConfirm={() => reopen(ask)} />
      )}
    </Modal>
  );
}

export default function ExamsTab() {
  const { grades } = useGrades();
  const { groups } = useGroups();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  const [form, setForm] = useState(null);
  const [results, setResults] = useState(null);
  const [del, setDel] = useState(null);
  const [notice, setNotice] = useState(null);

  const load = () => examsApi.list().then((d) => setRows(listOf(d))).catch(() => setErr("تعذّر تحميل الامتحانات."));
  useEffect(() => { load(); }, []);

  const edit = async (row) => {
    try { setForm(await examsApi.get(row.id)); } catch { setNotice({ tone: "err", text: "تعذّر فتح الامتحان." }); }
  };
  const publish = async (row) => {
    try {
      const r = await examsApi.publish(row.id);
      setNotice({ tone: "ok", text: `تم نشر الامتحان وإشعار ${r.notified} طالب.` });
      load();
    } catch (e) { setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر النشر." }); }
  };

  return (
    <>
      <div className="xt-head">
        <p className="xt-sub">أنشئ امتحانًا بأسئلة اختيار من متعدد أو صح/خطأ، وحدّد الصف أو المجموعة. التصحيح تلقائي والوقت يحسبه الخادم.</p>
        <Btn onClick={() => setForm("add")}><Plus size={16} /> امتحان جديد</Btn>
      </div>
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      {err && <Banner tone="err">{err}</Banner>}
      {rows && rows.length === 0 && <Empty title="لا توجد امتحانات بعد" text="اضغط «امتحان جديد» لإنشاء أول امتحان." />}
      <div className="xt-list">
        {(rows || []).map((r) => (
          <div className="xt-card" key={r.id}>
            <div className="xt-main">
              <b>{r.title}</b>
              <span>{r.question_count} سؤال • {r.duration_minutes} دقيقة • {r.attempt_count} محاولة</span>
              <span className={"chip-s " + (r.published_at ? "is-ok" : "")}>{r.published_at ? "منشور" : "مسودة"}</span>
            </div>
            <div className="xt-actions">
              {!r.published_at && <Btn variant="ghost" onClick={() => publish(r)}><Send size={14} /> نشر</Btn>}
              {r.attempt_count === 0 && <Btn variant="ghost" onClick={() => edit(r)}><Pencil size={14} /> تعديل</Btn>}
              {r.published_at && <Btn variant="ghost" onClick={() => setResults(r)}><BarChart3 size={14} /> النتائج</Btn>}
              <Btn variant="ghost" onClick={() => setDel(r)}><Trash2 size={14} /></Btn>
            </div>
          </div>
        ))}
      </div>
      {form && <ExamFormModal exam={form === "add" ? null : form} grades={grades} groups={groups} onClose={() => setForm(null)}
        onSaved={() => { setForm(null); load(); }} />}
      {results && <ResultsModal exam={results} onClose={() => setResults(null)} />}
      {del && <Confirm title="حذف الامتحان" text={`سيتم حذف «${del.title}» ونتائج الطلاب نهائيًا.`} confirmLabel="حذف" danger
        onClose={() => setDel(null)} onConfirm={async () => { await examsApi.remove(del.id).catch(() => {}); setDel(null); load(); }} />}
    </>
  );
}
