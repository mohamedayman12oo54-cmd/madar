# Traceability Matrix — Source → Obligation → WU → AC-seed → Verification

> **Authority:** Layer 4 (derived). Bidirectional: every implementation-relevant obligation has a WU;
> every WU has documented justification. `(Sys)` = System-level source; `(BE)` = Backend-level source.

## Forward chain (Obligation → WU → source)

| Obligation | WU(s) | Authoritative source | Level |
|---|---|---|---|
| OBL-FND-01 | FND-01 | ADR-001/012; execution-model | Sys+BE |
| OBL-FND-02 | FND-05 | ADR-008·api-contract; EX-1·security-authz | Sys+BE |
| OBL-FND-03 | FND-03, FND-04 | ADR-004/007·INV-7; DAT-1·BND-2 | Sys+BE |
| OBL-FND-04 | FND-06 | ADR-010; BND-2 | Sys+BE |
| OBL-FND-05/06 | FND-07 | invariants·api-contract; BR-1·AL-1 | Sys+BE |
| OBL-FND-07 | FND-02 | consistency·data-model | Sys+BE |
| OBL-FND-08/09 | FND-08, FND-09 | ADR-012; EX-1/2 | Sys+BE |
| OBL-RUN-03 | FND-10 | ADR-005·consistency; BND-3 | Sys+BE |
| OBL-FND-10 | FND-12 | observability; BR-3 | Sys+BE |
| OBL-FND-11 | FND-11 | configuration-secrets | BE |
| OBL-IE-01 | IE-01 | domain-model·INV-1 | Sys |
| OBL-IE-02/03 | IE-02, IE-03 | domain-model·INV-1..6; ADR-007 | Sys |
| OBL-IE-04 | IE-04 | building-blocks; BND-1·internal-contracts | Sys+BE |
| OBL-IE-05 | IE-05 | lifecycles·retention·INV-6 | Sys |
| OBL-EO-01 | EO-02 | lifecycles | Sys |
| OBL-EO-02/03 | EO-03 | functional·INV-8 | Sys |
| OBL-EO-04 | EO-04 | ADR-005·consistency; BND-3 | Sys+BE |
| OBL-EO-05 | EO-01, EO-05 | lifecycles·functional | Sys |
| OBL-FIN-01 | FIN-01 | functional·scope | Sys |
| OBL-FIN-02 | FIN-02 | INV-5; BND-1 | Sys+BE |
| OBL-SE-01 | SE-01 | functional·state-pipeline | Sys |
| OBL-SE-02 | SE-02 | functional | Sys |
| OBL-SE-03 | SE-03 | functional·security-authz | Sys |
| OBL-SE-04 | SE-04 | state-pipeline·ADR-006 | Sys |
| OBL-CON-01 | CON-01 | functional·data-model·external-interfaces | Sys |
| OBL-CON-02 | CON-02 | scope·KB-ops | Sys+BE |
| OBL-CON-03 | CON-03 | KB-seam·KB-ops·BR-3 | BE |
| OBL-AI-01 | AI-01 | ADR-002·external-interfaces; AI-contract | Sys+BE |
| OBL-AI-02 | AI-02 | ai-quiz·functional·ADR-006/011 | Sys |
| OBL-AI-03 | AI-03 | state-pipeline·ADR-006 | Sys |
| OBL-AI-04 | SE-04, AI-02, AI-03 (behavior) | ADR-006·consistency·data-model; DAT-3 | Sys+BE |
| OBL-NOT-01 | NOT-02 | functional·PD-4 | Sys |
| OBL-NOT-02/03/04 | NOT-01 | ADR-005; BND-3 | Sys+BE |
| OBL-RUN-01 | RUN-01 | BR-2·fast-session; ADR-005·quality | Sys+BE |
| OBL-RUN-02 | RUN-02 | ADR-006/011·api-contract; async-operations | Sys+BE |
| OBL-API-01/02 | API-01 | ADR-003·api-contract; external-api-alignment | Sys+BE |
| OBL-AUTH-02 | AUTH-01 | security-authz·glossary | Sys |
| OBL-EXT-01 | EXT-01 | external-interfaces·ADR-009/002/006 | Sys |
| OBL-EXT-02 | EXT-02 | external-interfaces·ADR-009/005 | Sys |
| OBL-EXT-03 | EXT-03 | external-interfaces·ADR-009 | Sys |
| OBL-OPS-01 | OPS-01 | deployment·ADR-001/012; OP-PARITY | Sys+BE |
| OBL-OPS-02 | OPS-02 | backup-recovery | Sys+BE |
| OBL-TAL-01/02 | TAL-01 | TAL-1·actor-lifecycles·security-authz; BD-21 | Sys+BE |
| OBL-TAL-03 | TAL-02 | TAL-2·DAT-4·actor-lifecycles; BD-22 | Sys+BE |
| OBL-TAL-04 | TAL-03 | TAL-4·actor-lifecycles; BD-23 | Sys+BE |
| OBL-TAL-05 | TAL-04 | TAL-5·AL-2·DAT-4·access-lifecycle; BD-24 | Sys+BE |

## Deferred/fenced obligations (represented as Nodes — not orphans)

| Obligation | Representation |
|---|---|
| OBL-AI-05 (Study Assistant interaction model) | NODE (DEFERRED/OPEN, fenced) — capability retained in V1 baseline; no WU for an undefined interaction contract |
| OBL-AI-04 (AI persistence **ownership**) | behavior in SE-04/AI-02/AI-03; **ownership** → NODE-AIOwnership (fenced) |
| OBL-API-03 (wire-level taxonomy) | semantics in FND-07/API-01; serialized → NODE-WireAPI (downstream-doc) |
| OBL-AUTH-02 (claiming mechanism) | flow in AUTH-01; OTP mechanism → NODE-OTP (fenced) |
| OBL-TAL-* mechanisms | boundaries in TAL-01..04; mechanisms → NODE-TeacherAuth/EnvProvision/Invitation/AccessBehavior (fenced) |

## Reverse coverage & orphan detection

- **Obligation → WU:** every implementation-relevant obligation has ≥1 WU. ✅
- **WU → justification:** all 49 WUs trace to a documented source at their level. **Zero orphan WU.** ✅
- **Verification:** every AC-seed has a WU target; **zero verification orphan.** ✅
- **Negative space** (Homework, caching, audit, rate-limit, tracing, inbound, online-payment, SMS, cross-env
  merge, "new quiz") produced **no** WU — correct, not a gap. ✅
- **ISSUE-08-01:** RESOLVED at the documentation-gap level; upstream chain now complete via WS-TAL.

## Coverage metrics

- Implementation-relevant obligation coverage: **100%**.
- WU justification: **49/49** have source + reason.
- Verification-path presence: **49/49** meaningful WUs.
- Traceability integrity: no orphan (WU/verification), no contradiction, negative space closed.
