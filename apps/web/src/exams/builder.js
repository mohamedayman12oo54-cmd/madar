// Pure helpers for the exam builder: the form shape, its validation (mirrors the server's rules so a
// teacher hears about a problem before the round trip) and the API payload. The server validates again.
import { toIso, toLocalInput, inHours } from "./time.js";

export const MAX_QUESTIONS = 100;
export const MIN_CHOICES = 2;
export const MAX_CHOICES = 6;

let seq = 0;
const key = () => `q${++seq}`;
const choice = (correct = false, text = "") => ({ key: key(), text, is_correct: correct });

export const blankQuestion = () => ({
  key: key(),
  text: "",
  points: 1,
  choices: [choice(true), choice(), choice()],
});
export const trueFalseQuestion = () => ({
  key: key(),
  text: "",
  points: 1,
  choices: [choice(true, "صح"), choice(false, "خطأ")],
});

export function blankForm() {
  return {
    title: "",
    description: "",
    duration: "30",
    opens: "",
    closes: inHours(48),
    shuffleQ: true,
    shuffleC: true,
    release: "immediate",
    reveal: false,
    maxViolations: "3",
    gradeIds: [],
    groupIds: [],
    students: [],
    questions: [blankQuestion()],
  };
}

export function fromExam(exam) {
  return {
    title: exam.title,
    description: exam.description || "",
    duration: String(exam.duration_minutes),
    opens: exam.opens_at ? toLocalInput(exam.opens_at) : "",
    closes: toLocalInput(exam.closes_at),
    shuffleQ: exam.shuffle_questions,
    shuffleC: exam.shuffle_choices,
    release: exam.results_release,
    reveal: exam.reveal_answers,
    maxViolations: String(exam.max_violations),
    gradeIds: exam.targets.grades.map((g) => g.id),
    groupIds: exam.targets.groups.map((g) => g.id),
    students: exam.targets.students,
    questions: (exam.questions || []).map((q) => ({
      key: key(),
      text: q.text,
      points: q.points,
      choices: q.choices.map((c) => ({ key: key(), text: c.text, is_correct: c.is_correct })),
    })),
  };
}

/** Everything wrong with the form, as sentences. Empty means it can be saved. */
export function validateExam(f, now = Date.now()) {
  const out = [];
  if (!f.title.trim()) out.push("أدخل عنوان الامتحان.");
  const mins = Number(f.duration);
  if (!Number.isInteger(mins) || mins < 1 || mins > 600)
    out.push("مدة الامتحان من 1 إلى 600 دقيقة.");
  const v = Number(f.maxViolations);
  if (!Number.isInteger(v) || v < 1 || v > 10) out.push("حد المخالفات من 1 إلى 10.");
  if (!f.closes) out.push("حدّد موعد إغلاق الامتحان.");
  else {
    if (new Date(f.closes).getTime() <= now) out.push("موعد الإغلاق يجب أن يكون في المستقبل.");
    if (f.opens && new Date(f.closes).getTime() <= new Date(f.opens).getTime())
      out.push("موعد الإغلاق يجب أن يكون بعد موعد الفتح.");
  }
  if (f.questions.length === 0) out.push("أضف سؤالًا واحدًا على الأقل.");
  if (f.questions.length > MAX_QUESTIONS) out.push(`الحد الأقصى ${MAX_QUESTIONS} سؤالًا.`);
  f.questions.forEach((q, i) => {
    const n = i + 1;
    if (!q.text.trim()) out.push(`السؤال ${n}: اكتب نص السؤال.`);
    const pts = Number(q.points);
    if (!Number.isInteger(pts) || pts < 1 || pts > 100)
      out.push(`السؤال ${n}: الدرجة من 1 إلى 100.`);
    if (q.choices.length < MIN_CHOICES || q.choices.length > MAX_CHOICES)
      out.push(`السؤال ${n}: من ${MIN_CHOICES} إلى ${MAX_CHOICES} اختيارات.`);
    if (q.choices.some((c) => !c.text.trim())) out.push(`السؤال ${n}: اكتب نص كل اختيار.`);
    const texts = q.choices.map((c) => c.text.trim().toLowerCase()).filter(Boolean);
    if (new Set(texts).size !== texts.length) out.push(`السؤال ${n}: اختيارات مكررة.`);
    if (q.choices.filter((c) => c.is_correct).length !== 1)
      out.push(`السؤال ${n}: حدّد إجابة صحيحة واحدة.`);
  });
  return out;
}

export function toPayload(f) {
  return {
    title: f.title.trim(),
    description: f.description.trim(),
    duration_minutes: Number(f.duration),
    opens_at: f.opens ? toIso(f.opens) : null,
    closes_at: toIso(f.closes),
    shuffle_questions: f.shuffleQ,
    shuffle_choices: f.shuffleC,
    results_release: f.release,
    reveal_answers: f.reveal,
    max_violations: Number(f.maxViolations),
    grade_ids: f.gradeIds,
    group_ids: f.groupIds,
    enrollment_ids: f.students.map((s) => s.id),
    questions: f.questions.map((q) => ({
      text: q.text.trim(),
      points: Number(q.points),
      choices: q.choices.map((c) => ({ text: c.text.trim(), is_correct: c.is_correct })),
    })),
  };
}

/** After an exam is sent, only these may change (the server refuses anything else). */
export function toLimitedPayload(f) {
  return {
    title: f.title.trim(),
    description: f.description.trim(),
    closes_at: toIso(f.closes),
    reveal_answers: f.reveal,
  };
}

export const moveItem = (list, from, to) => {
  if (to < 0 || to >= list.length) return list;
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
};
