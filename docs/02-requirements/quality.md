# Quality Requirements

> **Authority:** Normative (quality attributes & their priority).
> **Source of truth** for the V1 quality-attribute ranking and the fast-session bar.
> **Depends on:** `01-product/`, architectural drivers.

## Priority ranking (when concerns conflict)

1. **Strict tenant isolation & data correctness** — non-negotiable; protects the multi-teacher model.
2. **Fast-session responsiveness** — attendance/recitation happen live during teaching.
3. **Speed-to-market / operational simplicity** — preferred over premature complexity.
4. **AI cost / latency control** — controlled, but AI must never compromise deterministic correctness.
5. **Scalability headroom** — supported with reasonable headroom; no distributed complexity for
   hypothetical future scale.

This ranking is the reference the architecture trades against (see
[`../04-architecture/architecture.md`](../04-architecture/architecture.md), QA-response table).

## Fast Session responsiveness

- The Fast Attendance and Fast Recitation interfaces shall remain fast and lightweight for groups of
  approximately **40–50 students**, with no unnecessary wait between students.
- Interaction shall feel **immediate** when advancing to the next student, recording a result, and
  continuing through the group.
- These interfaces shall work well on **typical mid-range smartphones**, not only high-end devices.
- No specific numeric response-time threshold is committed in V1 (avoiding false precision); the
  testable bar is "immediate, lightweight, usable at 40–50 per group on a mid-range phone."

> A native mobile app is **not** required to meet this bar; the Student and Teacher surfaces are web
> (Teacher responsive, Student mobile-first). Native/cross-platform is a deferred V2 direction.

## Isolation as a quality attribute

Multi-teacher isolation shall be **structurally enforced by construction**, centrally, not by
per-query convention — strong **logical** isolation without per-teacher physical databases. See
ADR-004 / ADR-007 / ADR-008.

## Security & privacy posture (principle-level)

Encryption in transit is mandatory; student data is accessible only through authenticated,
authorized, tenant/relationship-scoped paths; minor/student data is treated as sensitive. Detailed
retention/deletion/legal policy is deferred to Operations and is **not** asserted here. See
[`../08-cross-cutting/security-authz.md`](../08-cross-cutting/security-authz.md).

## Reliability of async paths

Deterministic educational data and teacher authority shall remain correct regardless of the
availability of external dependencies (LLM, push, video). AI/notification failures affect only the
AI/notification-assisted experience, never the deterministic core (ADR-005, ADR-006).
