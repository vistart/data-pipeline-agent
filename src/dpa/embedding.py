"""Embedding-based tool matching using pg_vector.

Provides semantic tool retrieval by embedding tool descriptions and
matching them against user queries. Uses ``rhosocial-activerecord-postgres``
pg_vector support for cosine similarity search.

Architecture::

    User Query --> EmbeddingService._simple_embedding()
               --> pg_vector <=> operator (cosine distance)
               --> Top-K tool matches
               --> Injected into LLM prompt as context

The current implementation uses a simple hash-based embedding for
demonstration. In production, replace with a real embedding model
(e.g. OpenAI text-embedding-3-small, Cohere embed-v3).

Usage::

    from dpa.embedding import EmbeddingService, init_tool_index

    # Index all tools (run once at startup)
    init_tool_index()

    # Search for relevant tools
    service = EmbeddingService()
    context = service.get_tool_context("parse CSV files")
    # Returns: "Relevant tools for this query:\\n- parse_data: ..."
"""

from __future__ import annotations

import math
import os
from typing import Annotated, Optional

from rhosocial.activerecord.base.fields import UseSqlType
from rhosocial.activerecord.backend.impl.postgres.expression.types import PostgresVectorType
from rhosocial.activerecord.backend.impl.postgres.types.pgvector import PostgresVector
from rhosocial.activerecord.model import ActiveRecord


class ToolEmbedding(ActiveRecord):
    """ORM model for storing tool embeddings in pg_vector.

    Each record stores a tool's name, description, optional keywords,
    and a 64-dimensional vector embedding for similarity search.

    Table: ``tool_embeddings``
    """

    __table_name__ = "tool_embeddings"

    id: Annotated[int, UseSqlType(postgres="INTEGER")]
    """Primary key, auto-incremented."""

    tool_name: Annotated[str, UseSqlType(postgres="VARCHAR(64)")]
    """Unique tool identifier (e.g. ``"parse_data"``)."""

    description: Annotated[str, UseSqlType(postgres="TEXT")]
    """Human-readable tool description for embedding generation."""

    keywords: Annotated[Optional[str], UseSqlType(postgres="TEXT")]
    """Comma-separated keywords for additional matching context."""

    embedding: Annotated[PostgresVector, UseSqlType(PostgresVectorType(dim=64))]
    """64-dimensional vector embedding for cosine similarity search."""


class EmbeddingService:
    """Service for embedding-based tool retrieval.

    Provides tool indexing and search capabilities using pg_vector.
    The ``get_tool_context()`` method generates a context string suitable
    for injection into LLM prompts.
    """

    def __init__(self) -> None:
        """Initialize the embedding service with 64-dimensional vectors."""
        self._dim = 64

    def _simple_embedding(self, text: str) -> list[float]:
        """Generate a simple hash-based embedding from text.

        This is a demonstration implementation. For production use,
        replace with a real embedding model API call.

        Args:
            text: Input text to embed.

        Returns:
            A list of 64 floats representing the embedding.
        """
        words = text.lower().split()
        vocab = set(words)
        embedding = []
        for word in sorted(vocab):
            hash_val = hash(word) % 1000 / 1000.0
            embedding.append(hash_val)
        while len(embedding) < self._dim:
            embedding.append(0.0)
        return embedding[:self._dim]

    def index_tool(self, tool_name: str, description: str, keywords: list[str] | None = None) -> None:
        """Index a tool into the pg_vector store.

        Generates an embedding from the tool's name, description, and
        keywords, then saves it to the ``tool_embeddings`` table.

        Args:
            tool_name: Unique tool identifier.
            description: Human-readable tool description.
            keywords: Optional list of keywords for additional context.
        """
        text = f"{tool_name} {description}"
        if keywords:
            text += " " + " ".join(keywords)

        embedding = self._simple_embedding(text)
        vector = PostgresVector(embedding)

        record = ToolEmbedding(
            id=0,
            tool_name=tool_name,
            description=description,
            keywords=",".join(keywords) if keywords else None,
            embedding=vector,
        )
        record.save()

    def search_tools(self, query: str, top_k: int = 3) -> list[dict]:
        """Search for the most relevant tools using cosine similarity.

        Uses pg_vector's ``<=>`` operator to compute cosine distance
        between the query embedding and all indexed tool embeddings.

        Args:
            query: Natural language query (e.g. "parse CSV files").
            top_k: Number of top results to return.

        Returns:
            List of dicts with keys: ``tool_name``, ``description``,
            ``similarity`` (0.0 to 1.0, higher = more similar).
        """
        query_embedding = self._simple_embedding(query)
        query_vector = PostgresVector(query_embedding)

        # Cosine distance search via pg_vector <=> operator
        results = ToolEmbedding.query().raw(
            f"""
            SELECT tool_name, description,
                   1 - (embedding <=> %s::vector({self._dim})) as similarity
            FROM tool_embeddings
            ORDER BY embedding <=> %s::vector({self._dim})
            LIMIT %s
            """,
            (str(query_vector), str(query_vector), top_k),
        )

        return [
            {"tool_name": r[0], "description": r[1], "similarity": float(r[2])}
            for r in results
        ]

    def get_tool_context(self, query: str, top_k: int = 3) -> str:
        """Generate a tool context string for LLM prompt injection.

        Searches for the most relevant tools and formats them as a
        readable list suitable for inclusion in a system prompt.

        Args:
            query: Natural language query to match against.
            top_k: Number of tools to include.

        Returns:
            Formatted string with tool names, descriptions, and similarity
            scores. Returns empty string if no tools are indexed.
        """
        results = self.search_tools(query, top_k)
        if not results:
            return ""

        context_parts = ["Relevant tools for this query:"]
        for r in results:
            context_parts.append(f"- {r['tool_name']}: {r['description']} (similarity: {r['similarity']:.3f})")

        return "\n".join(context_parts)


def init_tool_index() -> None:
    """Index all registered tools into pg_vector.

    Iterates over all tools in the TOOL_REGISTRY and creates embedding
    records for each. Run once at application startup.
    """
    from dpa.tools import get_tools

    service = EmbeddingService()
    tools = get_tools()

    for tool in tools:
        service.index_tool(
            tool.name,
            tool.description,
            keywords=getattr(tool, "keywords", []),
        )

    print(f"Indexed {len(tools)} tools to pg_vector")


if __name__ == "__main__":
    init_tool_index()
