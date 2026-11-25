// MOCK DATA ONLY — nothing here comes from the backend. This file is the single place to replace once the
// "state recommendation agent" has a real API: the pages read ONLY the shapes documented below.
//
// What the agent is imagined to do: watch the signals Madar already has (attendance, recitation, exams, quizzes,
// videos), find the topics a student is stuck on, and act by creating practice exams for exactly those topics —
// by itself, or after the guardian approves, depending on the autonomy level the guardian chose.
//
// child = {
//   id, student{name,grade,env,group},
//   state{key,previous,trend,confidence,updatedAt}, headline, story[{step,text}],
//   signals[{id,label,value,unit,delta,note}],
//   topics[{id,name,unit,mastery,history[6],evidence[],next}],
//   exams[{id,title,topics[],questions,minutes,difficulty,status,score,max,createdAt,reason,auto}],
//   decisions[{id,kind,title,why,evidence[],at,autonomy,examId?}],
//   weeklyUsed, plan[{day,items[{type,text}]}], tips[], defaults{autonomy,weeklyLimit,notify,weeklySummary}
// }

const HOUR = 3_600_000;
const ago = (hours) => new Date(Date.now() - hours * HOUR).toISOString();
const days = (n) => n * 24;

export const STATE_LABEL = { good: "جيد", needs_follow_up: "يحتاج متابعة", at_risk: "معرّض للخطر" };
export const STATE_TONE = { good: "good", needs_follow_up: "warn", at_risk: "bad" };
export const TREND_LABEL = { improving: "في تحسّن", steady: "مستقر", declining: "في تراجع" };

export const EXAM_STATUS = {
  ready: { label: "جاهز للبدء", tone: "good" },
  proposed: { label: "بانتظار موافقة ولي الأمر", tone: "warn" },
  completed: { label: "تم الحل", tone: "" },
  declined: { label: "تم رفضه", tone: "bad" },
  postponed: { label: "مؤجّل", tone: "warn" },
};

export const AUTONOMY_LEVELS = [
  {
    key: "suggest",
    title: "اقتراح فقط",
    text: "الوكيل يخبرك بما لاحظه ويقترح اختبارًا، ولا يُنشئ شيئًا قبل أن تطلب أنت ذلك.",
  },
  {
    key: "approval",
    title: "إنشاء بموافقتك",
    text: "الوكيل يجهّز الاختبار ويشرح سببه، ولا يصل إلى الطالب إلا بعد موافقتك.",
  },
  {
    key: "auto",
    title: "تلقائي ضمن حدود",
    text: "الوكيل ينشئ اختبارات التقوية بنفسه ويُبلغك، بشرط ألا يتجاوز الحد الأسبوعي الذي تحدده.",
  },
];

/** Plain rule used everywhere a score needs a colour: weak / in progress / strong. */
export const masteryTone = (m) => (m >= 75 ? "good" : m >= 50 ? "warn" : "bad");
export const masteryLabel = (m) => (m >= 75 ? "متمكّن" : m >= 50 ? "قيد التحسّن" : "يحتاج تقوية");
export const examPercent = (e) => (e.max ? Math.round((e.score * 100) / e.max) : null);
export const weakTopics = (child) => [...child.topics].filter((t) => t.mastery < 50).sort((a, b) => a.mastery - b.mastery);
export const topicsByNeed = (child) => [...child.topics].sort((a, b) => a.mastery - b.mastery);
export const completedExams = (exams) => exams.filter((e) => e.status === "completed");
export const averageExamPercent = (exams) => {
  const done = completedExams(exams).map(examPercent).filter((p) => p != null);
  return done.length ? Math.round(done.reduce((a, b) => a + b, 0) / done.length) : null;
};

const yousef = {
  id: "yousef",
  student: { name: "يوسف أحمد", grade: "الثالث الإعدادي", env: "أ. محمود — الرياضيات", group: "مجموعة السبت والثلاثاء" },
  state: { key: "needs_follow_up", previous: "at_risk", trend: "improving", confidence: 82, updatedAt: ago(5) },
  headline:
    "مستواه في الجبر بدأ يتحسن بعد آخر اختبارين، لكن الهندسة (تشابه المثلثات) ما زالت تحتاج تثبيتًا.",
  story: [
    { step: "لاحظ", text: "انخفض متوسط الامتحانات من 72% إلى 51% خلال أسبوعين، مع غياب حصتين." },
    { step: "قرر", text: "الأخطاء متركزة في التحليل إلى العوامل والمعادلات التربيعية، فلا حاجة لمراجعة المنهج كله." },
    { step: "فعل", text: "أنشأ اختبارين قصيرين على هذين الموضوعين فقط، وجهّز ثالثًا للتدريب المدمج." },
    { step: "النتيجة", text: "ارتفع إتقان التحليل من 29% إلى 38% وتحسّنت نتيجة آخر اختبار من 4/10 إلى 7/10." },
  ],
  signals: [
    { id: "attendance", label: "الحضور", value: 78, unit: "%", delta: -4, note: "غاب حصتين في آخر 3 أسابيع" },
    { id: "recitation", label: "التسميع", value: 62, unit: "%", delta: 8, note: "ذاكر 5 من آخر 8 حصص" },
    { id: "exams", label: "متوسط الامتحانات", value: 58, unit: "%", delta: 7, note: "آخر امتحانين رسميين" },
    { id: "quizzes", label: "كويزات الذكاء الاصطناعي", value: 64, unit: "%", delta: 12, note: "حلّ 4 كويزات هذا الشهر" },
    { id: "videos", label: "إكمال الفيديوهات", value: 45, unit: "%", delta: -6, note: "أكمل 5 من 11 فيديو" },
  ],
  topics: [
    {
      id: "factoring", name: "التحليل إلى العوامل", unit: "الجبر", mastery: 38, history: [29, 29, 31, 33, 35, 38],
      evidence: [
        "أخطأ في 5 من 8 أسئلة في كويز التحليل.",
        "لم يُكمل جزء «الفرق بين مربعين» من الفيديو الخاص بالدرس.",
        "الاختبار التشخيصي: 4/10، والتدريب التالي: 7/10.",
      ],
      next: "اختبار قصير إضافي بعد مراجعة فيديو الفرق بين مربعين.",
    },
    {
      id: "quadratics", name: "المعادلات التربيعية", unit: "الجبر", mastery: 52, history: [38, 40, 43, 46, 49, 52],
      evidence: ["نجح في الحل بالتحليل، لكن يتعثر عند استخدام القانون العام.", "أخطاء حسابية متكررة في إشارة المميّز."],
      next: "اختبار «تدريب مدمج» جاهز الآن للبدء.",
    },
    {
      id: "similarity", name: "تشابه المثلثات", unit: "الهندسة", mastery: 41, history: [48, 46, 45, 44, 42, 41],
      evidence: [
        "أجاب عن 3 من 8 أسئلة بشكل صحيح في آخر كويز.",
        "غاب عن حصة الهندسة الأخيرة، ولم يشاهد فيديو الشرح.",
      ],
      next: "الوكيل اقترح اختبارًا مخصصًا وينتظر موافقة ولي الأمر.",
    },
    {
      id: "linear", name: "الدوال الخطية", unit: "الجبر", mastery: 67, history: [60, 61, 63, 64, 66, 67],
      evidence: ["أداء جيد في الرسم، مع تعثر بسيط في إيجاد معادلة الخط من نقطتين."],
      next: "لا يحتاج اختبارًا الآن؛ سيراجعها الوكيل ضمن الاختبار الشهري.",
    },
    {
      id: "pythagoras", name: "نظرية فيثاغورس", unit: "الهندسة", mastery: 78, history: [70, 72, 73, 75, 77, 78],
      evidence: ["أجاب بشكل صحيح عن 7 من 8 أسئلة في الكويز الأخير."],
      next: "متمكّن — لا إجراء مطلوب.",
    },
    {
      id: "statistics", name: "الإحصاء", unit: "الإحصاء", mastery: 86, history: [80, 82, 83, 84, 85, 86],
      evidence: ["نتائج ثابتة فوق 80% في آخر ثلاثة تقييمات."],
      next: "متمكّن — لا إجراء مطلوب.",
    },
  ],
  exams: [
    {
      id: "e3", title: "تدريب مدمج: المعادلات التربيعية", topics: ["المعادلات التربيعية"], questions: 8, minutes: 12,
      difficulty: "متوسط", status: "ready", createdAt: ago(6), auto: true,
      reason: "إتقان المعادلات التربيعية 52%، والأخطاء متركزة في إشارة المميّز.",
    },
    {
      id: "e4", title: "تدريب مخصص: تشابه المثلثات", topics: ["تشابه المثلثات"], questions: 10, minutes: 15,
      difficulty: "سهل ثم متوسط", status: "proposed", createdAt: ago(days(3)), auto: false,
      reason: "تراجع إتقان تشابه المثلثات من 48% إلى 41% مع غياب عن آخر حصة هندسة. الاختبار يبدأ بأسئلة سهلة لإعادة بناء الثقة.",
    },
    {
      id: "e2", title: "تدريب موجّه: التحليل إلى العوامل", topics: ["التحليل إلى العوامل"], questions: 10, minutes: 15,
      difficulty: "متوسط", status: "completed", score: 7, max: 10, createdAt: ago(days(14)), auto: true,
      reason: "بعد الاختبار التشخيصي ظهر أن العثرة في الفرق بين مربعين.",
    },
    {
      id: "e1", title: "اختبار تشخيصي: الجبر", topics: ["التحليل إلى العوامل", "المعادلات التربيعية"], questions: 10, minutes: 15,
      difficulty: "متدرّج", status: "completed", score: 4, max: 10, createdAt: ago(days(20)), auto: true,
      reason: "هبوط مفاجئ في متوسط الامتحانات؛ يلزم تحديد الموضوع المسبب بدقة قبل أي تدريب.",
    },
  ],
  decisions: [
    {
      id: "d9", kind: "exam", title: "جهّز اختبار «المعادلات التربيعية»", at: ago(6), autonomy: "auto",
      why: "أُنشئ تلقائيًا ضمن الحد الأسبوعي (2 من 3 مستخدم). الموضوع: المعادلات التربيعية.",
      evidence: ["إتقان الموضوع 52%", "أخطاء متكررة في إشارة المميّز"],
    },
    {
      id: "d7", kind: "decision", examId: "e4", title: "اقترح اختبارًا في «تشابه المثلثات»", at: ago(days(3)), autonomy: "approval",
      why: "الاختبار الجديد يمسّ موضوعًا في الهندسة خارج ما درّبه الوكيل سابقًا، فطلب موافقة ولي الأمر أولًا.",
      evidence: ["3 من 8 صحيحة في الكويز", "غياب عن آخر حصة هندسة"],
    },
    {
      id: "d6", kind: "observation", title: "لاحظ تراجعًا في «تشابه المثلثات»", at: ago(days(3) + 2), autonomy: "info",
      why: "انخفض الإتقان من 48% إلى 41% خلال ثلاثة أسابيع بينما بقيت بقية الهندسة مستقرة.",
      evidence: ["كويز 3/8", "لم يشاهد فيديو الشرح"],
    },
    {
      id: "d8", kind: "state", title: "تحسّنت الحالة من «معرّض للخطر» إلى «يحتاج متابعة»", at: ago(days(6)), autonomy: "info",
      why: "ارتفع متوسط الكويزات 12 نقطة وتحسّنت نتيجة آخر تدريب. ما زال الحضور أقل من 80%.",
      evidence: ["متوسط الكويزات 64%", "الحضور 78%"],
    },
    {
      id: "d5", kind: "result", title: "نتيجة التدريب الموجّه: 7/10", at: ago(days(10)), autonomy: "info",
      why: "تحسّن بثلاث درجات عن الاختبار التشخيصي في نفس الموضوع، فتقرّر الإبقاء على نفس النمط.",
      evidence: ["من 4/10 إلى 7/10", "إتقان التحليل 33% ← 35%"],
    },
    {
      id: "d4", kind: "exam", title: "أنشأ «تدريب موجّه: التحليل إلى العوامل»", at: ago(days(14)), autonomy: "auto",
      why: "استهدف الفرق بين مربعين تحديدًا، وهو مصدر معظم الأخطاء في التشخيص.",
      evidence: ["5 من 8 أخطاء في التحليل"],
    },
    {
      id: "d3", kind: "result", title: "نتيجة الاختبار التشخيصي: 4/10", at: ago(days(18)), autonomy: "info",
      why: "حدّد التحليل إلى العوامل والمعادلات التربيعية كموضوعين ضعيفين، وأن باقي المنهج سليم.",
      evidence: ["إتقان التحليل 29%", "إتقان المعادلات 38%"],
    },
    {
      id: "d2", kind: "exam", title: "أنشأ «اختبارًا تشخيصيًا: الجبر»", at: ago(days(20)), autonomy: "auto",
      why: "قبل بناء أي تدريب، يلزم معرفة الموضوع المسبب للهبوط بدلًا من التخمين.",
      evidence: ["متوسط الامتحانات 72% ← 51%"],
    },
    {
      id: "d1", kind: "observation", title: "لاحظ هبوطًا مفاجئًا في الامتحانات", at: ago(days(21)), autonomy: "info",
      why: "انخفض المتوسط 21 نقطة خلال امتحانين متتاليين مع غياب حصتين، فتغيّرت الحالة إلى «معرّض للخطر».",
      evidence: ["72% ← 51%", "غياب حصتين"],
    },
  ],
  plan: [
    { day: "السبت", items: [{ type: "class", text: "حصة المجموعة — 6:00 م" }] },
    { day: "الأحد", items: [{ type: "exam", text: "تدريب مدمج: المعادلات التربيعية (12 دقيقة)" }] },
    { day: "الاثنين", items: [{ type: "video", text: "فيديو: الفرق بين مربعين (18 دقيقة)" }] },
    { day: "الثلاثاء", items: [{ type: "class", text: "حصة المجموعة — 6:00 م" }] },
    { day: "الأربعاء", items: [{ type: "exam", text: "تدريب تشابه المثلثات — بعد موافقة ولي الأمر" }] },
  ],
  tips: [
    "شجّعه على مشاهدة فيديو «الفرق بين مربعين» قبل اختبار الأحد؛ هو سبب معظم أخطائه.",
    "اجلس معه 10 دقائق بعد كل اختبار لتراجعا الأسئلة الخاطئة فقط، لا الاختبار كله.",
    "حضور حصة السبت مهم هذا الأسبوع لأنها تشرح التشابه الذي تراجع فيه.",
    "إن غاب عن حصة، تواصل مع المعلم من صفحة المتابعة ليُعوَّض الشرح.",
  ],
  weeklyUsed: 2,
  defaults: { autonomy: "approval", weeklyLimit: 3, notify: true, weeklySummary: true },
};

const mariam = {
  id: "mariam",
  student: { name: "مريم أحمد", grade: "الأول الثانوي", env: "أ. هبة — اللغة العربية", group: "مجموعة الأحد والأربعاء" },
  state: { key: "good", previous: "good", trend: "steady", confidence: 91, updatedAt: ago(9) },
  headline: "مستواها ممتاز ومستقر. يراجع الوكيل النحو بشكل دوري ولا يرى حاجة لتدخل الآن.",
  story: [
    { step: "لاحظ", text: "نتائج الامتحانات والكويزات فوق 85% في آخر شهرين، والحضور 96%." },
    { step: "قرر", text: "لا توجد مواضيع ضعيفة. موضوع واحد (الأسلوب البلاغي) أقل من الباقي لكنه ضمن المقبول." },
    { step: "فعل", text: "لم يُنشئ اختبارات جديدة. جدولة مراجعة خفيفة للأسلوب البلاغي بعد أسبوعين." },
    { step: "النتيجة", text: "لا حاجة لإجراء منك الآن؛ سيُبلغك الوكيل فورًا إن تغيّر شيء." },
  ],
  signals: [
    { id: "attendance", label: "الحضور", value: 96, unit: "%", delta: 1, note: "لم تغب سوى حصة واحدة" },
    { id: "recitation", label: "التسميع", value: 92, unit: "%", delta: 2, note: "ذاكرت 11 من آخر 12 حصة" },
    { id: "exams", label: "متوسط الامتحانات", value: 88, unit: "%", delta: 0, note: "ثابت منذ شهرين" },
    { id: "quizzes", label: "كويزات الذكاء الاصطناعي", value: 90, unit: "%", delta: 3, note: "حلّت 6 كويزات هذا الشهر" },
    { id: "videos", label: "إكمال الفيديوهات", value: 91, unit: "%", delta: 4, note: "أكملت 10 من 11 فيديو" },
  ],
  topics: [
    {
      id: "grammar", name: "النحو والإعراب", unit: "اللغة", mastery: 91, history: [86, 87, 88, 89, 90, 91],
      evidence: ["أخطأت في سؤال واحد فقط من آخر 20 سؤالًا."], next: "متمكّنة — لا إجراء مطلوب.",
    },
    {
      id: "reading", name: "فهم المقروء", unit: "القراءة", mastery: 89, history: [85, 86, 87, 88, 88, 89],
      evidence: ["نتائج ثابتة فوق 85% في المقالات الأدبية والعلمية."], next: "متمكّنة — لا إجراء مطلوب.",
    },
    {
      id: "rhetoric", name: "الأسلوب البلاغي", unit: "البلاغة", mastery: 71, history: [66, 67, 68, 69, 70, 71],
      evidence: ["تخلط أحيانًا بين التشبيه والاستعارة في أسئلة المقارنة."],
      next: "مراجعة خفيفة مجدولة بعد أسبوعين.",
    },
    {
      id: "writing", name: "التعبير الكتابي", unit: "الكتابة", mastery: 83, history: [78, 79, 80, 81, 82, 83],
      evidence: ["تقييم المعلمة لآخر موضوعين: ممتاز."], next: "متمكّنة — لا إجراء مطلوب.",
    },
  ],
  exams: [
    {
      id: "m1", title: "مراجعة خفيفة: الأسلوب البلاغي", topics: ["الأسلوب البلاغي"], questions: 6, minutes: 8,
      difficulty: "سهل", status: "completed", score: 5, max: 6, createdAt: ago(days(30)), auto: true,
      reason: "مراجعة دورية لموضوع إتقانه أقل من 75%.",
    },
  ],
  decisions: [
    {
      id: "m4", kind: "observation", title: "راجع الحالة الأسبوعية — لا تغيّر", at: ago(9), autonomy: "info",
      why: "كل المؤشرات ثابتة أو أفضل من الأسبوع السابق، فلا يلزم أي اختبار أو تنبيه.",
      evidence: ["الحضور 96%", "متوسط الامتحانات 88%"],
    },
    {
      id: "m3", kind: "decision", title: "قرر عدم إنشاء اختبارات هذا الأسبوع", at: ago(days(7)), autonomy: "auto",
      why: "الوكيل لا ينشئ اختبارًا إلا لسبب واضح؛ لا يوجد موضوع تحت 70%.",
      evidence: ["أضعف موضوع: الأسلوب البلاغي 71%"],
    },
    {
      id: "m2", kind: "result", title: "نتيجة المراجعة الخفيفة: 5/6", at: ago(days(29)), autonomy: "info",
      why: "ارتفع إتقان الأسلوب البلاغي من 62% إلى 66%.",
      evidence: ["5 من 6 صحيحة"],
    },
    {
      id: "m1d", kind: "exam", title: "أنشأ مراجعة خفيفة في الأسلوب البلاغي", at: ago(days(30)), autonomy: "auto",
      why: "الموضوع كان أضعف من الباقي قليلًا، فاختار اختبارًا قصيرًا وسهلًا.",
      evidence: ["الإتقان 62%"],
    },
  ],
  plan: [
    { day: "الأحد", items: [{ type: "class", text: "حصة المجموعة — 5:00 م" }] },
    { day: "الثلاثاء", items: [{ type: "video", text: "فيديو: أساليب التشبيه والاستعارة (14 دقيقة)" }] },
    { day: "الأربعاء", items: [{ type: "class", text: "حصة المجموعة — 5:00 م" }] },
  ],
  tips: [
    "لا حاجة لتدخل. يكفي تشجيعها على الاستمرار على نفس الروتين.",
    "يمكنها حل كويز إضافي عن البلاغة إن أرادت تحديًا بدلًا من مجرد المراجعة.",
  ],
  weeklyUsed: 0,
  defaults: { autonomy: "auto", weeklyLimit: 2, notify: true, weeklySummary: true },
};

export const AGENT_CHILDREN = [yousef, mariam];

/** What the agent is allowed to do on its own, and where it must stop. Shown to guardians as the safety contract. */
export const GUARDRAILS = {
  does: [
    "يقرأ أرقام الحضور والتسميع والامتحانات والكويزات والفيديوهات.",
    "ينشئ اختبارات قصيرة من مواد المعلم المنشورة فقط.",
    "يشرح سبب كل قرار والدلائل التي بُني عليها.",
    "يلتزم بمستوى الاستقلالية والحد الأسبوعي الذي تحدده.",
  ],
  doesNot: [
    "لا يغيّر أي درجة أو تقييم أو سجل حضور.",
    "لا يراسل المعلم أو يرد باسمك.",
    "لا يتجاوز الحد الأسبوعي للاختبارات مهما كانت الحالة.",
    "لا يستخدم محتوى من خارج مواد المعلم.",
    "لا يقرر حالة نهائية للطالب؛ القرار النهائي دائمًا للمعلم.",
  ],
};

/** The signals the agent reads, listed once so the student/guardian can see exactly what it looks at. */
export const WATCHED = ["الحضور", "التسميع", "نتائج الامتحانات", "الكويزات", "مشاهدة الفيديوهات"];
