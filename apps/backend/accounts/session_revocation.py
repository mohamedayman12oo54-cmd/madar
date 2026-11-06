from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenBackendError, TokenError
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .models import RevokedSession, User


@transaction.atomic
def revoke_all_sessions(user) -> None:
    """Invalidate every credential the user currently holds:
      * bump `session_version`  -> all outstanding ACCESS tokens stop working
      * blacklist every outstanding REFRESH token -> no new access tokens
    Call from any flow that must cut off existing sessions (password reset).
    """
    User.objects.filter(pk=user.pk).update(session_version=F("session_version") + 1)
    for token in OutstandingToken.objects.filter(user_id=user.pk):
        BlacklistedToken.objects.get_or_create(token=token)
    user.refresh_from_db(fields=["session_version"])


def is_session_revoked(sid) -> bool:
    return bool(sid) and RevokedSession.objects.filter(sid=sid).exists()


@transaction.atomic
def logout_session(raw_refresh) -> bool:
    """End the session a refresh token belongs to: its access tokens stop working now and the refresh token
    can never mint another. Idempotent: a refresh token that was already rotated away or blacklisted (a second
    tab, a retried request) still ends the session. -> False when `raw_refresh` is not a genuine, unexpired
    refresh token of this server (nothing is changed)."""
    try:
        payload = token_backend.decode(raw_refresh, verify=True)  # signature + expiry, but NOT the blacklist
    except TokenBackendError:
        return False
    if payload.get("token_type") != "refresh":
        return False
    sid = payload.get("sid")
    if sid:
        now = timezone.now()
        # Kept for the REFRESH lifetime: a refresh token another tab rotated just before this logout is not
        # blacklisted, so only this record stops it from reviving the session.
        refresh_life = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
        RevokedSession.objects.get_or_create(sid=sid, defaults={"expires_at": now + refresh_life + timedelta(minutes=1)})
        RevokedSession.objects.filter(expires_at__lt=now).delete()  # housekeeping: no token of those sessions can live
    try:
        RefreshToken(raw_refresh).blacklist()
    except TokenError:
        pass  # already blacklisted / rotated
    return True
