"""
Country-aware MOBILE phone validation (the single source of truth on the
server; mirrored by src/lib/phone.js on the client — keep both in lockstep).

Why mobile only: every phone in Madar receives an OTP (claiming, signup,
password reset), so a landline is never a usable identity.

What this checks: the number is a well-formed mobile number for a supported
country (dial code + national number length + valid mobile prefix). It does
NOT prove the line exists or belongs to the person — that is what the OTP is
for. Unsupported countries are rejected rather than guessed at.

Canonical stored form: digits only, dial code + national number, no "+",
no trunk "0"  (Egypt 010 1234 5678 -> "201012345678"). Arabic-Indic digits
are accepted and converted, so the same real number can never be stored twice
under different formatting.
"""
import re
from dataclasses import dataclass
from typing import Optional

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


@dataclass(frozen=True)
class Country:
    iso: str
    dial: str
    name: str      # Arabic display name
    pattern: str   # national (significant) mobile number, without trunk 0
    example: str


COUNTRIES = (
    Country("EG", "20", "مصر", r"1[0125]\d{8}", "1001234567"),
    Country("SA", "966", "السعودية", r"5\d{8}", "512345678"),
    Country("AE", "971", "الإمارات", r"5[024568]\d{7}", "501234567"),
    Country("KW", "965", "الكويت", r"[569]\d{7}", "50012345"),
    Country("QA", "974", "قطر", r"[3567]\d{7}", "33123456"),
    Country("BH", "973", "البحرين", r"[36]\d{7}", "36001234"),
    Country("OM", "968", "عُمان", r"(?:7[126-9]\d|9[1-9]\d)\d{5}", "92123456"),
    Country("JO", "962", "الأردن", r"7[789]\d{7}", "790123456"),
    Country("LB", "961", "لبنان", r"(?:3\d{6}|(?:7[01689]|81)\d{6})", "71123456"),
    Country("IQ", "964", "العراق", r"7[3-9]\d{8}", "7912345678"),
    Country("SY", "963", "سوريا", r"9(?:22|[3-689]\d)\d{6}", "944567890"),
    Country("PS", "970", "فلسطين", r"5[69]\d{7}", "599123456"),
    Country("YE", "967", "اليمن", r"7[0137]\d{7}", "712345678"),
    Country("LY", "218", "ليبيا", r"9[1-6]\d{7}", "912345678"),
    Country("TN", "216", "تونس", r"[2459]\d{7}", "20123456"),
    Country("DZ", "213", "الجزائر", r"[567]\d{8}", "551234567"),
    Country("MA", "212", "المغرب", r"[67]\d{8}", "612345678"),
    Country("SD", "249", "السودان", r"(?:1[0-2]|9[0-3569])\d{7}", "912345678"),
)

BY_ISO = {c.iso: c for c in COUNTRIES}
_COMPILED = {c.iso: re.compile(c.pattern) for c in COUNTRIES}
# Dial codes are prefix-free (E.164), so the first match is the only match.
_BY_DIAL = {c.dial: c for c in COUNTRIES}

DEFAULT_COUNTRY = "EG"
MAX_RAW_LENGTH = 32


class PhoneError(ValueError):
    """`code`: empty | chars | unsupported | invalid.  `message_ar` is safe to show."""

    def __init__(self, code, message_ar):
        super().__init__(message_ar)
        self.code = code
        self.message_ar = message_ar


def to_ascii_digits(value) -> str:
    return str(value or "").translate(_ARABIC_DIGITS)


def digits_only(value) -> str:
    return re.sub(r"\D", "", to_ascii_digits(value))


def _match_dial(digits: str) -> Optional[Country]:
    for length in (3, 2):
        country = _BY_DIAL.get(digits[:length])
        if country:
            return country
    return None


def _validate_national(country: Country, national: str) -> str:
    if len(national) > 1 and national.startswith("0"):
        national = national[1:]  # people type +20 010… — drop the stray trunk 0
    if not _COMPILED[country.iso].fullmatch(national):
        raise PhoneError("invalid", f"أدخل رقم موبايل صحيح لدولة {country.name}.")
    return country.dial + national


def canonical_phone(raw, default_country: Optional[str] = None) -> str:
    """Return the canonical digits-only international number or raise PhoneError.

    default_country=None  -> strict: the number MUST carry its country code
                             (the API contract for every phone field).
    default_country="EG"  -> lenient, ONLY for the teacher login identifier:
                             a local number such as 010… is read as Egyptian.
    """
    text = to_ascii_digits(raw).strip()
    if not text:
        raise PhoneError("empty", "أدخل رقم الهاتف.")
    if len(text) > MAX_RAW_LENGTH or re.search(r"[^\d+\s().\-]", text):
        raise PhoneError("chars", "رقم الهاتف يحتوي على رموز غير مسموحة.")
    international = text.startswith("+") or text.startswith("00")
    digits = re.sub(r"\D", "", text)
    if text.startswith("00") and not text.startswith("+"):
        digits = digits[2:]
    if not digits:
        raise PhoneError("empty", "أدخل رقم الهاتف.")

    if international or default_country is None:
        country = _match_dial(digits)
        if not country:
            raise PhoneError("unsupported", "رمز الدولة غير مدعوم، اختر دولة من القائمة.")
        return _validate_national(country, digits[len(country.dial):])

    # Lenient path: an explicit country code first, else the default country.
    country = _match_dial(digits)
    if country:
        try:
            return _validate_national(country, digits[len(country.dial):])
        except PhoneError:
            pass
    return _validate_national(BY_ISO[default_country], digits)


def try_canonical_phone(raw, default_country: Optional[str] = None) -> Optional[str]:
    try:
        return canonical_phone(raw, default_country)
    except PhoneError:
        return None


def country_of(canonical: str) -> Optional[Country]:
    return _match_dial(canonical or "")
