# Actor Lifecycles — Teacher & Environment

> **Authority:** Descriptive (canonical for the Teacher account and Teacher-Environment *lifecycle*).
> **Source of truth** for how a Teacher enters Madar, how a Teacher Environment comes into existence,
> and how the Teacher lifecycle connects to the existing Student lifecycle.
> **Depends on:** `00-overview/system-overview.md`, `03-domain/domain-model.md`,
> `01-product/access-lifecycle.md`, `08-cross-cutting/security-authz.md`.
> **Scope note:** this document establishes the **lifecycle** at the system/product level only. It
> deliberately does **not** specify authentication mechanisms, provisioning technology, cardinality
> rules, APIs, or storage — those are marked unresolved/deferred where not decided. It does not
> redefine any existing entity; it fills the upstream gap the lifecycle audit identified.

The existing documentation defined what a Teacher *does* once authenticated inside an existing
Environment, but not how the Teacher or the Environment come to exist. This document supplies that
upstream chain and connects it to the already-documented Student lifecycle (`security-authz.md`),
which is preserved unchanged.

## Teacher lifecycle

A Teacher progresses through these system-level states:

```
Prospective Teacher (has reached the product entry point)
        │  creates a Madar account
        ▼
Teacher Account (a Madar user/account holder)
        │  authenticates
        ▼
Authenticated Teacher
        │  establishes / receives access to their educational environment
        ▼
Teacher operating a Teacher Environment   ← the state all existing capability docs assume
```

- **Product entry.** A prospective Teacher reaches Madar through a product entry point and can begin
  the journey via a **Free Trial** (see `01-product/access-lifecycle.md`). The entry point's
  acquisition channels and UI are out of scope.
- **Account creation.** A prospective Teacher can **become a Madar account holder** — an account is
  created for the Teacher as a distinct actor. (Contrast: Students do **not** self-signup; they are
  teacher-created — `security-authz.md`. The Teacher account path is a *separate* path and does not
  alter the Student model.)
- **Authentication.** A Teacher account holder can **authenticate** to access Madar. The specific
  authentication mechanism (credentials, OTP, tokens, provider) is **not decided here** and is
  deferred to implementation, consistent with how claiming mechanics are already deferred.
- **Operating state.** Once authenticated and holding access to an Environment, the Teacher is in the
  state every existing capability document already assumes ("the authenticated actor… authorized
  environment"). Those documents remain unchanged; this chain simply explains how that state is
  reached.

The composite authorization model (`security-authz.md`, ADR-010) continues to govern what an
authenticated Teacher may do; nothing there changes.

## Teacher Environment lifecycle

The Teacher Environment keeps its existing meaning — **the isolation/tenant boundary** owning Academic
Years, Grades, Groups, Schedules, video metadata, and (through Enrollments) all educational records
(`00-overview/glossary.md`, `06-data/data-model.md`). This document adds only its **origin**:

```
Authenticated Teacher (no environment yet)
        │  environment is established as part of the Teacher's journey
        ▼
Teacher Environment exists (empty, ready for setup)
        │  initial setup populates it (see "Initial use" below)
        ▼
Active educational environment
```

- **Establishment.** A Teacher Environment is **established as part of the Teacher's product
  journey** — it is not a pre-existing given. It comes into existence in association with the Teacher
  becoming an operating user.
- **Initial state.** A newly established Environment is **empty**: it has no Grades, Groups, Academic
  Years, Enrollments, or records until the Teacher creates them.
- **Isolation unchanged.** Its tenant-boundary semantics (`teacher_environment_id`, server-derived
  context, two-layer enforcement — ADR-004/007/008) are unchanged. This document does not alter how
  isolation works; it only documents when/why the Environment first exists.

> **Resolved — permanent one-to-one cardinality.** A Teacher Account owns **exactly one** Teacher
> Environment, permanently (not a V1-only limitation). A Teacher wanting a second, separate environment
> creates another account. See INV-9 (`03-domain/invariants.md`) and
> `10-decisions/ADR-013-permanent-environment-cardinality.md`, which is the authoritative decision and
> reconciles this with ADR-008's "authorized environments" (plural) language — that phrasing describes
> the general server-derived-context mechanism (an actor is resolved against *whichever* environments
> it is authorized for) and is not, and was never intended as, a cardinality commitment; ADR-008 is
> otherwise unaffected and continues to govern context-resolution mechanics regardless of how many
> environments an actor type may hold.
>
> **The exact provisioning trigger/mechanics** (automatic on account creation vs. an explicit action)
> remain **not decided** — in the current signup flow, account creation and the one Environment's
> establishment happen atomically, but this is a description of today's code, not a binding
> specification of the only allowed mechanism. See `10-decisions/rejected-deferred.md`.
>
> **Implementation follow-up (not performed by this documentation pass):** enforcing the invariant at
> the Django ORM level (a `OneToOneField` is the expected semantic target, replacing the current plain
> `ForeignKey` on `Environment.owner`) and at the Postgres DB-integrity level; no live database has been
> checked for pre-existing violating data; and existing tests
> (e.g. `environments/tests.py:26-40`) currently assume multiple environments per teacher and will need
> updating to reflect the new invariant. These are implementation tasks, tracked but not resolved here.

## Initial use (empty → usable)

The existing requirements already define the *capabilities* for building the educational structure
(`02-requirements/functional.md` §Environment structure: create Grades, Groups, Schedules, register
students). This document adds only the **lifecycle framing** that connects an empty Environment to
active use:

```
Empty Environment
   → Teacher creates Academic Year / Grade(s) / Group(s) / Schedule(s)
   → Teacher introduces students (below)
   → educational operations proceed (03-domain/lifecycles.md, 05-runtime/*)
```

There is **no mandated wizard or fixed onboarding sequence** — the documentation supports the Teacher
using the existing creation capabilities to move the Environment from empty to usable. Any specific
guided-onboarding UX is out of scope and not required.

## Teacher → Student introduction (connecting to the existing Student lifecycle)

This is a **connection**, not a new invitation system. The existing Student identity/claiming model is
preserved exactly (`security-authz.md`, `03-domain/domain-model.md`):

```
Teacher operating their Environment
   → Teacher introduces / adds a student to the Environment
   → [existing model] teacher-created Student identity, possibly unclaimed
   → [existing model] Student later claims via phone-based verification
   → [existing model] authenticated Student access, one active environment at a time
```

- The Teacher's introduction of a student is the entry into the **already-documented** chain:
  teacher-created Student → unclaimed → claim → authenticated access. None of that is redesigned.
- **Unresolved (do not assume):** the exact **secure invitation/access mechanism** by which the
  Teacher provides the student their entry (e.g., how the claim is initiated and delivered) is **not
  decided**. The product intent is that it be secure and easy for both actors, consistent with the
  existing phone-based claiming model; the specific mechanism is deferred, not invented here.

## Relationship to the commercial lifecycle

The Teacher's account and environment lifecycle runs **in parallel** with the commercial/access
lifecycle (Free Trial → Subscription) documented in `01-product/access-lifecycle.md`. Account +
environment establishment happen as the Teacher enters via the Free Trial; continued access after the
trial depends on subscription. The two are cross-referenced but kept distinct.
