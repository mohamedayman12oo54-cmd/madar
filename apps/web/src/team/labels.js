// Arabic labels and badge tones for every enum the Control Center shows. One place, so a status looks the same everywhere.
export const TICKET_STATUS = {
  open: ["مفتوحة", "info"],
  in_progress: ["قيد المعالجة", "warn"],
  waiting_for_user: ["بانتظار العميل", "plain"],
  resolved: ["تم الحل", "ok"],
  closed: ["مغلقة", "plain"],
};
export const PRIORITY = { low: "منخفضة", medium: "متوسطة", high: "عالية", critical: "حرجة" };
export const RESPONSE = {
  awaiting_team: ["بانتظار الفريق", "warn"],
  awaiting_customer: ["بانتظار العميل", "plain"],
  done: ["—", "plain"],
};
export const KIND = { ticket: "تذكرة", complaint: "شكوى" };
export const USER_ROLE = { teacher: "معلّم", student: "طالب", parent: "ولي أمر", other: "آخر", team: "فريق" };
export const ACCOUNT_STATUS = { active: ["نشط", "ok"], suspended: ["موقوف", "bad"], pending: ["بانتظار التفعيل", "warn"] };
export const PAYMENT_STATUS = {
  initiated: ["بدأت", "plain"],
  pending: ["قيد المعالجة", "warn"],
  succeeded: ["ناجحة", "ok"],
  failed: ["فاشلة", "bad"],
  unknown: ["تحتاج مطابقة", "warn"],
};
export const SUB_STATE = {
  trial: ["تجريبي", "info"],
  active: ["نشط", "ok"],
  past_due: ["متأخر السداد", "warn"],
  canceled: ["ملغى (ينتهي بنهاية الفترة)", "plain"],
  expired: ["منتهي", "bad"],
};
export const AI_STATUS = {
  pending: ["قيد الانتظار", "plain"],
  processing: ["قيد المعالجة", "warn"],
  completed: ["مكتملة", "ok"],
  failed: ["فشلت", "bad"],
};
export const DELIVERY = { pending: ["قيد الإرسال", "warn"], sent: ["سُلّم لخدمة الدفع", "info"], failed: ["فشل", "bad"] };
export const NOTICE_DELIVERY = {
  queued: "في الانتظار",
  sent: "سُلّم لخدمة الدفع",
  failed: "فشل",
  no_device: "بلا جهاز مفعّل",
};
export const JOB_STATUS = {
  ok: ["سليم", "ok"],
  failed: ["فشل آخر تشغيل", "bad"],
  quiet: ["لم يُشغَّل منذ فترة", "warn"],
  never: ["لا يوجد تشغيل مسجّل", "plain"],
};
export const AUDIT_ACTIONS = {
  view: "اطّلاع على بيانات",
  "user.update": "تعديل مستخدم",
  "user.suspend": "إيقاف حساب",
  "user.restore": "إعادة تفعيل حساب",
  "team.role": "تغيير دور عضو",
  "team.permissions": "تغيير صلاحيات عضو",
  "team.activate": "تفعيل عضو",
  "team.deactivate": "تعطيل عضو",
  "team.update": "تعديل عضو",
  "role.create": "إنشاء دور",
  "role.update": "تعديل دور",
  "role.delete": "حذف دور",
  "ticket.create": "إنشاء تذكرة",
  "ticket.reply": "رد على تذكرة",
  "ticket.note": "ملاحظة داخلية",
  "ticket.status": "تغيير حالة تذكرة",
  "ticket.reopen": "إعادة فتح تذكرة",
  "ticket.priority": "تغيير أولوية",
  "ticket.assign": "إسناد تذكرة",
  "ticket.category": "تغيير تصنيف",
  "ticket.bulk": "إجراء جماعي على التذاكر",
  "ticket_category.create": "إنشاء تصنيف",
  "ticket_category.update": "تعديل تصنيف",
  "ticket_category.delete": "حذف تصنيف",
  "environment.update": "تعديل بيئة",
  "notification.send": "إرسال إشعار منصة",
  "notification_template.create": "إنشاء قالب إشعار",
  "notification_template.update": "تعديل قالب إشعار",
  "notification_template.delete": "حذف قالب إشعار",
  "settings.update": "تعديل الإعدادات",
};
export const ENTITY = {
  user: "مستخدم",
  team_member: "عضو فريق",
  role: "دور",
  ticket: "تذكرة",
  ticket_category: "تصنيف",
  environment: "بيئة",
  guardian: "ولي أمر",
  ai_operation: "عملية ذكاء اصطناعي",
  notification: "إشعار",
  platform_notice: "إشعار منصة",
  notification_template: "قالب إشعار",
  settings: "إعدادات",
};
export const AI_KIND = { assistant: "المساعد الدراسي", state_recommendation: "اقتراح حالة الطالب", quiz_generation: "توليد اختبار" };
export const KPI = {
  total_users: "إجمالي المستخدمين",
  active_users: "المستخدمون النشطون",
  total_teachers: "المعلّمون",
  total_students: "الطلاب",
  total_environments: "البيئات التعليمية",
  open_tickets: "تذاكر مفتوحة",
  unassigned_tickets: "تذاكر غير مسندة",
  critical_complaints: "شكاوى حرجة",
  ai_success: "عمليات ذكاء اصطناعي ناجحة",
  ai_failed: "عمليات ذكاء اصطناعي فاشلة",
  payments_success: "مدفوعات ناجحة",
  payments_pending: "مدفوعات معلّقة",
};
export const ATTENTION = {
  critical_complaints: ["شكاوى حرجة أو عالية غير محلولة", "ادخل وعالجها أولًا"],
  overdue_tickets: ["تذاكر تجاوزت مهلة الحل", "تأخرت عن الموعد المحدد حسب أولويتها"],
  waiting_too_long: ["تذاكر تنتظر ردّ الفريق منذ وقت طويل", "لم يردّ عليها أحد خلال المهلة"],
  unassigned_tickets: ["تذاكر غير مسندة", "لا يملكها أي موظف"],
  failed_payments: ["عمليات دفع فاشلة أو تحتاج مطابقة", "خلال فترة المراقبة"],
  payment_verification: ["أحداث دفع تعذّر التحقق منها أو تطبيقها", "راجع صفحة مشكلات الدفع"],
  ai_failures: ["فشل متكرر في الذكاء الاصطناعي", "خلال آخر 24 ساعة"],
  job_failures: ["عمليات خلفية فشلت", "خلال آخر 24 ساعة"],
  notification_backlog: ["إشعارات عالقة في الانتظار", "الطابور متأخر عن المعتاد"],
};
export const REPORT_FILTERS = {
  users: ["role", "status", "environment"],
  teachers: ["status", "environment"],
  students: ["status", "environment"],
  environments: [],
  tickets: ["status", "role", "environment"],
  agents: [],
  finance: ["status", "environment"],
  ai: ["status", "environment"],
  notifications: ["status", "environment"],
  admin_activity: [],
};
