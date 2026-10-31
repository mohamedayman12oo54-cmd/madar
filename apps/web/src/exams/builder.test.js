import test from "node:test";
import assert from "node:assert/strict";
import {
  blankForm,
  blankQuestion,
  fromExam,
  moveItem,
  toLimitedPayload,
  toPayload,
  trueFalseQuestion,
  validateExam,
} from "./builder.js";

const valid = () => {
  const f = blankForm();
  f.title = "امتحان";
  f.gradeIds = [1];
  f.questions = [blankQuestion()];
  f.questions[0].text = "سؤال؟";
  f.questions[0].choices.forEach((c, i) => (c.text = `اختيار ${i}`));
  return f;
};

test("a complete form has no problems", () => assert.deepEqual(validateExam(valid()), []));

test("every kind of mistake is reported in words", () => {
  const f = valid();
  f.title = " ";
  f.duration = "0";
  f.maxViolations = "11";
  f.questions[0].text = "";
  f.questions[0].choices[1].text = "";
  f.questions[0].choices[0].is_correct = false;
  const msgs = validateExam(f).join("|");
  for (const part of ["عنوان", "مدة", "المخالفات", "نص السؤال", "نص كل اختيار", "إجابة صحيحة"])
    assert.ok(msgs.includes(part), part);
});

test("two correct choices, duplicate choices and an empty paper are caught", () => {
  const two = valid();
  two.questions[0].choices[1].is_correct = true;
  assert.ok(validateExam(two).some((m) => m.includes("إجابة صحيحة")));
  const dup = valid();
  dup.questions[0].choices[1].text = dup.questions[0].choices[0].text;
  assert.ok(validateExam(dup).some((m) => m.includes("مكررة")));
  const empty = valid();
  empty.questions = [];
  assert.ok(validateExam(empty).some((m) => m.includes("سؤالًا واحدًا")));
});

test("the closing time must be in the future and after the opening time", () => {
  const f = valid();
  f.closes = "2020-01-01T10:00";
  assert.ok(validateExam(f).some((m) => m.includes("المستقبل")));
  const g = valid();
  g.opens = "2099-01-02T10:00";
  g.closes = "2099-01-01T10:00";
  assert.ok(validateExam(g).some((m) => m.includes("بعد موعد الفتح")));
});

test("the payload carries ids and trimmed text, with exactly one correct choice per question", () => {
  const f = valid();
  f.students = [{ id: 9, name: "س" }];
  f.questions[0].text = "  سؤال؟  ";
  const p = toPayload(f);
  assert.deepEqual(p.enrollment_ids, [9]);
  assert.equal(p.questions[0].text, "سؤال؟");
  assert.equal(p.questions[0].choices.filter((c) => c.is_correct).length, 1);
  assert.equal(p.duration_minutes, 30);
  assert.ok(!("key" in p.questions[0]));
});

test("true/false starts with two choices; the limited payload has only the four editable fields", () => {
  assert.deepEqual(
    trueFalseQuestion().choices.map((c) => c.text),
    ["صح", "خطأ"]
  );
  assert.deepEqual(Object.keys(toLimitedPayload(valid())).sort(), [
    "closes_at",
    "description",
    "reveal_answers",
    "title",
  ]);
});

test("an exam round-trips through the form", () => {
  const exam = {
    title: "ت",
    description: "",
    duration_minutes: 20,
    opens_at: null,
    closes_at: "2099-01-01T10:00:00Z",
    shuffle_questions: false,
    shuffle_choices: true,
    results_release: "after_close",
    reveal_answers: true,
    max_violations: 4,
    targets: { grades: [{ id: 1, name: "أول" }], groups: [], students: [] },
    questions: [
      {
        text: "س",
        points: 2,
        choices: [
          { text: "أ", is_correct: true },
          { text: "ب", is_correct: false },
        ],
      },
    ],
  };
  const back = toPayload(fromExam(exam));
  assert.equal(back.duration_minutes, 20);
  assert.equal(back.results_release, "after_close");
  assert.equal(back.opens_at, null);
  assert.deepEqual(back.grade_ids, [1]);
  assert.equal(back.questions[0].points, 2);
});

test("moveItem reorders and ignores out-of-range moves", () => {
  assert.deepEqual(moveItem([1, 2, 3], 0, 1), [2, 1, 3]);
  assert.deepEqual(moveItem([1, 2, 3], 0, -1), [1, 2, 3]);
});
