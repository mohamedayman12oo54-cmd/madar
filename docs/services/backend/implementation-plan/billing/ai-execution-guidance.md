# AI Execution Guidance — BILL-PLAN-01

> Directives for a future Claude Code (or other AI agent) session that **implements** this plan. Layer 6
> authority: below System Docs, Backend Docs, ADRs, this plan and Engineering Skills. Complements, doesn't
> replace, `../ai-execution.md`.
> **Provenance note:** the authoring brief referred to "18 numbered constraints from Section 9.9". That
> section's text wasn't supplied verbatim to the author, so the 18 directives below are **adapted** from the
> brief's stated constraints and the binding documents. If the original wording surfaces, reconcile it and
> record a deviation.

## Directives

1. **Obey the authority order.** System Docs → Backend Service Docs → ADR-001..018 → this plan → Engineering
   Skills → this guidance → your inference. On conflict the higher layer wins, and you record a deviation
   (`../changes.md` protocol). Never rewrite a higher layer to match code.
2. **One Work Unit at a time, in dependency order.** Start a unit only when its "Dependencies required before
   execution" are VERIFIED (`dependency-graph.md`). Don't merge units into one PR unless the unit files' commit
   boundaries allow it.
3. **Never start a BLOCKED unit.** BILL-WU-004, 007, 013, 015, 016, 026, 027, 030, 033, 036 and 037 stay
   untouched until their named gate (BILL-DEC-* / BILL-EXT-* / BILL-OPS-* / data condition) has a recorded
   resolution you can link. Don't build "a reasonable default" in advance.
4. **Never invent commercial numbers.** Retry count, retry schedule, grace duration, repeat-trial rules,
   proration, refund policy, price-change handling, invoice/tax rules and AI quotas are open. The only decided
   numbers (16 days, 30 elapsed days, caps 250/400/800/none, EGP 1,000/1,500/2,000) must be copied from
   `docs/01-product/commercial-model.md` at execution time, not from memory or from this plan.
5. **Keep the Kashier 30-day question external.** Don't enable live renewals, and don't choose
   `paymentFrequency`/`minimumDaysBetweenPayments` live values, until BILL-EXT-01 has a written Kashier answer
   (BILL-WU-026). Never switch to calendar-month billing to "make it fit". Escalate instead.
6. **Fix the phantom app first.** BILL-WU-001 precedes everything. Confirm BILL-DEC-08 (has someone else got
   a `billing` implementation?) before opening a PR.
7. **Never perform destructive data cleanup.** Duplicate-owner remediation (BILL-WU-004) runs only under an
   approved BILL-DEC-01 policy, after a verified backup, as a dry-run first. Never apply the cardinality
   migration to a shared DB without a same-window zero-duplicate report (BILL-WU-007).
8. **Entitlement never goes into authentication.** Don't modify `apps/backend/accounts/authentication.py`
   (`MadarJWTAuthentication.get_user`). Entitlement checks run as permissions listed **after**
   `IsEnvironmentMember` (ADR-018), and on the Worker before provider calls (OP-PARITY).
9. **Only one inbound integration.** The Kashier webhook is the sole new unauthenticated route. Don't add
   other inbound routes, and don't revive `content/providers.py` `verify_webhook` or subclass `VideoProvider`
   (ADR-015/016). Signature verification on the raw body precedes any use of the payload.
10. **A redirect is never proof of payment.** Only a verified webhook event, or reconciliation via Kashier's
    status lookup, may change Subscription, PaymentAttempt or entitlement state.
11. **Payment-event dedup is its own mechanism.** Don't use or extend `ai/models.py` `idempotency_key` or its
    constraint for billing (ADR-017). Use the provider-event record's unique dedup key plus terminal-state
    checks under row locks.
12. **Use the right worker template.** Model billing commands on
    `ai/management/commands/process_ai_operations.py` (atomic conditional-UPDATE claim, provider call outside
    transactions). Never copy `notifications/management/commands/process_notifications.py`. **Never requeue a
    stale renewal charge to pending.** Stale charges go to `unknown`, then reconciliation. Don't build an
    Outbox or broker (BILL-RISK-24).
13. **Respect module boundaries.** `billing` owns its persistence. Other modules call Billing capabilities
    (`entitlements.decide`, `services.start_trial`); Billing obtains Environment/Enrollment facts via the owning
    module's capability (BND-1/BND-4). Never touch `financials`, and never import `config/months.py` in billing.
14. **Secrets and card data.** No secret values in code, tests, fixtures, logs, docs or commits. Only names go
    in `.env.example`. Store only opaque token/agreement references, never PAN or CVV. Redact cardholder name
    and masked card in logs (BILL-WU-035).
15. **No outbound call inside a DB transaction.** Claim/persist in short transactions; call Kashier outside
    them; timeouts on every call; a transport timeout means `unknown`, never `failed`.
16. **Implemented ≠ Verified.** A unit is VERIFIED only with the evidence in `verification-plan.md` §9: a
    full PostgreSQL suite run attached (no CI exists), AC links, sandbox records for provider-dependent ACs,
    and reviewer sign-off. READY WITH A TRACKED OPEN ITEM units must leave their open item visibly unresolved
    (a TODO/flag citing the ID).
17. **Commit discipline.** Follow the repo's observed Conventional-Commit style (`feat(scope):`,
    `test(scope):`, `fix(scope):`, `docs(scope):`, `build(scope):`, e.g. `feat(billing): …`,
    `test(environments): …`) and the per-unit commit boundaries. Commit only when the user asks. Never commit
    the root audit files. Never skip hooks.
18. **Stop and escalate** when: a decision would change a system boundary, invariant, external/client
    contract, tenant model or ADR; Kashier behaviour contradicts the docs or ADR-016 assumptions; a test you
    need to change would remove coverage of an invariant; you'd need a new notification channel or type;
    anything requires refunds, proration, plan change or invoices; documentation is ambiguous in a way that
    changes money or access outcomes.

## Dangerous assumptions (do not make)

- That the `settings.py:167-169` comment describes an approved design. It doesn't; DAT-5 and ADR-017 do.
- That dev DBs are INV-9-clean (`seed_demo.py` creates duplicates).
- That Kashier's public docs settle the signature key, token fields or 30-day cadence (BILL-EXT-01/03).
- That a notification channel exists for teachers (it doesn't; BILL-DEC-06).
- That the general Study Assistant is plan-gated (BILL-DEC-07).
- That the Backend-wide plan's Outbox/FND-08 mechanisms exist in code (they don't).
