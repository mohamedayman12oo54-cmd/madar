// Country-aware MOBILE phone validation. Mirrors madar-backend/accounts/phones.py
// rule-for-rule (the server is still the authority — this only gives instant
// feedback). Keep the two lists in lockstep; phone.test.js and the backend's
// test_phones.py use the same sample numbers.
//
// Mobile only, because every Madar phone receives an OTP. A format check does
// not prove the line exists — the OTP does that.

export const COUNTRIES = [
  { iso: "EG", dial: "20", name: "مصر", pattern: "1[0125]\\d{8}", example: "1001234567" },
  { iso: "SA", dial: "966", name: "السعودية", pattern: "5\\d{8}", example: "512345678" },
  { iso: "AE", dial: "971", name: "الإمارات", pattern: "5[024568]\\d{7}", example: "501234567" },
  { iso: "KW", dial: "965", name: "الكويت", pattern: "[569]\\d{7}", example: "50012345" },
  { iso: "QA", dial: "974", name: "قطر", pattern: "[3567]\\d{7}", example: "33123456" },
  { iso: "BH", dial: "973", name: "البحرين", pattern: "[36]\\d{7}", example: "36001234" },
  {
    iso: "OM",
    dial: "968",
    name: "عُمان",
    pattern: "(?:7[126-9]\\d|9[1-9]\\d)\\d{5}",
    example: "92123456",
  },
  { iso: "JO", dial: "962", name: "الأردن", pattern: "7[789]\\d{7}", example: "790123456" },
  {
    iso: "LB",
    dial: "961",
    name: "لبنان",
    pattern: "(?:3\\d{6}|(?:7[01689]|81)\\d{6})",
    example: "71123456",
  },
  { iso: "IQ", dial: "964", name: "العراق", pattern: "7[3-9]\\d{8}", example: "7912345678" },
  {
    iso: "SY",
    dial: "963",
    name: "سوريا",
    pattern: "9(?:22|[3-689]\\d)\\d{6}",
    example: "944567890",
  },
  { iso: "PS", dial: "970", name: "فلسطين", pattern: "5[69]\\d{7}", example: "599123456" },
  { iso: "YE", dial: "967", name: "اليمن", pattern: "7[0137]\\d{7}", example: "712345678" },
  { iso: "LY", dial: "218", name: "ليبيا", pattern: "9[1-6]\\d{7}", example: "912345678" },
  { iso: "TN", dial: "216", name: "تونس", pattern: "[2459]\\d{7}", example: "20123456" },
  { iso: "DZ", dial: "213", name: "الجزائر", pattern: "[567]\\d{8}", example: "551234567" },
  { iso: "MA", dial: "212", name: "المغرب", pattern: "[67]\\d{8}", example: "612345678" },
  {
    iso: "SD",
    dial: "249",
    name: "السودان",
    pattern: "(?:1[0-2]|9[0-3569])\\d{7}",
    example: "912345678",
  },
];

export const DEFAULT_ISO = "EG";
export const COUNTRY_BY_ISO = Object.fromEntries(COUNTRIES.map((c) => [c.iso, c]));
const COMPILED = Object.fromEntries(
  COUNTRIES.map((c) => [c.iso, new RegExp(`^(?:${c.pattern})$`)])
);

const ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩";
const PERSIAN = "۰۱۲۳۴۵۶۷۸۹";

/** Arabic-Indic / Persian digits -> ASCII (people on Arabic keyboards type them). */
export function toAsciiDigits(value) {
  return String(value ?? "").replace(/[٠-٩۰-۹]/g, (ch) => {
    const i = ARABIC_INDIC.indexOf(ch);
    return String(i >= 0 ? i : PERSIAN.indexOf(ch));
  });
}

export function digitsOnly(value) {
  return toAsciiDigits(value).replace(/\D/g, "");
}

/** What the national-number box keeps: ASCII digits, no leading trunk 0, max 12. */
export function cleanNational(raw) {
  return digitsOnly(raw).replace(/^0+/, "").slice(0, 12);
}

/** "201001234567" / "+20 100…" -> { country, national } or null (unknown dial code). */
export function parseInternational(value) {
  const digits = digitsOnly(value);
  for (const len of [3, 2]) {
    const country = COUNTRIES.find((c) => c.dial === digits.slice(0, len));
    if (country) return { country, national: digits.slice(country.dial.length).replace(/^0+/, "") };
  }
  return null;
}

/** Error message (Arabic) for a full international number, or "" when valid.
 *  Set `required: false` to accept an empty value (optional fields). */
export function phoneError(value, { required = true } = {}) {
  const text = toAsciiDigits(value).trim();
  if (!text) return required ? "أدخل رقم الهاتف." : "";
  if (/[^\d+\s().-]/.test(text) || text.length > 32) return "رقم الهاتف يحتوي على رموز غير مسموحة.";
  const parsed = parseInternational(text);
  if (!parsed) return "رمز الدولة غير مدعوم، اختر دولة من القائمة.";
  if (!COMPILED[parsed.country.iso].test(parsed.national)) {
    return `أدخل رقم موبايل صحيح لدولة ${parsed.country.name}.`;
  }
  return "";
}

/** The canonical digits-only form the backend stores ("201001234567"), or null. */
export function canonicalPhone(value) {
  if (phoneError(value, { required: true })) return null;
  const { country, national } = parseInternational(value);
  return country.dial + national;
}

/** For display: "201001234567" -> "+20 1001234567" (always LTR in the UI). */
export function formatPhone(value) {
  const parsed = parseInternational(value);
  return parsed
    ? `+${parsed.country.dial} ${parsed.national}`
    : value
      ? `+${digitsOnly(value)}`
      : "";
}

/** "مصر (+20)" for a country <option>. Inside Arabic text the browser's bidi
 *  algorithm can move the "+" behind the digits ("20+"); an explicit LTR
 *  isolate (U+2066 ... U+2069) around the code keeps it as typed, anywhere. */
export const dialLabel = (c) => `${c.name} (\u2066+${c.dial}\u2069)`;
