import { useEffect, useId, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2, X } from "lucide-react";
import { Banner, Btn, Field, Modal, TextInput } from "../auth/ui.jsx";
import DateTimePicker from "../components/DateTimePicker.jsx";
import { SearchSelect, useDebounced } from "../dashboard/common.jsx";
import { enrollmentsApi } from "../lib/academicsApi.js";
import { examsApi } from "../lib/examsApi.js";
import { ApiError } from "../lib/api.js";
import {
  MAX_CHOICES,
  MAX_QUESTIONS,
  MIN_CHOICES,
  blankForm,
  blankQuestion,
  fromExam,
  moveItem,
  toLimitedPayload,
  toPayload,
  trueFalseQuestion,
  validateExam,
} from "./builder.js";
import "./exams.css";

const listOf = (d) => (Array.isArray(d) ? d : d?.results || []);
const LETTERS = ["أ", "ب", "ج", "د", "هـ", "و"];

function QuestionEditor({ q, index, total, onChange, onMove, onRemove }) {
  const set = (patch) => onChange({ ...q, ...patch });
  const setChoice = (i, patch) =>
    set({ choices: q.choices.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  const markCorrect = (i) =>
    set({ choices: q.choices.map((c, j) => ({ ...c, is_correct: j === i })) });
  const removeChoice = (i) => {
    const next = q.choices.filter((_, j) => j !== i);
    // never leave a question without its correct answer
    if (!next.some((c) => c.is_correct)) next[0] = { ...next[0], is_correct: true };
    set({ choices: next });
  };
  return (
    <fieldset className="ex-q" style={{ margin: 0 }}>
      <div className="ex-q-head">
        <legend className="ex-q-no" style={{ padding: 0 }}>
          السؤال <bdi>{index + 1}</bdi>
        </legend>
        <div className="ex-q-tools">
          <button
            type="button"
            className="mini-btn"
            aria-label="نقل السؤال لأعلى"
            disabled={index === 0}
            onClick={() => onMove(index, index - 1)}
          >
            <ArrowUp size={13} />
          </button>
          <button
            type="button"
            className="mini-btn"
            aria-label="نقل السؤال لأسفل"
            disabled={index === total - 1}
            onClick={() => onMove(index, index + 1)}
          >
            <ArrowDown size={13} />
          </button>
          <button
            type="button"
            className="mini-btn danger"
            aria-label="حذف السؤال"
            onClick={() => onRemove(index)}
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
      <textarea
        className="inp"
        rows={3}
        maxLength={1500}
        value={q.text}
        onChange={(e) => set({ text: e.target.value })}
        placeholder="اكتب السؤال هنا"
        aria-label={`نص السؤال ${index + 1}`}
      />
      <div
        className="ex-choices"
        role="radiogroup"
        aria-label={`اختيارات السؤال ${index + 1}، حدّد الإجابة الصحيحة`}
      >
        {q.choices.map((c, i) => (
          <div key={c.key} className={"ex-choice" + (c.is_correct ? " is-correct" : "")}>
            <input
              type="radio"
              name={`correct-${q.key}`}
              checked={c.is_correct}
              onChange={() => markCorrect(i)}
              aria-label={`الاختيار ${LETTERS[i]} هو الإجابة الصحيحة`}
              title="الإجابة الصحيحة"
            />
            <TextInput
              value={c.text}
              maxLength={300}
              onChange={(e) => setChoice(i, { text: e.target.value })}
              placeholder={`الاختيار ${LETTERS[i]}`}
              aria-label={`نص الاختيار ${LETTERS[i]}`}
            />
            <button
              type="button"
              className="mini-btn"
              aria-label={`حذف الاختيار ${LETTERS[i]}`}
              disabled={q.choices.length <= MIN_CHOICES}
              onClick={() => removeChoice(i)}
            >
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
      <div className="ex-q-foot">
        <button
          type="button"
          className="mini-btn"
          disabled={q.choices.length >= MAX_CHOICES}
          onClick={() =>
            set({
              choices: [
                ...q.choices,
                { key: `${q.key}-${q.choices.length}-${Date.now()}`, text: "", is_correct: false },
              ],
            })
          }
        >
          <Plus size={13} /> اختيار
        </button>
        <label className="ex-points">
          الدرجة
          <input
            className="inp"
            type="number"
            min={1}
            max={100}
            value={q.points}
            onChange={(e) => set({ points: e.target.value })}
            aria-label={`درجة السؤال ${index + 1}`}
          />
        </label>
      </div>
    </fieldset>
  );
}

/** Create or edit an exam. A draft is fully editable; an exam already sent to students keeps its paper
 *  frozen (the server refuses those changes) and only allows title, description, closing time and the
 *  answer review. */
export default function ExamBuilder({ exam, grades, groups, onClose, onSaved }) {
  const formId = useId();
  const locked = Boolean(exam?.published);
  const [f, setF] = useState(() => (exam ? fromExam(exam) : blankForm()));
  const [problems, setProblems] = useState([]);
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const [found, setFound] = useState([]);
  const set = (patch) => setF((s) => ({ ...s, ...patch }));

  useEffect(() => {
    if (locked || q.trim().length < 2) {
      setFound([]);
      return;
    }
    enrollmentsApi
      .list({ search: q, is_active: "true" })
      .then((d) => setFound(listOf(d).slice(0, 6)))
      .catch(() => setFound([]));
  }, [q, locked]);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    const bad = locked
      ? [!f.title.trim() && "أدخل عنوان الامتحان.", !f.closes && "حدّد موعد الإغلاق."].filter(
          Boolean
        )
      : validateExam(f);
    setProblems(bad);
    if (bad.length) return;
    setSaving(true);
    try {
      if (!exam) await examsApi.create(toPayload(f));
      else await examsApi.update(exam.id, locked ? toLimitedPayload(f) : toPayload(f));
      onSaved();
    } catch (e2) {
      setErr(
        e2 instanceof ApiError
          ? e2.fields
            ? Object.values(e2.fields).flat().join(" ")
            : e2.message
          : "تعذّر الحفظ."
      );
    } finally {
      setSaving(false);
    }
  };

  const updateQ = (i, nq) => set({ questions: f.questions.map((x, j) => (j === i ? nq : x)) });
  const totalPoints = f.questions.reduce((s, x) => s + (Number(x.points) || 0), 0);

  return (
    <Modal
      size="lg"
      title={exam ? (locked ? "تعديل الامتحان (أُرسل للطلاب)" : "تعديل الامتحان") : "إنشاء امتحان"}
      text={
        locked
          ? "الأسئلة والمدة والمستهدفون مقفلة بعد الإرسال حتى لا تتغير شروط الامتحان على من بدأ."
          : "اكتب الأسئلة وحدّد الإجابة الصحيحة لكل سؤال، ثم اختر من يصله وموعد الفتح والإغلاق."
      }
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" type="button" onClick={onClose}>
            إلغاء
          </Btn>
          <Btn type="submit" form={formId} loading={saving} loadingText="جارٍ الحفظ…">
            {exam ? "حفظ التعديلات" : "حفظ كمسودة"}
          </Btn>
        </>
      }
    >
      <form id={formId} onSubmit={submit} className="dash-form" noValidate>
        {err && (
          <div className="form-wide">
            <Banner tone="err">{err}</Banner>
          </div>
        )}
        {problems.length > 0 && (
          <div className="form-wide">
            <Banner tone="err">
              <ul className="ex-errlist">
                {problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </Banner>
          </div>
        )}

        <div className="form-wide form-section">
          <h4 className="form-section-title">بيانات الامتحان</h4>
        </div>
        <Field className="form-wide" label="عنوان الامتحان" required>
          <TextInput
            value={f.title}
            maxLength={200}
            onChange={(e) => set({ title: e.target.value })}
            autoFocus
            placeholder="مثال: امتحان الباب الأول"
          />
        </Field>
        <Field
          className="form-wide"
          label="تعليمات للطلاب (اختياري)"
          hint="تظهر للطالب قبل أن يبدأ."
        >
          <textarea
            className="inp"
            rows={2}
            maxLength={2000}
            value={f.description}
            onChange={(e) => set({ description: e.target.value })}
          />
        </Field>
        <div className="form-wide form-pair">
          <Field label="مدة الامتحان بالدقائق" required hint="يبدأ العدّ من لحظة بدء كل طالب.">
            <TextInput
              type="number"
              min={1}
              max={600}
              value={f.duration}
              disabled={locked}
              onChange={(e) => set({ duration: e.target.value })}
            />
          </Field>
          <Field label="حد المخالفات" hint="يُسلَّم الامتحان تلقائيًا عند الوصول إليه.">
            <TextInput
              type="number"
              min={1}
              max={10}
              value={f.maxViolations}
              disabled={locked}
              onChange={(e) => set({ maxViolations: e.target.value })}
            />
          </Field>
          <Field label="يُفتح في (اختياري)" hint="اتركه فارغًا ليُفتح لحظة الإرسال.">
            {locked ? (
              <TextInput value={f.opens ? f.opens.replace("T", " ") : "لحظة الإرسال"} disabled />
            ) : (
              <DateTimePicker value={f.opens || ""} onChange={(v) => set({ opens: v })} />
            )}
          </Field>
          <Field
            label="يُغلق في"
            required
            hint="بعده لا يستطيع أحد البدء، ويُسلَّم ما بدأ تلقائيًا."
          >
            <DateTimePicker value={f.closes} onChange={(v) => set({ closes: v })} required />
          </Field>
        </div>

        <div className="form-wide form-section">
          <h4 className="form-section-title">الخيارات</h4>
        </div>
        <div className="form-wide ex-opts">
          <label className="ex-check">
            <input
              type="checkbox"
              checked={f.shuffleQ}
              disabled={locked}
              onChange={(e) => set({ shuffleQ: e.target.checked })}
            />
            <span>ترتيب أسئلة مختلف لكل طالب</span>
          </label>
          <label className="ex-check">
            <input
              type="checkbox"
              checked={f.shuffleC}
              disabled={locked}
              onChange={(e) => set({ shuffleC: e.target.checked })}
            />
            <span>ترتيب اختيارات مختلف لكل طالب</span>
          </label>
          <Field label="متى يرى الطالب درجته؟">
            <select
              className="inp"
              value={f.release}
              disabled={locked}
              onChange={(e) => set({ release: e.target.value })}
            >
              <option value="immediate">فور التسليم</option>
              <option value="after_close">بعد موعد الإغلاق</option>
            </select>
          </Field>
          <label className="ex-check">
            <input
              type="checkbox"
              checked={f.reveal}
              onChange={(e) => set({ reveal: e.target.checked })}
            />
            <span>يرى الطالب الإجابات الصحيحة بعد إغلاق الامتحان</span>
          </label>
        </div>

        {!locked && (
          <>
            <div className="form-wide form-section">
              <h4 className="form-section-title">من يصله الامتحان</h4>
              <p className="field-msg">
                اختر صفًّا أو مجموعة، أو طلابًا بعينهم. بلا مستهدفين لا يمكن إرساله.
              </p>
            </div>
            <div className="form-wide form-pair">
              <Field label="الصفوف المستهدفة">
                <SearchSelect
                  multiple
                  items={grades}
                  value={f.gradeIds}
                  onChange={(v) => set({ gradeIds: v })}
                  placeholder="اختر الصفوف"
                  searchPlaceholder="ابحث عن صف…"
                  empty="لا توجد صفوف بعد."
                />
              </Field>
              <Field label="المجموعات المستهدفة">
                <SearchSelect
                  multiple
                  items={groups}
                  value={f.groupIds}
                  onChange={(v) => set({ groupIds: v })}
                  placeholder="اختر المجموعات"
                  searchPlaceholder="ابحث عن مجموعة…"
                  empty="لا توجد مجموعات بعد."
                />
              </Field>
            </div>
            <Field className="form-wide" label="طلاب بعينهم (اختياري)">
              <TextInput
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="ابحث باسم الطالب أو رقمه…"
              />
              {found.length > 0 && (
                <div className="tag-list" style={{ marginBlockStart: 8 }}>
                  {found
                    .filter((x) => !f.students.some((s) => s.id === x.id))
                    .map((x) => (
                      <button
                        type="button"
                        key={x.id}
                        className="mini-btn"
                        onClick={() => {
                          set({ students: [...f.students, { id: x.id, name: x.student.name }] });
                          setSearch("");
                          setFound([]);
                        }}
                      >
                        + {x.student.name}
                      </button>
                    ))}
                </div>
              )}
              {f.students.length > 0 && (
                <div className="tag-list" style={{ marginBlockStart: 8 }}>
                  {f.students.map((s) => (
                    <span key={s.id} className="chip-s">
                      {s.name}{" "}
                      <button
                        type="button"
                        aria-label="إزالة"
                        onClick={() => set({ students: f.students.filter((x) => x.id !== s.id) })}
                      >
                        <X size={11} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </Field>

            <div className="form-wide form-section">
              <h4 className="form-section-title">
                الأسئلة (<bdi>{f.questions.length}</bdi>) — المجموع <bdi>{totalPoints}</bdi> درجة
              </h4>
              <p className="field-msg">
                اختيار من متعدد أو صح/خطأ. لكل سؤال إجابة صحيحة واحدة تحدّدها بالدائرة.
              </p>
            </div>
            <div className="form-wide ex-questions">
              {f.questions.map((x, i) => (
                <QuestionEditor
                  key={x.key}
                  q={x}
                  index={i}
                  total={f.questions.length}
                  onChange={(nq) => updateQ(i, nq)}
                  onMove={(a, b) => set({ questions: moveItem(f.questions, a, b) })}
                  onRemove={(idx) => set({ questions: f.questions.filter((_, j) => j !== idx) })}
                />
              ))}
              <div className="ex-add-row">
                <button
                  type="button"
                  className="mini-btn is-primary"
                  disabled={f.questions.length >= MAX_QUESTIONS}
                  onClick={() => set({ questions: [...f.questions, blankQuestion()] })}
                >
                  <Plus size={13} /> سؤال اختيار من متعدد
                </button>
                <button
                  type="button"
                  className="mini-btn"
                  disabled={f.questions.length >= MAX_QUESTIONS}
                  onClick={() => set({ questions: [...f.questions, trueFalseQuestion()] })}
                >
                  <Plus size={13} /> سؤال صح / خطأ
                </button>
              </div>
            </div>
          </>
        )}
      </form>
    </Modal>
  );
}
