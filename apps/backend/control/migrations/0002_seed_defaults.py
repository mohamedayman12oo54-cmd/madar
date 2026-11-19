from django.db import migrations

from control.permissions_catalog import SYSTEM_ROLES

CATEGORIES = [
    "تسجيل الدخول والمصادقة", "مشكلات الحساب", "مشكلات المعلّمين", "مشكلات الطلاب", "مشكلات البيئة التعليمية",
    "مشكلات الجدولة", "مشكلات الحضور", "مشكلات التقييم", "المدفوعات والمشكلات المالية", "ميزات الذكاء الاصطناعي",
    "الإشعارات", "مشكلات تقنية", "اقتراحات وملاحظات", "أخرى",
]

TEMPLATES = [
    ("صيانة مجدولة", "صيانة مجدولة للمنصة", "ستخضع مدار لصيانة قصيرة قريبًا. قد تتوقف بعض الخدمات لدقائق."),
    ("ميزة جديدة", "ميزة جديدة في مدار", "أضفنا ميزة جديدة. افتح مدار لتتعرف عليها."),
    ("تذكير بالاشتراك", "تذكير بتجديد الاشتراك", "اشتراكك على وشك الانتهاء. جدّده لتستمر في استخدام جميع الميزات."),
    ("تم حل مشكلتك", "تم حل مشكلتك", "حلّ فريق الدعم المشكلة التي أبلغت عنها. افتح التذكرة للاطلاع على التفاصيل."),
]


def seed(apps, schema_editor):
    Role = apps.get_model("control", "Role")
    for key, (name, description, perms) in SYSTEM_ROLES.items():
        Role.objects.update_or_create(
            key=key, defaults={"name": name, "description": description, "permissions": sorted(perms), "is_system": True})
    Cat = apps.get_model("control", "TicketCategory")
    for i, name in enumerate(CATEGORIES):
        Cat.objects.get_or_create(name=name, defaults={"order": i})
    Tpl = apps.get_model("control", "NotificationTemplate")
    for name, title, body in TEMPLATES:
        Tpl.objects.get_or_create(name=name, defaults={"title": title, "body": body})


class Migration(migrations.Migration):
    dependencies = [("control", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
