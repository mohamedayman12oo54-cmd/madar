from django.db import transaction
from django.db.models import F
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import User


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
