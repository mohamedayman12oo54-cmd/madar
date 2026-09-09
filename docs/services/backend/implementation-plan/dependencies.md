# Dependency Model — Semantic Typed Graph

> **Authority:** Layer 4 (derived). Edges are **engineering relationships**, not shared-source coincidences.
> **Types:** BLOCK (needs full impl) · CONTRACT (needs stable seam/interface) · DATA · ENV · DECISION · EXTERNAL · VERIF.
> **Direction:** `prerequisite → dependent`. **Blocking graph is acyclic.**

## Shared preconditions (declared once — not N×N edges)

- **Platform Floor:** FND-01 (skeleton, ENV) · FND-02 (persistence, DATA) — precondition for every implementing/persisting WU.
- **Enforcement Substrate:** FND-04 (isolation) · FND-05 (context) · FND-06 (authz) · FND-07 (invariant/error) — BLOCK-for-completion precondition for every teacher-scoped WU (IE/EO/FIN/SE/CON/RUN-01/API). Consumed as a substrate precondition; specific edges below appear only where a dependency is *particular* (e.g., CON-02 → FND-06).

## Foundation-internal edges

| prereq → dependent | type | reason |
|---|---|---|
| FND-01 → FND-02 | ENV | persistence over the Django project |
| FND-03 → FND-04 | BLOCK | FND-04 implements the spike-validated isolation mechanism |
| FND-02 → FND-04 | BLOCK | data-access over persistence foundation |
| FND-05 → FND-04 | CONTRACT | FND-04 enforces the context FND-05 establishes |
| FND-05 → FND-06 | CONTRACT | composite authz needs actor+role+env context |
| FND-02 → FND-07 | DATA | atomic rejection needs the transaction foundation |
| FND-08 → FND-09 | BLOCK | FND-09 implements the validated job/queue |
| FND-08 → FND-10 | BLOCK | FND-10 implements the validated Outbox |
| FND-02 → FND-09 | DATA | DB-backed jobs in the same relational DB |
| FND-02 → FND-10 | DATA | Outbox + atomic txn in the same DB |
| FND-09 → FND-11(async obs of FND-12) | VERIF (soft) | async-path observability needs the async paths present |

## Lifecycle-seam edges (Stage-8 repair, additive)

| prereq → dependent | type | reason |
|---|---|---|
| NODE-TeacherAuth → TAL-01 | DECISION | fences the auth mechanism only |
| NODE-EnvProvision → TAL-02 | DECISION | fences trigger + cardinality only |
| NODE-Invitation → TAL-03 | DECISION | fences invitation mechanism only |
| NODE-AccessBehavior → TAL-04 | DECISION | fences access-not-granted + commercial mechanics |
| TAL-01 → FND-05 | CONTRACT | produces the authenticated-Teacher actor context FND-05 consumes (resolves ISSUE-08-01) |
| TAL-02 → FND-05 | CONTRACT | established environment to resolve context against |
| TAL-02 → IE-02 | DATA | structural entities created within an established (empty) environment |
| IE-01 → TAL-03 | CONTRACT | introduction uses the existing student-identity model |
| TAL-04 → API-01 | CONTRACT | access-state consulted as prior input at the access-decision boundary |

## Identity / capability edges

| prereq → dependent | type | reason |
|---|---|---|
| IE-01 → IE-03 | BLOCK/DATA | Enrollment references exactly one Student (INV-1) |
| IE-02 → IE-03 | DATA | Enrollment carries Grade + memberships within the Grade |
| IE-03 → IE-04 | BLOCK | capability resolves Enrollment/Grade context |
| IE-03 → IE-05 | DATA | lifecycle operates on Enrollment |
| IE-04 → EO-03 / FIN-01 / FIN-02 / SE-01 / SE-02 / CON-01 / AI-03 | CONTRACT | resolve enrollment/grade context via capability (BND-1) |
| IE-01 → AUTH-01 | BLOCK/DATA | claiming to an existing Student identity |
| FND-05 → AUTH-01 | CONTRACT | auth/context |

## Educational + Fast-Session edges

| prereq → dependent | type | reason |
|---|---|---|
| IE-02 → EO-01 / EO-05 | DATA | Schedule for a Group |
| IE-02 → EO-02 | DATA | Session Instance belongs to a Group |
| EO-01 → EO-02 | CONTRACT (non-blocking) | scheduled origination optional (ad-hoc allowed) |
| EO-02 → EO-03 | BLOCK/DATA | records attach to a Session Instance (INV-8) |
| EO-03 → EO-04 | BLOCK | emitted on Absent/Not-Studied outcomes |
| FND-10 → EO-04 | BLOCK (consumption) | uses the Outbox hand-off |
| EO-02 / EO-03 / EO-04 → RUN-01 | BLOCK | RUN-01 composes the capture path |

## Async spine · AI · Notifications edges

| prereq → dependent | type | reason |
|---|---|---|
| EXT-01 → AI-01 | CONTRACT/BLOCK | L&AI crosses the Madar-owned LLM seam |
| FND-09 → RUN-02 | BLOCK | spine runs on the async substrate |
| AI-01 → RUN-02 | CONTRACT | invokes L&AI capability |
| FND-05 → RUN-02 | CONTRACT | trusted operation context |
| RUN-02 → AI-02 / AI-03 | BLOCK | both use the spine |
| AI-01 → AI-02 / AI-03 | CONTRACT | invoke L&AI |
| CON-01 → AI-02 | DATA/CONTRACT | quiz source = teacher content |
| EO-03 → AI-03 | DATA | evidence (attendance/recitation) |
| AI-02 → AI-03 | DATA (non-blocking) | quiz performance = optional evidence |
| AI-03 → SE-04 | CONTRACT | SE consumes the advisory via capability boundary |
| SE-01 → SE-04 | DATA | merged into the State record for finalization |
| FND-09 → NOT-01 | BLOCK | consumption on the substrate |
| FND-10 → NOT-01 | BLOCK (consumption) | consumes Outbox hand-offs |
| EXT-02 → NOT-01 | CONTRACT | Push interface |
| FND-10 → NOT-02 | CONTRACT | emits via hand-off |
| CON-01 / SE-02 / IE-02 → NOT-02 | DATA | event sources: new-video, rating-published, group/grade broadcast |

## Content · API · Ops edges

| prereq → dependent | type | reason |
|---|---|---|
| EXT-03 → CON-01 | CONTRACT | Video interface |
| FND-06 → CON-02 | BLOCK | Content-Maintainer authz isolated from educational records |
| CON-02 → CON-03 | BLOCK | publish operates on authored KB |
| FND-09 → CON-03 | CONTRACT/BLOCK | publish/index as background job |
| FND-05 / FND-06 / FND-07 → API-01 | CONTRACT | server-derived tenant · composite authz · error semantics |
| RUN-02 → API-01 | CONTRACT | submit-poll async operations |
| FND-01 / FND-12 → OPS-01 | BLOCK/CONTRACT | deployable + observability |
| FND-02 / OPS-01 → OPS-02 | DATA/ENV | datastore + environments |

## Fenced-Node → WU edges (decision/external/downstream)

| node → dependent | type | scope |
|---|---|---|
| NODE-OTP → AUTH-01 | DECISION | fences OTP/verification provider only |
| NODE-Vendors → EXT-01/02/03, OPS-01/02, FND-12, FND-11 | EXTERNAL | vendor/host/secret-store adapters only; seams buildable |
| NODE-WireAPI → API-01, FND-07 | DOWNSTREAM | serialized taxonomy/schemas only; semantics unblocked |
| NODE-AIOwnership → SE-04, AI-02, AI-03, CON-03 | DECISION (fenced sub-boundary) | fences persistence *ownership* only; behavior/ordering unblocked |

## Verification-ordering edges (not execution prerequisites)

`FND-03 → verify(FND-04)` · `FND-08 → verify(FND-09/10)` · `EO-02/03/04 + FND-10 → verify(RUN-01)` · `AI-01 + FND-09 → verify(RUN-02)` · `TAL-seams → verify(FND-05/API-01)`.

## Integrity

- **Acyclic blocking graph:** floor → substrate → identity → modules → async → experience → contract; no back-edge; DECISION nodes have in-degree 0 from WUs. **PASS.**
- **No artificial ordering:** floor/substrate declared once; EO-01→EO-02 and AI-02→AI-03 non-blocking; module→IE via CONTRACT (capability) not BLOCK; no edge from shared source alone.
- **State semantics:** a DECISION node does not turn its WU or consumers BLOCKED while the seam is definable (SEAM-READY).
