# System Overview

> **Authority:** Descriptive (system boundary & context) · **Source of truth** for actors,
> external dependencies, and the V1 system boundary.
> **Depends on:** the product decisions and the stabilized domain/architecture knowledge.

## What Madar is

Madar is a **multi-teacher SaaS platform** for the Egyptian private-tutoring context. It gives a
teacher one organized digital environment to run the administrative and educational operation
around their **offline, in-person** teaching.

Madar does **not** replace in-person teaching and is **not** an online-learning platform (LMS).
The teaching relationship stays offline; Madar is the digital layer for what happens **before,
during, and after** the session.

## The problem it solves

A private teacher manages a large volume of daily detail — registering students, organizing groups
and schedules, taking attendance, tracking who studied, following payments, keeping notes, and
communicating — using notebook, memory, WhatsApp, and scattered tools. That is slow, error-prone,
and never produces an organized, continuous picture of each student. Madar replaces that fragmented
process with one system.

**Irreducible core:** *managing students and their educational records.* Every other capability
(attendance, recitation, payments, content, notifications, evaluation, the student area, AI) exists
to serve that core.

## Who uses it (actors)

| Actor | Nature | Surface (V1) |
|-------|--------|--------------|
| **Teacher** | Primary customer; owns and operates an educational environment | Responsive web (Fast Session must excel on smartphones) |
| **Student** | Secondary user; consumes their area + selected active features | Mobile-first web |
| **Madar Content Maintainer** | Internal Madar operator; curates the central Knowledge Base | Internal web tool |

> **Provenance:** The Content Maintainer actor is *derived* from the V1 product decision that the
> AI Study Assistant runs on a **central, product-owned** Knowledge Base (teachers do not curate AI
> sources). It is not in the original brief; it exists because that decision requires someone to
> maintain the KB.

**Not actors in V1:** Parent (contact info is stored, but there is no Parent account, interface,
or access path), and any assistant/secretary/center-admin role (V1 targets a solo teacher operating
their own center).

## How users enter Madar (lifecycle)

Madar has a **product entry point** through which a prospective Teacher reaches the product and begins
the journey, typically via a **Free Trial**. From there the Teacher becomes an account holder,
establishes their educational environment, uses it during the trial, and can **subscribe** to continue
after the trial. This end-to-end lifecycle is documented in
[`../03-domain/actor-lifecycles.md`](../03-domain/actor-lifecycles.md) (Teacher account &
environment) and [`../01-product/access-lifecycle.md`](../01-product/access-lifecycle.md) (Free Trial
→ Subscription). Students enter differently — they are **teacher-created** and later **claim** their
identity — which is unchanged and documented in
[`../08-cross-cutting/security-authz.md`](../08-cross-cutting/security-authz.md).

## System boundary

**Inside Madar:**
- Core Madar system / domain (the eight modules, including Billing — see `04-architecture/`)
- The central curated **Knowledge Base** (product-owned)
- **AI product logic / orchestration** (behavior, boundaries, decision rules)

**Outside Madar (external dependencies):**
- **LLM / AI provider** — the underlying model; Madar owns orchestration, the model is external (outbound only)
- **Push-notification delivery** infrastructure (outbound only)
- **Video storage / streaming / delivery** infrastructure (outbound only)
- **Payment provider (Kashier)** — outbound checkout/status calls, **plus** the system's one approved
  inbound integration (see below)

**No inbound external integrations in V1, except one narrowly-scoped exception.** Only Teacher,
Student, and Content Maintainer act *on* Madar, and the three original providers remain outbound only.
The sole exception is Kashier's signature-verified payment-result webhook, approved by
[`10-decisions/ADR-016-inbound-webhook-exception.md`](../10-decisions/ADR-016-inbound-webhook-exception.md)
following the commercial-design pass — it is not a general reopening of this rule, and no other
inbound SMS, WhatsApp, email, or third-party integration exists.

See the diagram: [`diagrams/system/system-context.mmd`](../diagrams/system/system-context.mmd).

## V1 at a glance

- **Committed capabilities:** teacher environment (grades, groups, schedules), student registration
  & profiles, attendance + fast-attendance session, recitation/study tracking + fast session,
  payment tracking, video upload & targeting, notifications, student states + monthly rating, the
  student-facing area, and AI (study assistant + AI quiz).
- **Fenced (feasibility-dependent, outside the V1 Definition-of-Done):** homework upload/annotation.
- **Architecture:** a **Modular Monolith** running in two runtime roles (web + worker), with strong
  internal module boundaries, one unified REST API, centralized tenant isolation, and Madar-owned
  interfaces to the three external dependencies.

Full product scope is planned for `01-product/`; the architecture is in `04-architecture/`.

## Where to read next

1. [`glossary.md`](glossary.md) — the canonical vocabulary (read this before the domain model)
2. [`../03-domain/domain-model.md`](../03-domain/domain-model.md) — the world Madar represents
3. [`../04-architecture/architecture.md`](../04-architecture/architecture.md) — how it is structured
