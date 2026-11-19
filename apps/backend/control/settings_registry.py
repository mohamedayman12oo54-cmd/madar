"""Operating settings the team may tune at runtime. Only settings that the code really reads are listed: each one
is consumed by the support / health / attention logic through `get_setting()`. Values that are fixed by the
deployment (token lifetimes, lockout rules) are shown read-only by the settings endpoint, never editable here."""
from .models import PlatformSetting

# key -> (group, Arabic label, description, default, min, max)
REGISTRY = {
    "sla.critical_hours": ("ticket_workflow", "مهلة حل التذاكر الحرجة (ساعات)", "الوقت المتاح لحل تذكرة حرجة قبل اعتبارها متأخرة.", 4, 1, 720),
    "sla.high_hours": ("ticket_workflow", "مهلة حل التذاكر العالية (ساعات)", "الوقت المتاح لحل تذكرة عالية الأولوية.", 8, 1, 720),
    "sla.medium_hours": ("ticket_workflow", "مهلة حل التذاكر المتوسطة (ساعات)", "الوقت المتاح لحل تذكرة متوسطة الأولوية.", 24, 1, 720),
    "sla.low_hours": ("ticket_workflow", "مهلة حل التذاكر المنخفضة (ساعات)", "الوقت المتاح لحل تذكرة منخفضة الأولوية.", 72, 1, 720),
    "tickets.stale_hours": ("ticket_workflow", "تذكرة تنتظر ردّ الفريق (ساعات)", "تظهر في «يحتاج انتباهًا» إذا مرّ هذا الوقت دون رد من الفريق.", 12, 1, 720),
    "tickets.reopen_days": ("ticket_workflow", "مهلة إعادة فتح التذكرة المغلقة للعميل (أيام)", "المدة التي يستطيع العميل خلالها طلب إعادة فتح تذكرة مغلقة. الفريق يعيد الفتح دائمًا.", 7, 0, 365),
    "tickets.agent_overload": ("ticket_workflow", "حدّ ازدحام الموظف (تذاكر نشطة)", "الموظف الذي لديه هذا العدد أو أكثر من التذاكر النشطة يُعدّ مزدحمًا.", 15, 1, 500),
    "ai.repeated_failures": ("monitoring", "فشل متكرر للذكاء الاصطناعي (خلال 24 ساعة)", "عدد حالات الفشل الذي يُظهر تنبيهًا.", 5, 1, 1000),
    "ai.slow_seconds": ("monitoring", "عملية ذكاء اصطناعي بطيئة (ثوانٍ)", "العمليات التي تتجاوز هذه المدة تُعلَّم كبطيئة.", 60, 1, 3600),
    "notifications.pending_minutes": ("monitoring", "إشعار عالق في الانتظار (دقائق)", "يُعدّ الطابور متأخرًا إذا بقي إشعار قيد الإرسال أطول من ذلك.", 30, 1, 10080),
    "payments.attention_days": ("monitoring", "نافذة تنبيهات المدفوعات (أيام)", "عمليات الدفع الفاشلة خلال هذه المدة تظهر في «يحتاج انتباهًا».", 7, 1, 90),
}

GROUP_LABELS = {"ticket_workflow": "سير عمل التذاكر", "monitoring": "المراقبة والتنبيهات"}


def get_setting(key):
    row = PlatformSetting.objects.filter(key=key).first()
    return row.value if row is not None else REGISTRY[key][3]


def all_settings():
    stored = {s.key: s for s in PlatformSetting.objects.filter(key__in=REGISTRY)}
    return {k: (stored[k].value if k in stored else REGISTRY[k][3]) for k in REGISTRY}


def validate_value(key, value):
    reg = REGISTRY[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("القيمة يجب أن تكون رقمًا صحيحًا.")
    if not reg[4] <= value <= reg[5]:
        raise ValueError(f"القيمة يجب أن تكون بين {reg[4]} و{reg[5]}.")
    return value
