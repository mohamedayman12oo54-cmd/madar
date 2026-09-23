"""
Password rules — kept in exact lockstep with the frontend's PW_RULES in
src/auth/ui.jsx:
    len : at least 8 characters
    up  : at least one uppercase letter (A-Z)
    low : at least one lowercase letter (a-z)
    num : at least one digit (0-9)
    sp  : at least one non-alphanumeric ("special") character

If the frontend's rules ever change, update PASSWORD_RULES here to match —
the two lists are intentionally structured the same way so a diff is easy.
"""
import re

from django.core.exceptions import ValidationError


PASSWORD_RULES = [
    ("len", "كلمة المرور يجب أن تكون ٨ أحرف على الأقل.", lambda v: len(v) >= 8),
    ("up", "كلمة المرور يجب أن تحتوي على حرف كبير (A-Z).", lambda v: re.search(r"[A-Z]", v) is not None),
    ("low", "كلمة المرور يجب أن تحتوي على حرف صغير (a-z).", lambda v: re.search(r"[a-z]", v) is not None),
    ("num", "كلمة المرور يجب أن تحتوي على رقم (0-9).", lambda v: re.search(r"\d", v) is not None),
    ("sp", "كلمة المرور يجب أن تحتوي على رمز خاص (!@#…).", lambda v: re.search(r"[^A-Za-z0-9]", v) is not None),
]


def password_meets_rules(value: str) -> bool:
    return all(test(value) for _, _, test in PASSWORD_RULES)


class MadarPasswordValidator:
    """Django AUTH_PASSWORD_VALIDATORS-compatible wrapper around the rules
    above, so both Django's own password-change machinery (e.g. the admin
    "change password" form) and our DRF serializers enforce the same
    policy as the public signup / reset screens."""

    def validate(self, password, user=None):
        errors = [msg for _, msg, test in PASSWORD_RULES if not test(password)]
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return "٨ أحرف على الأقل، حرف كبير، حرف صغير، رقم، ورمز خاص."
