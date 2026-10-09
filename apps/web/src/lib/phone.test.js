import test from "node:test";
import assert from "node:assert/strict";
import { COUNTRIES, canonicalPhone, cleanNational, formatPhone, phoneError, parseInternational } from "./phone.js";

// Same samples as madar-backend/accounts/test_phones.py
const VALID = {
  "+20 100 123 4567": "201001234567",
  "00201001234567": "201001234567",
  "+201001234567": "201001234567",
  "+٢٠ ١٠٠ ١٢٣ ٤٥٦٧": "201001234567",
  "+20 0100 123 4567": "201001234567",
  "+966 55 123 4567": "966551234567",
  "+971 50 123 4567": "971501234567",
  "+965 5001 2345": "96550012345",
  "+962 79 012 3456": "962790123456",
  "+964 791 234 5678": "9647912345678",
  "+212 612 345 678": "212612345678",
};
const INVALID = [
  "", "   ", "abc", "+20abc", "+20 1301234567", "+20 100123456", "+20 10012345678",
  "+966 4 123 4567", "+966 5123456", "+971 51 234 5678",
  "+999 123456789", "+1 202 555 0123", "+20 100 123 4567; DROP TABLE", "<script>",
];

test("valid numbers normalise to one canonical form", () => {
  for (const [raw, expected] of Object.entries(VALID)) {
    // the "00…" prefix is a server-side convenience; the UI always sends +dial+national
    const input = raw.startsWith("00") ? "+" + raw.slice(2) : raw;
    assert.equal(canonicalPhone(input), expected, raw);
  }
});

test("invalid numbers are rejected with an Arabic message", () => {
  for (const raw of INVALID) {
    assert.ok(phoneError(raw), `should reject: ${JSON.stringify(raw)}`);
  }
});

test("every country accepts its own example and rejects an extra digit", () => {
  for (const c of COUNTRIES) {
    assert.equal(phoneError(`+${c.dial}${c.example}`), "", c.iso);
    assert.ok(phoneError(`+${c.dial}${c.example}0`), c.iso);
    assert.equal(parseInternational(`+${c.dial}${c.example}`).country.iso, c.iso);
  }
});

test("dial codes are prefix-free", () => {
  for (const a of COUNTRIES) for (const b of COUNTRIES) {
    if (a !== b) assert.ok(!b.dial.startsWith(a.dial), `${a.iso}/${b.iso}`);
  }
});

test("optional fields may be empty", () => {
  assert.equal(phoneError("", { required: false }), "");
  assert.ok(phoneError("+20 123", { required: false }));
});

test("national box keeps only digits, drops the trunk zero and Arabic digits are converted", () => {
  assert.equal(cleanNational("٠١٠ 0123-4567"), "10" + "01234567".slice(0, 8));
  assert.equal(cleanNational("010abc01234567"), "1001234567");
  assert.equal(formatPhone("201001234567"), "+20 1001234567");
});
