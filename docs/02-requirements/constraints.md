# Constraints

> **Authority:** Descriptive (the constraints that shaped V1).
> **Depends on:** the architectural drivers.

## Team

Three senior engineers — Software Architect & Backend, Full-Stack, AI Engineer — possibly +1 AI if the
AI workload grows. Small, senior team; the architecture must stay operationally manageable and avoid
premature distribution.

## Clients

- **Teacher:** responsive, mobile-friendly web (Fast Session must excel on smartphones).
- **Student:** mobile-first web.
- **Content Maintainer:** internal web tool.

V1 minimizes the number of independently developed client applications. A cross-platform mobile app is
a possible V2 direction, not a V1 requirement.

## Operating context

Egypt-first, private-tutoring / teacher-owned-center context. Target students are expected to have
sufficient smartphone + internet access to actively use the Student Area.

Approximate environment scale (per teacher — **not** system traffic):

| Teacher type | Students | Groups | Grades |
|--------------|---------|--------|--------|
| Typical | ~150 | ~3 | ~3 |
| Busy | ~300 | ~8 | ~6 |
| Very large | ~500 | ~10 | ~6 |

Madar must comfortably support a teacher managing hundreds of students across multiple groups/grades
without the workflow feeling operationally heavy.

## Hosting & operations

Cloud-hosted, managed services wherever practical; avoid self-run infrastructure unless a concrete
requirement later justifies it. No specific cloud/vendor selected at this stage. No Egypt-only data
residency requirement is established — and none is to be invented.

## Data sensitivity

Madar handles student educational data, potentially including minors' data → security and privacy are
important quality concerns. No specific regulatory regime is currently a hard V1 constraint; one must
not be invented (see `08-cross-cutting/security-authz.md` and `09-operations/`).
