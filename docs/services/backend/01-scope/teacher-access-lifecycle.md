# Teacher Access & Lifecycle Boundary (Backend)

> **Authority:** **Normative** for the Backend responsibility boundary described here; every mechanism
> named as deferred stays **fenced**.
> **Specializes (new upstream):** `../../../03-domain/actor-lifecycles.md` (Teacher account &
> Teacher-Environment lifecycle), `../../../01-product/access-lifecycle.md` (Free Trial →
> Subscription), and the Teacher-authentication existence note in
> `../../../08-cross-cutting/security-authz.md`.
> **Why this file exists:** the System Documentation's lifecycle-correction pass made explicit an
> upstream chain the earlier Backend documentation did not represent — *product entry → Teacher
> account → Teacher authentication → Teacher Environment establishment → initial (empty→usable) use →
> Teacher introduces students → existing Student lifecycle*, plus a parallel *Free Trial →
> Subscription* access lifecycle. This document records the **Backend-level responsibilities** those
> additions necessarily create, and **fences** every mechanism the System Documentation leaves
> unresolved. It introduces **no** technology and **no** product/commercial decision.

This is a boundary/responsibility document, not a design. Where the System Documentation defers a
mechanism, the Backend defers it too — the responsibility is named; the mechanism is not invented.

## The lifecycle chain the Backend must support (traceability)

| System-level step (upstream) | Backend-level responsibility | Status |
|------------------------------|------------------------------|--------|
| Product entry point | None (acquisition channel/UI is out of scope; not a Backend concern) | Unaffected |
| Teacher becomes a **Madar account holder** | Represent the Teacher as an **authenticatable actor/account** (see TAL-1) | Newly required (responsibility only) |
| Teacher **authenticates** | Server-side Teacher **authentication responsibility** producing the authenticated actor context the capability docs already assume (see TAL-1) | Newly required; **mechanism deferred** |
| Teacher **Environment established** (empty) | Represent Environment **establishment/origin** and **initial empty state** as a Backend lifecycle point (see TAL-2) | Newly required (responsibility only); **cardinality resolved (ADR-013/INV-9); provisioning trigger mechanism still deferred** |
| Empty → usable (initial use) | No new capability — the existing creation capabilities populate the Environment (see TAL-3) | Contextually affected (framing only) |
| Teacher **introduces a Student** | Represent the **introduction/association** entry point into the **existing** Student claiming model (see TAL-4) | Newly required (connection only); **invitation mechanism deferred** |
| Existing Student lifecycle | **Unchanged** — teacher-created → unclaimed → phone-based claim → authenticated (see TAL-4) | Preserved |
| **Free Trial → Subscription** access state | Treat **access state** as an input to the authorization/access decision boundary (see TAL-5) | Newly required; **commercial parameters decided (commercial-model.md); Billing module owns enforcement (ADR-014/018); exact retry/grace/read-only mechanics still open** |

## TAL-1 — Teacher account & authentication responsibility

The earlier Backend documentation began at *"the authenticated actor… authorized environment."* The
System Documentation now makes explicit **how** a Teacher reaches that state. The Backend therefore
owns the responsibility, previously implicit, to:

- represent a **Teacher account** as a distinct, authenticatable actor (an account holder), and
- **authenticate** a Teacher account into the **authenticated actor context** that the composite
  authorization model and all capability documents already assume
  (`../08-cross-cutting/security-authz.md`; `../../../10-decisions/ADR-010-composite-authorization.md`).

This is a **separate path** from student entry and **does not alter the student model** (TAL-4).

> **Fenced — mechanism not decided.** The System Documentation does **not** select the Teacher
> authentication mechanism (credentials / OTP / tokens / provider). The Backend names the
> responsibility and the contract boundary (an authenticated Teacher actor context must be produced
> before capability requests are authorized) but **does not** select an authentication technology or
> protocol. This mirrors the already-deferred claiming mechanics
> (`../../../10-decisions/rejected-deferred.md`).

**Relationship to the composite model:** nothing in `ADR-010` changes. TAL-1 only supplies the
*origin* of the "authenticated actor" that the composite model consumes; it does not redefine the
model, roles, or environment authorization.

## TAL-2 — Teacher Environment establishment & initial state

The Environment keeps its exact inherited meaning — the tenant/isolation boundary keyed by
`teacher_environment_id` (`../06-data/data-model.md`, DAT-1;
`../../../10-decisions/ADR-004-two-layer-tenant-isolation.md`,
`../../../10-decisions/ADR-007-two-level-data-scoping.md`,
`../../../10-decisions/ADR-008-server-derived-tenant-context.md`). The System Documentation adds only
its **origin**: an Environment is **established as part of the Teacher's journey** and begins
**empty**. The Backend-level consequence:

- The Backend must recognize an Environment's **establishment/origin** and its **initial empty state**
  (no Academic Years, Grades, Groups, Enrollments, or records) as a real lifecycle point, rather than
  assuming an Environment always already exists and is populated.
- Isolation semantics are **unchanged** — establishment does not alter how `teacher_environment_id`,
  server-derived context, or two-layer enforcement work; it only explains **when/why** an Environment
  first exists.

> **Cardinality resolved — fenced only on provisioning trigger.** Per
> `../../../10-decisions/ADR-013-permanent-environment-cardinality.md` and INV-9
> (`../../../03-domain/invariants.md`), a Teacher Account owns **exactly one** Teacher Environment,
> permanently. The Backend documentation records this as settled. What remains **fenced** is only the
> provisioning **trigger/mechanics** (automatic on account creation vs. an explicit action vs.
> background job vs. service call) — not decided here. Note the inherited tenant model's "authorized
> environments" (plural) language (`ADR-008`) describes the general context-resolution mechanism and
> is unaffected; for the Teacher actor type specifically, the resolved set now has exactly one member.
> The API contract's "one *active* environment per student-facing context" rule
> (`../07-contracts/external-api-alignment.md`) is unchanged and, for Teachers, is now simply the only
> environment they have.
>
> **Implementation follow-up (not performed by this documentation pass):** DB-level enforcement
> (`OneToOneField` on `Environment.owner`), a check for pre-existing violating data in any live
> database (not performed), and reconciling `environments/tests.py`'s existing multi-environment
> fixture with the new invariant. See ADR-013 §Consequences.

## TAL-3 — Initial use (empty → usable) is existing capability, not a new workflow

Moving an Environment from empty to usable uses the **existing** creation capabilities (create
Academic Year / Grade(s) / Group(s) / Schedule(s), register students) already documented in scope
(`responsibilities.md`) and requirements. The Backend adds only the **framing** that these first runs
occur against a newly-established, empty Environment.

> **No mandated onboarding.** The System Documentation specifies **no** wizard or fixed onboarding
> sequence. The Backend introduces **no** mandatory onboarding workflow, ordering constraint, or
> guided-setup operation. This is framing only.

## TAL-4 — Teacher → Student introduction (connection to the existing model)

The System Documentation adds an explicit **connection**: a Teacher operating an Environment
**introduces/adds a Student**, which is the entry into the **already-documented** Student lifecycle.
The Backend-level consequence is only to recognize this **introduction/association** as the entry
point; it is **not** a new identity or account system.

The existing Student model is **preserved exactly** (`../08-cross-cutting/security-authz.md`;
`../06-data/data-model.md`): teacher-created global Student identity → possibly **unclaimed** →
**phone-based claim** → authenticated Student access; global Student identity vs. teacher-scoped
Enrollment distinction unchanged.

> **Fenced — invitation mechanism not decided.** The **secure invitation/access mechanism** by which
> the Teacher provides the Student their entry (how the claim is initiated/delivered) is **not decided**
> at the System level. The Backend may recognize the responsibility/boundary but **does not invent**
> the mechanism; it remains consistent with the existing phone-based claiming model and deferred
> (`../../../10-decisions/rejected-deferred.md`). **The existing claiming architecture is not altered
> to satisfy this connection.**

## TAL-5 — Access state (Free Trial / Subscription) as an access-decision input

The System Documentation establishes a parallel **access lifecycle** — *Free Trial → trial ends →
Subscription / continued access* — where **whether a Teacher currently has access** to their
Environment and its capabilities is governed by their **access state**. The Backend-level
consequence, and its strict boundary:

- The Backend may need to represent an **abstract access state / access-decision input** — an
  additional input to the authorization/access boundary answering *"does this Teacher currently have
  access?"* — **alongside** (not replacing) the composite authorization model. Composite authorization
  continues to govern **what** an authenticated, authorized Teacher may do; access state governs
  **whether access is currently granted at all**.
- This is an **abstract boundary only**. It is deliberately **not** a billing architecture.

> **Commercial mechanics now decided at the System level; Backend ownership boundary now concrete.**
> Pricing, plans/tiers, trial duration, billing cycle, and the failed-payment policy **direction** are
> decided (`../../../01-product/commercial-model.md`). A dedicated **Billing** Backend module now owns
> this responsibility (`../../../10-decisions/ADR-014-billing-bounded-module.md`), via a Madar-owned
> payment-provider interface (`ADR-015`) and a narrow, ADR-approved inbound-webhook exception
> (`ADR-016`). What remains **fenced/open**: exact retry count/grace-period duration, exact
> student-facing restricted-access behavior, the complete teacher read-only ruleset, refunds,
> proration, and upgrade/downgrade timing (`../../../01-product/commercial-model.md` §Open items). Any
> data-retention consequence of an access-not-granted state is unchanged
> (`../../../06-data/lifecycle-retention.md`: indefinite retention, no deletion workflow in V1).

### Do not conflate with student fee tracking

The Teacher's **subscription/access to Madar** (this document) is a distinct concept from
**student fee tracking inside the environment** (the teacher recording a student's monthly Grade-fee
status — `responsibilities.md` §Payments, `../06-data/data-model.md`, INV-5). Neither changes the
other; they must not be merged.

## Summary — new responsibilities vs. fenced mechanisms

**Newly named Backend responsibilities (boundary only):** Teacher account/actor representation and
authentication (TAL-1); Environment establishment/origin + initial empty state (TAL-2); Teacher→Student
introduction as the entry to the existing claiming model (TAL-4); an abstract access-state input to the
access-decision boundary (TAL-5).

**Fenced / unresolved (not invented here):** Teacher authentication mechanism; Environment provisioning
**trigger** (cardinality itself is resolved — ADR-013/INV-9); secure Teacher→Student invitation
mechanism; the exact numeric/behavioral sub-decisions of commercial mechanics (retry count, grace
duration, refunds, proration — see `../../../01-product/commercial-model.md` §Open items);
access-not-granted exact behavior (student-facing restrictions, teacher read-only ruleset) and its
retention consequence.

**Preserved unchanged:** the entire Student identity/claiming architecture; the composite authorization
model; tenant isolation and `teacher_environment_id` semantics; all inherited ADRs; student fee
tracking.
