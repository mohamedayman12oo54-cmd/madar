"""
Progressive lock-out after repeated WRONG credentials / codes.

Policy (product-owner decision, Oct 2026): a first round of FIRST_ROUND_FAILS wrong attempts locks the
target for LOCK_SECONDS (5 minutes); after that every further round allows ROUND_FAILS attempts, then
locks for another LOCK_SECONDS, and so on. A correct answer clears the counters.

This complements, and does not replace, the per-IP / per-identifier request-rate throttles in
`throttles.py`: those cap how FAST anyone may try, this caps how many WRONG guesses a target absorbs.

The key is a hash of the normalised identifier taken from the INPUT (never from whether an account
exists), so the lock-out itself is not an account-enumeration oracle. Counters live in the shared
cache (one bucket for every web worker, like the throttles). They expire after IDLE_SECONDS without a
failure, so an honest user who mistyped once yesterday starts fresh.
"""
import hashlib
import time

from django.core.cache import cache
from rest_framework.exceptions import Throttled

FIRST_ROUND_FAILS = 6
ROUND_FAILS = 5
LOCK_SECONDS = 5 * 60
IDLE_SECONDS = 60 * 60


class LockedOut(Throttled):
    """429 whose message names the wait, so the user knows when to try again."""

    default_code = "locked_out"

    def __init__(self, wait):
        minutes = max(1, -(-int(wait) // 60))
        super().__init__(
            wait=wait,
            detail=f"تم تجاوز عدد المحاولات المسموح بها. حاول مرة أخرى بعد {minutes} "
                   f"{'دقيقة' if minutes == 1 else 'دقائق'}.",
        )


def _keys(scope, ident):
    digest = hashlib.sha256(f"{scope}:{ident}".encode("utf-8")).hexdigest()[:32]
    return (f"lock:fails:{digest}", f"lock:round:{digest}", f"lock:until:{digest}")


def check(scope, ident):
    """Raise LockedOut while the target is locked. Call BEFORE evaluating the guess."""
    if not ident:
        return
    until = cache.get(_keys(scope, ident)[2])
    now = time.time()
    if until and until > now:
        raise LockedOut(until - now)


def record_failure(scope, ident):
    """Count one wrong guess; start a lock when the round's allowance is used up."""
    if not ident:
        return
    k_fails, k_round, k_until = _keys(scope, ident)
    rounds = cache.get(k_round, 0)
    limit = FIRST_ROUND_FAILS if rounds == 0 else ROUND_FAILS
    cache.add(k_fails, 0, IDLE_SECONDS)
    try:
        fails = cache.incr(k_fails)
    except ValueError:  # expired between add() and incr()
        cache.set(k_fails, 1, IDLE_SECONDS)
        fails = 1
    if fails >= limit:
        cache.set(k_until, time.time() + LOCK_SECONDS, LOCK_SECONDS)
        cache.delete(k_fails)
        cache.set(k_round, rounds + 1, IDLE_SECONDS + LOCK_SECONDS)


def record_success(scope, ident):
    if not ident:
        return
    for k in _keys(scope, ident):
        cache.delete(k)


def guarded(scope, ident, attempt):
    """Run `attempt()` (which raises ValidationError on a wrong guess) under the lock-out policy."""
    from rest_framework.exceptions import ValidationError

    check(scope, ident)
    try:
        result = attempt()
    except ValidationError:
        record_failure(scope, ident)
        raise
    record_success(scope, ident)
    return result
