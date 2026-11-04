"""Rank change request sections against a policy rule."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Protocol

from reqtrace.documents import Rule, Section

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def build_query(rule: Rule) -> str:
    """Build a query from the rule's wording, without its ID as a retrieval hint."""
    return f"{rule.title}. {rule.text}"


class Retriever(Protocol):
    def rank(self, query: str, sections: Sequence[Section]) -> list[Section]:
        """Return all sections, most relevant first."""
        ...


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _section_text(section: Section) -> str:
    return f"{section.title}\n{section.text}"


class Bm25Retriever:
    """A lexical baseline with no model dependency."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

    def rank(self, query: str, sections: Sequence[Section]) -> list[Section]:
        documents = [_tokens(_section_text(section)) for section in sections]
        average_length = sum(map(len, documents)) / max(len(documents), 1)
        document_frequency = Counter(term for document in documents for term in set(document))

        def score(document: list[str]) -> float:
            counts = Counter(document)
            total = 0.0
            for term in _tokens(query):
                frequency = counts[term]
                if not frequency:
                    continue
                n = document_frequency[term]
                idf = math.log(1 + (len(documents) - n + 0.5) / (n + 0.5))
                scale = 1 - self.b + self.b * len(document) / max(average_length, 1e-9)
                total += idf * frequency * (self.k1 + 1) / (frequency + self.k1 * scale)
            return total

        scores = [score(document) for document in documents]
        order = sorted(range(len(sections)), key=lambda i: (-scores[i], i))
        return [sections[i] for i in order]


class EmbeddingRetriever:
    """Semantic search over a small in-memory set of sections."""

    def __init__(
        self,
        embed: Callable[[list[str]], Sequence[Sequence[float]]] | None = None,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.model_name = model_name
        self._embed = embed or self._load_model(model_name)
        self._cache: dict[str, list[float]] = {}

    @staticmethod
    def _load_model(model_name: str) -> Callable[[list[str]], Sequence[Sequence[float]]]:
        from fastembed import TextEmbedding

        model = TextEmbedding(model_name=model_name)
        return lambda texts: list(model.embed(texts))

    def _vectors(self, texts: list[str]) -> list[list[float]]:
        missing = [text for text in dict.fromkeys(texts) if text not in self._cache]
        if missing:
            for text, vector in zip(missing, self._embed(missing)):
                self._cache[text] = [float(value) for value in vector]
        return [self._cache[text] for text in texts]

    def rank(self, query: str, sections: Sequence[Section]) -> list[Section]:
        query_vector = self._vectors([query])[0]
        vectors = self._vectors([_section_text(section) for section in sections])

        def cosine(vector: list[float]) -> float:
            dot = sum(a * b for a, b in zip(query_vector, vector))
            norms = math.hypot(*query_vector) * math.hypot(*vector)
            return dot / norms if norms else 0.0

        scores = [cosine(vector) for vector in vectors]
        order = sorted(range(len(sections)), key=lambda i: (-scores[i], i))
        return [sections[i] for i in order]
