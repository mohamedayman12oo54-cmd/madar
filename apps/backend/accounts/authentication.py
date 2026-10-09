from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class MadarJWTAuthentication(JWTAuthentication):
    """The existing SimpleJWT authentication, plus one check: the token's
    `sv` (session version) claim must equal the user's current
    `session_version`.

    Bumping `User.session_version` (see accounts/session_revocation.py — done
    on password reset) therefore invalidates every access token issued
    before the bump immediately, instead of leaving stolen access tokens
    usable until their 30-minute expiry. Tokens minted before this claim
    existed are treated as version 0.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if validated_token.get("sv", 0) != user.session_version:
            raise AuthenticationFailed("انتهت الجلسة، برجاء تسجيل الدخول مرة أخرى.", code="session_revoked")
        if user.role == "student":
            # Checked on EVERY request (not only at login) so a teacher
            # deactivating a student takes effect immediately, even for a
            # token the student already holds.
            from academics.access import student_has_active_enrollment

            if not student_has_active_enrollment(user):
                raise AuthenticationFailed("حسابك غير مفعّل لدى أي معلّم حاليًا.", code="student_inactive")
        return user
