from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import PendingAuth, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["username", "name", "role", "email", "phone", "is_active", "is_verified", "date_joined"]
    list_filter = ["role", "is_active", "is_verified", "is_staff"]
    search_fields = ["username", "name", "email", "phone"]
    readonly_fields = ["date_joined", "last_login"]
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Identity", {"fields": ("role", "name", "email", "phone")}),
        ("Status", {"fields": ("is_active", "is_verified", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "role", "name", "email", "phone", "password1", "password2", "is_active", "is_verified"),
        }),
    )


@admin.register(PendingAuth)
class PendingAuthAdmin(admin.ModelAdmin):
    list_display = ["id", "purpose", "target", "verified", "otp_attempts", "created_at"]
    list_filter = ["purpose", "verified"]
    readonly_fields = [f.name for f in PendingAuth._meta.fields]

    def has_add_permission(self, request):
        return False
