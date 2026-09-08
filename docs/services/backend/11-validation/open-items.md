# Validation — Open / Deferred Items (Backend)

> **Authority:** Informative (documentation control). This is the consolidated register of items the
> Backend documentation **deliberately leaves open** — each with an owner/target and the reason it is
> **non-blocking**.
> **Depends on:** `../../../10-decisions/rejected-deferred.md`.

## The governing principle

> Validation does not require every implementation or design detail to be resolved. It requires
> unresolved items to be correctly classified, explicitly owned/routed, consistent with established
> boundaries, and non-blocking for the documentation purpose at hand.

Documentation must **not** resolve any of these implicitly. In particular: no technology/stack choice,
no concrete mechanism, no schema/endpoint catalog, and no ownership inference where ownership is open.

## Open items

| Item | Status | Owner / target | Why non-blocking |
|------|--------|----------------|------------------|
| Backend technology stack (language, framework, database, ORM, hosting, queue) | Open | Architecture / Data / Operations / implementation | Design-first: behavior/boundaries specified independent of stack; the *absence* is itself documentable. |
| Execution-context serialization / transport / storage / reconstruction mechanism | Open | Implementation / runtime | Behavioral rule (EX-1) holds regardless of mechanism. |
| Transactional event hand-off mechanism (Outbox / queue / broker / polling / CDC — none named) | Open | Implementation / runtime | Pattern (BD-10) is asserted; mechanism does not change the guarantee. |
| Concrete async mechanism (job/queue technology) | Open | Implementation / runtime | Common async principles (EX-2) hold regardless. |
| Concrete KB store technology | Open | Architecture / Data | Application-level KB lifecycle owned by the Backend; store tech does not affect the seam. |
| **AI product-state persistence ownership** | **Open** | **AI Module / Domain refinement** | Persistence facts are stated (DAT-3); ownership must not be back-inferred and is not needed to document the Backend. |
| **Study Assistant interaction model** | **Open / Deferred** | System / product / AI design | Recorded as deferred (async-operations.md); fabricating a model would violate the methodology. |
| Wire-level error taxonomy (HTTP codes, error codes/categories, payload schemas, endpoint catalog) | Deferred | API-documentation stage | Semantic failure mapping (AL-1) is asserted; wire detail is a later stage per the inherited contract. |
| OTP / identity-verification provider mechanics | Deferred | Implementation / Operations | Claiming flow is documented; the mechanism's form (incl. whether it is an external provider) is undecided. |
| Concrete secret storage / injection / config-delivery / rotation | Deferred | Operations | Principle-level rule (BD-19) is asserted; the *how* is an Operations concern. |
| Concrete cloud/hosting selection; backup verification procedure | Deferred | Operations | Inherited managed-service posture applies; vendor/procedure not required at this stage. |
| Numeric RPO/RTO; numeric Backend latency SLA | Deferred (conditional) | Operations / Architecture | Only established if a real business requirement/evidence emerges; false precision otherwise. |
| Retention / deletion / privacy / legal operational policy | Deferred | Operations follow-up | Explicit V1 scope decision (retain indefinitely, no deletion workflow); policy not yet binding. |
| Targeted abuse/cost protection on AI operations | Conditional | Introduced only if a concrete need emerges | "Permitted if needed" is not a commitment that the mechanism exists now. |
| Teacher authentication mechanism (credentials / OTP / tokens / provider) | Deferred | Implementation (upstream: System-deferred) | Responsibility named (TAL-1); mechanism not selected upstream, so not invented here. |
| Environment provisioning trigger & per-Teacher cardinality (one vs. many) | **Open** | System (unresolved) / Implementation | Establishment recognized (TAL-2); trigger/cardinality deliberately unresolved upstream. |
| Secure Teacher→Student invitation/access mechanism | Deferred | System (unresolved) / Implementation | Connection recognized (TAL-4); mechanism unresolved upstream; existing claiming model unchanged. |
| Commercial mechanics (pricing, plans, billing provider/gateway, invoicing, trial duration, renewal, cancellation, proration, payment processing) | Deferred | Commercial-design pass | Access-state input is abstract (TAL-5); billing architecture is out of scope and unresolved upstream. |
| Access-not-granted behavior (suspension / grace / read-only) + any retention consequence | **Open** | System (unresolved) / Operations | Access state recognized (TAL-5); exact behavior unresolved upstream; retention rule unchanged. |

## Escalation reminder

Any future resolution of an open item that would **redefine** a system boundary, an established
invariant, an external/client-facing contract, the tenant/isolation model, an external integration
contract, or an inherited ADR must be **escalated to the System Documentation level** — not resolved
inside the Backend documentation.
