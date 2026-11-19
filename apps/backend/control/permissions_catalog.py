"""
The permission vocabulary of the Madar Control Center and the built-in roles.

Every key here is enforced on the BACKEND by `control.access.HasControlPerm`; the frontend only uses the same
list to decide which menu entries to draw. A team member's effective permissions are:

    role.permissions  +  profile.extra_permissions  -  profile.revoked_permissions

`knowledge.manage` is the pre-existing Content Maintainer right (the Knowledge Base). A team account that has no
TeamProfile at all (every account created before the Control Center existed) keeps exactly that and nothing else,
so introducing roles never widens anybody's access.
"""

# key -> (group, Arabic label)
PERMISSIONS = {
    "overview.view": ("overview", "عرض لوحة النظرة العامة"),
    "users.view": ("users", "عرض المستخدمين"),
    "users.edit": ("users", "تعديل بيانات المستخدمين"),
    "users.suspend": ("users", "إيقاف المستخدمين وإعادة تفعيلهم"),
    "teachers.view": ("users", "عرض المعلّمين"),
    "students.view": ("users", "عرض الطلاب"),
    "parents.view": ("users", "عرض أولياء الأمور"),
    "environments.view": ("environments", "عرض البيئات التعليمية"),
    "environments.manage": ("environments", "تعديل بيانات البيئات"),
    "team.view": ("team", "عرض أعضاء الفريق"),
    "team.manage": ("team", "إدارة أعضاء الفريق"),
    "roles.view": ("team", "عرض الأدوار والصلاحيات"),
    "roles.manage": ("team", "إدارة الأدوار والصلاحيات"),
    "tickets.view": ("support", "عرض التذاكر"),
    "tickets.create": ("support", "إنشاء تذكرة نيابةً عن عميل"),
    "tickets.reply": ("support", "الرد على التذاكر وإضافة ملاحظات داخلية"),
    "tickets.assign": ("support", "إسناد التذاكر وإعادة إسنادها"),
    "tickets.priority": ("support", "تغيير أولوية التذكرة"),
    "tickets.resolve": ("support", "حل التذاكر وإغلاقها وإعادة فتحها"),
    "tickets.categories": ("support", "إدارة تصنيفات التذاكر"),
    "support.analytics": ("support", "عرض تحليلات الدعم"),
    "finance.view": ("business", "عرض البيانات المالية"),
    "ai.view": ("business", "عرض عمليات الذكاء الاصطناعي"),
    "notifications.view": ("business", "عرض الإشعارات"),
    "notifications.manage": ("business", "إرسال الإشعارات وإدارة القوالب"),
    "reports.view": ("analytics", "عرض التقارير وتصديرها"),
    "audit.view": ("system", "عرض سجل التدقيق"),
    "system.view": ("system", "عرض صحة النظام والعمليات الخلفية"),
    "settings.view": ("system", "عرض الإعدادات"),
    "settings.manage": ("system", "تعديل إعدادات المنصة"),
    "knowledge.manage": ("content", "إدارة قاعدة المعرفة"),
}

GROUP_LABELS = {
    "overview": "نظرة عامة",
    "users": "المستخدمون",
    "environments": "البيئات",
    "team": "الفريق والأدوار",
    "support": "الدعم الفني",
    "business": "العمليات التجارية",
    "analytics": "التحليلات",
    "system": "النظام",
    "content": "المحتوى",
}

ALL = sorted(PERMISSIONS)

_SUPPORT_CORE = ["tickets.view", "tickets.create", "tickets.reply", "tickets.priority", "tickets.resolve"]

# key -> (Arabic name, description, permissions)
SYSTEM_ROLES = {
    "super_admin": ("مدير عام", "كل الصلاحيات، بما فيها إدارة الأدوار. لا يمكن تقييده.", ALL),
    "admin": ("مدير", "كل الصلاحيات ما عدا إدارة الأدوار.", [p for p in ALL if p != "roles.manage"]),
    "support_manager": (
        "مدير الدعم", "يدير فريق الدعم والتذاكر وتحليلاتها.",
        ["overview.view", "users.view", "teachers.view", "students.view", "parents.view", "environments.view",
         *_SUPPORT_CORE, "tickets.assign", "tickets.categories", "support.analytics", "team.view",
         "notifications.view", "reports.view", "ai.view"],
    ),
    "support_agent": (
        "موظف دعم", "يتعامل مع التذاكر المسندة إليه.",
        ["overview.view", "users.view", "teachers.view", "students.view", "environments.view", *_SUPPORT_CORE],
    ),
    "technical_support": (
        "دعم فني", "يتابع المشكلات التقنية والذكاء الاصطناعي وصحة النظام.",
        ["overview.view", "users.view", "environments.view", "tickets.view", "tickets.reply", "tickets.resolve",
         "ai.view", "notifications.view", "system.view"],
    ),
    "finance_manager": (
        "مدير مالي", "يتابع المدفوعات والاشتراكات.",
        ["overview.view", "users.view", "environments.view", "finance.view", "tickets.view", "tickets.reply",
         "reports.view"],
    ),
    "content_manager": (
        "مدير المحتوى", "يدير قاعدة المعرفة.",
        ["overview.view", "knowledge.manage"],
    ),
    "analyst": (
        "محلّل", "يقرأ التقارير والمؤشرات المجمّعة فقط.",
        ["overview.view", "reports.view", "support.analytics", "finance.view", "ai.view"],
    ),
}

# What an account with no TeamProfile can do: exactly what the `team` role could do before roles existed.
LEGACY_PERMISSIONS = ["knowledge.manage"]
