// Small pure helpers for the student's exam screens (kept apart from the components so they can be tested).

export const nAr = (n) => Number(n ?? 0).toLocaleString("ar-EG", { maximumFractionDigits: 1 });
export const pctText = (p) => `${nAr(p)}٪`;
export const clampPct = (p) => Math.max(0, Math.min(100, Number(p) || 0));

/** mm:ss (or h:mm:ss) for a number of seconds, in Arabic digits. */
export function clock(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const sec = String(s % 60).padStart(2, "0");
  return (h ? `${h}:${m}:${sec}` : `${m}:${sec}`).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);
}

/** Result band: one colour class + a short, plain verdict. */
export function band(percent) {
  const p = clampPct(percent);
  if (p >= 90) return { cls: "is-great", label: "ممتاز" };
  if (p >= 75) return { cls: "is-good", label: "جيد جدًا" };
  if (p >= 60) return { cls: "is-fair", label: "جيد" };
  if (p >= 50) return { cls: "is-pass", label: "مقبول" };
  return { cls: "is-low", label: "تحتاج إلى مراجعة" };
}

/** "تحذير واحد" / "تحذيران" / "٣ تحذيرات" */
export function warningsText(n) {
  if (n === 1) return "تحذير واحد";
  if (n === 2) return "تحذيران";
  return `${nAr(n)} تحذيرات`;
}

export const CHOICE_LETTERS = ["أ", "ب", "ج", "د", "هـ", "و"];

/** What the student is told when the page reports a violation (the server's vocabulary -> plain Arabic). */
export const VIOLATION_TEXT = {
  blur: "غادرت نافذة الامتحان",
  hidden: "بدّلت التبويب أو صغّرت المتصفح",
  fullscreen_exit: "خرجت من الشاشة الكاملة",
  copy: "حاولت نسخ محتوى الامتحان",
  paste: "حاولت اللصق",
  contextmenu: "فتحت قائمة النقر الأيمن",
  print: "حاولت الطباعة أو تصوير الشاشة",
  shortcut: "استخدمت اختصارًا ممنوعًا",
};

/** The warning card's content from the server's counters: which warning this is and what happens next. */
export function warningInfo({ type, violations, max }) {
  const left = Math.max(0, max - violations);
  return {
    reason: VIOLATION_TEXT[type] || "تصرّف غير مسموح أثناء الامتحان",
    n: violations,
    max,
    left,
    final: left === 1,
    title: left === 1 ? "آخر تحذير" : "تحذير: سُجّلت مخالفة",
    next:
      left === 1
        ? "أي مخالفة أخرى ستُنهي الامتحان فورًا ويُسلَّم بما أجبت عليه."
        : `تبقّى لك ${warningsText(left)} قبل أن يُغلق الامتحان تلقائيًا.`,
  };
}

/** Share of the exam already passed, 0–100 (the question being answered does not count yet). */
export const progressPct = (index, total) => (total ? clampPct((100 * index) / total) : 0);
