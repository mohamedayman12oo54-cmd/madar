"""
Retrieval over the central Knowledge Base — the **bounded source contract**
the Study Assistant is documented to run on (`01-product/scope.md`:
"Study Assistant <- central curated Knowledge Base").

Scope note (docs: `09-operations/knowledge-base.md`): the specific RAG /
embedding / vector-store strategy is explicitly DEFERRED to implementation.
This module therefore implements the smallest honest thing that satisfies the
documented contract: lexical selection over PUBLISHED documents only. It is
real retrieval over real curated rows — not a stand-in for one — and the
richer strategy can replace `select_sources()` alone without touching the
model, the worker, the API, or the UI.

Hard rules enforced here:
  * only PUBLISHED documents are ever returned (drafts are not authoritative);
  * the caller receives the exact documents used, so an answer can state its
    sources instead of implying knowledge it does not have;
  * nothing about any student is read, passed or matched — the Assistant is a
    general tutor and must stay that way.
"""
import re

from .models import KBDocument

MAX_SOURCES = 3
MAX_SOURCE_CHARS = 1200
_STOP = {
    "من", "في", "على", "عن", "الى", "إلى", "ما", "هو", "هي", "هل", "كيف", "لماذا",
    "the", "a", "an", "is", "are", "what", "how", "why", "of", "to", "in", "and",
}


def _tokens(text: str) -> set[str]:
    # `[^\W_]` is Unicode letters/digits only. A naive \u0600-\u06FF range
    # would swallow Arabic punctuation (`؟` is U+061F), gluing it onto the
    # last word so "الخلية؟" never matched "الخلية".
    words = re.findall(r"[^\W_]+", (text or "").lower(), re.UNICODE)
    return {w for w in words if len(w) > 2 and w not in _STOP}


def select_sources(prompt: str, limit: int = MAX_SOURCES) -> list[KBDocument]:
    """The PUBLISHED KB documents most relevant to `prompt`, best first.

    Returns [] when the KB has nothing relevant — callers must treat that as
    "no grounding available" and must not answer from thin air.
    """
    terms = _tokens(prompt)
    if not terms:
        return []
    scored = []
    for doc in KBDocument.published.all()[:500]:
        haystack = _tokens(f"{doc.title} {doc.topic} {doc.body}")
        overlap = terms & haystack
        if not overlap:
            continue
        # Title/topic matches are worth more than a passing mention in the body.
        head = _tokens(f"{doc.title} {doc.topic}")
        scored.append((len(overlap) + 2 * len(terms & head), doc.updated_at, doc))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [doc for _, _, doc in scored[:limit]]


def as_context(docs) -> str:
    """The bounded text actually handed to the provider. Truncated per
    document so one long article cannot crowd out the rest."""
    return "\n\n".join(
        f"[{d.title}]\n{d.body[:MAX_SOURCE_CHARS]}" for d in docs
    )


def as_citations(docs) -> list[dict]:
    """What gets persisted on the operation and shown in the UI, so the
    student can see exactly which curated material the answer came from."""
    return [{"id": d.id, "title": d.title, "topic": d.topic, "version": d.version} for d in docs]
