from django.contrib import admin

from .models import Environment, EnvironmentMembership


class MembershipInline(admin.TabularInline):
    model = EnvironmentMembership
    extra = 0
    readonly_fields = ["joined_at", "last_accessed_at"]


@admin.register(Environment)
class EnvironmentAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "academic_year", "initials", "created_at"]
    search_fields = ["name", "owner__name", "owner__email", "owner__phone"]
    inlines = [MembershipInline]


@admin.register(EnvironmentMembership)
class EnvironmentMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "environment", "role", "joined_at", "last_accessed_at"]
    list_filter = ["role"]
    search_fields = ["user__name", "user__phone", "user__email", "environment__name"]
