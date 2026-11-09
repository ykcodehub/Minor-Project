"""Retrieve retained source chunks; ranking is not evidence or an accuracy score.

Callers must authorize the source scope first. An optional owner_id adds a second
tenant predicate for REST/MCP callers. PostgreSQL uses native full-text ranking;
development SQLite uses a bounded, disclosed lexical ranking over the same scope.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from sqlalchemy import func, literal_column, select

from app.models import Chunk, Source, now

STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "could",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "may",
        "me",
        "my",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "there",
        "these",
        "this",
        "to",
        "under",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "would",
        "you",
        "your",
    ]
)
# These widen retrieval only; all answers still require exact source verification.
TERM_GROUPS = (
    {"retain", "retained", "retention", "delete", "deletion", "erase", "erasure"},
    {
        "cancel",
        "cancellation",
        "terminate",
        "termination",
        "renew",
        "renewal",
        "रद्द",
        "समाप्त",
        "band",
        "khatam",
    },
    {
        "pay",
        "payment",
        "payments",
        "fee",
        "fees",
        "charge",
        "charges",
        "cost",
        "भुगतान",
        "पैसे",
        "paisa",
        "paise",
    },
    {"share", "sharing", "disclose", "disclosure", "transfer", "transfers", "साझा", "बेचना", "baant", "bech"},
    {"consent", "permission", "authorize", "authorization"},
)


def query_terms(question: str) -> set[str]:
    terms = {
        word
        for word in re.findall(r"[^\W_]+", question.lower(), re.UNICODE)
        if word not in STOP_WORDS and len(word) > 1
    }
    for group in TERM_GROUPS:
        if terms & group:
            terms.update(group)
    return terms


def rank_chunks(chunks: list[dict], question: str, limit: int = 8) -> list[dict]:
    """Portable bounded lexical fallback, preserving original chunk spans untouched."""
    if not 1 <= limit <= 20 or len(question) > 4000:
        raise ValueError("Invalid retrieval query or limit.")
    if len(chunks) > 1200:
        raise ValueError("Retrieval scope exceeds the configured chunk budget.")
    terms = query_terms(question)
    frequencies = [Counter(re.findall(r"[^\W_]+", chunk.get("text", "").lower())) for chunk in chunks]
    doc_frequency = {term: sum(bool(counts[term]) for counts in frequencies) for term in terms}
    scores = []
    for index, counts in enumerate(frequencies):
        length = max(sum(counts.values()), 1)
        score = sum(
            (1 + math.log(counts[term])) * math.log(1 + (len(chunks) + 1) / (doc_frequency[term] + 1))
            for term in terms
            if counts[term]
        ) / math.sqrt(length)
        scores.append((score, index))
    ranked = sorted(scores, key=lambda item: (-item[0], item[1]))[:limit]
    return [
        {
            **chunks[index],
            "retrieval": {
                "method": "portable_lexical",
                "rank": rank + 1,
                "score": round(score, 8),
                "matched_query": score > 0,
            },
        }
        for rank, (score, index) in enumerate(ranked)
    ]


def retrieve_chunks(
    db, source_ids: list[str], question: str, limit: int = 8, *, owner_id: str | None = None
) -> list[dict]:
    """Return only stored, unexpired chunks from the explicitly authorized scope."""
    if not source_ids or len(source_ids) > 10 or not 1 <= limit <= 20 or len(question) > 4000:
        raise ValueError("Invalid retrieval scope, query or limit.")
    scope = [Chunk.source_id.in_(list(dict.fromkeys(source_ids))), Source.expires_at > now()]
    if owner_id is not None:
        scope.append(Source.owner_id == owner_id)
    base = select(Chunk).join(Source, Source.id == Chunk.source_id).where(*scope)
    if db.bind.dialect.name == "postgresql" and query_terms(question):
        config = literal_column("'english'::regconfig")
        text = Chunk.data["text"].as_string()
        vector = func.to_tsvector(config, text)
        query = func.websearch_to_tsquery(config, " OR ".join(sorted(query_terms(question))))
        score = func.ts_rank_cd(vector, query)
        rows = db.execute(
            select(Chunk, score.label("score"))
            .join(Source, Source.id == Chunk.source_id)
            .where(*scope, vector.op("@@")(query))
            .order_by(score.desc(), Chunk.source_id, Chunk.ordinal)
            .limit(limit)
        ).all()
        if rows:
            return [
                {
                    **row.data,
                    "chunk_id": row.id,
                    "source_id": row.source_id,
                    "retrieval": {
                        "method": "postgresql_fts",
                        "rank": rank + 1,
                        "score": float(value),
                        "matched_query": True,
                    },
                }
                for rank, (row, value) in enumerate(rows)
            ]
    # No full-text match is not proof that the document lacks an answer. Select a
    # bounded lexical candidate set and let source-grounded generation abstain.
    rows = db.scalars(base.order_by(Chunk.source_id, Chunk.ordinal).limit(1201)).all()
    chunks = [{**row.data, "chunk_id": row.id, "source_id": row.source_id} for row in rows]
    return rank_chunks(chunks, question, limit)
