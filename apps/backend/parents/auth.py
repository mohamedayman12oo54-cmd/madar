"""
Guardian access without a Parent account.

The documentation forbids a global Parent entity and says parent contact is
teacher-scoped data. So a guardian never gets a User row: they get a **signed,
short-lived, read-only session token** bound to ONE Enrollment — the exact
enrollment whose `parent_phone` they proved they control via OTP.

Consequences that make this safe:
  * the teacher stays the source of truth — change `parent_phone` and the old
    guardian's next request resolves to nothing;
  * nothing is writable: there is no guardian write path anywhere;
  * the token names one enrollment, so a guardian of one child can never see
    another child, another teacher's environment, or a sibling.
"""
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from rest_framework import authentication, exceptions, permissions

SALT = "parents.session"
SESSION_TTL_SECONDS = 60 * 60 * 6  # a school day; re-verify by OTP after that


def guardian_visible_q():
    """A guardian can follow a child only once the CHILD has activated their own
    account (claimed it by OTP). The guardian never activates anything: their
    phone number, as recorded by the teacher, is the only thing they prove.
    Filter reused at request time, verify time and on every portal request, so
    deactivating the student ends the guardian's access immediately too."""
    from django.db.models import Q

    return Q(student__is_active=True, student__is_verified=True)


def issue_session(enrollment) -> str:
    return TimestampSigner(salt=SALT).sign(f"{enrollment.id}:{enrollment.parent_phone}")


class ParentPrincipal:
    """A non-persisted principal. Deliberately NOT a User: a guardian has no
    account, no password and no presence in the user table."""

    is_authenticated = True
    is_anonymous = False
    is_staff = False
    is_superuser = False
    role = "parent"

    def __init__(self, enrollment):
        self.enrollment = enrollment
        self.pk = None
        self.id = None

    def __str__(self):
        return f"guardian of enrollment {self.enrollment_id}"

    @property
    def enrollment_id(self):
        return self.enrollment.id


class ParentSessionAuthentication(authentication.BaseAuthentication):
    """`Authorization: Parent <token>`."""

    keyword = "Parent"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("رمز وصول غير صالح.")

        from academics.models import Enrollment

        try:
            raw = TimestampSigner(salt=SALT).unsign(header[1].decode(), max_age=SESSION_TTL_SECONDS)
        except (BadSignature, SignatureExpired, UnicodeDecodeError):
            raise exceptions.AuthenticationFailed("انتهت صلاحية الجلسة. سجّل الدخول مرة أخرى.")

        enrollment_id, _, phone = raw.partition(":")
        enrollment = (
            Enrollment.objects.filter(pk=enrollment_id, is_active=True)
            .filter(guardian_visible_q())
            .select_related("grade", "student", "environment").first()
        )
        # The phone is re-checked on every request: if the teacher corrected or
        # removed it, access ends immediately rather than at token expiry.
        if enrollment is None or enrollment.parent_phone != phone:
            raise exceptions.AuthenticationFailed("لم يعد هذا الرقم مرتبطًا بطالب.")
        return (ParentPrincipal(enrollment), None)

    def authenticate_header(self, request):
        return self.keyword


class IsParent(permissions.BasePermission):
    def has_permission(self, request, view):
        return isinstance(getattr(request, "user", None), ParentPrincipal)
