from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.models import User, normalize_phone
from .models import Environment, EnvironmentMembership


def fmt_last(dt):
    if not dt:
        return None
    from django.utils import timezone
    from django.utils.timesince import timesince

    delta = timezone.now() - dt
    if delta.days == 0:
        return "آخر دخول: اليوم"
    if delta.days == 1:
        return "آخر دخول: أمس"
    return f"آخر دخول: قبل {timesince(dt, timezone.now()).split(',')[0]}"


class TeacherEnvironmentSerializer(serializers.ModelSerializer):
    last = serializers.SerializerMethodField()
    meta = serializers.CharField(source="academic_year")

    class Meta:
        model = Environment
        fields = ["id", "name", "initials", "meta", "subject_stage", "last"]

    def get_last(self, obj):
        membership = obj.memberships.filter(user=self.context["request"].user).first()
        return fmt_last(membership.last_accessed_at) if membership else None


class StudentEnvironmentSerializer(serializers.Serializer):
    """A student sees the *teacher's* identity for each environment
    they're in, matching EnvCard usage in StudentEnvSelect (initials/name
    are the teacher's, not the environment's own)."""

    id = serializers.IntegerField(source="environment.id")
    name = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()
    meta = serializers.CharField(source="environment.academic_year")
    last = serializers.SerializerMethodField()

    def get_name(self, membership):
        return membership.environment.owner.name

    def get_initials(self, membership):
        return membership.environment.owner.initials

    def get_last(self, membership):
        return fmt_last(membership.last_accessed_at)
