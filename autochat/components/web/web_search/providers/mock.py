import logging
from typing import Any

from injector import singleton

from autochat.components.web.web_search.models import WebSearchResult
from autochat.components.web.web_search.providers.base import BaseWebSearchProvider

logger = logging.getLogger(__name__)


@singleton
class MockSearchProvider(BaseWebSearchProvider):
    def __init__(self) -> None:
        self._requests_count = 0

    async def make_query(
        self, query: str, num_links: int = 10, **kwargs: Any
    ) -> list[WebSearchResult]:
        self._requests_count += 1
        mock_results = [
            WebSearchResult(
                idx=1,
                title="What is retrieval-augmented generation?",
                url="https://example.com/guides/retrieval-augmented-generation",
                description="Retrieval-augmented generation (RAG) <strong>grounds a language model's answer in documents fetched at query time</strong>, so responses can cite their sources.",
                age="100 days ago",
            ),
            WebSearchResult(
                idx=2,
                title="Vector search explained - Example Docs",
                url="https://example.com/docs/vector-search",
                description="Vector search <strong>finds passages by meaning rather than exact keywords</strong>, by comparing embeddings with a similarity measure such as cosine distance.",
                age="2 weeks ago",
            ),
            WebSearchResult(
                idx=3,
                title="Chunking strategies for document retrieval",
                url="https://example.org/blog/chunking-strategies",
                description="Splitting documents into overlapping chunks at ingestion time keeps prompts small and lets retrieval return only the relevant parts.",
                age="",
            ),
            WebSearchResult(
                idx=4,
                title="Running language models locally - Example Wiki",
                url="https://example.org/wiki/local-llm",
                description="Local inference servers expose <strong>an OpenAI-compatible HTTP API</strong>, so applications can switch between hosted and self-hosted models.",
                age="",
            ),
            WebSearchResult(
                idx=5,
                title="Measuring latency in LLM applications",
                url="https://example.com/articles/llm-latency",
                description="Time to first token and total latency are measured separately: the first reflects prompt processing, the second also includes generation length.",
                age="March 19, 2025",
            ),
        ]

        results = mock_results[:num_links]
        logger.debug(
            f"Mock search completed for query: '{query}' - {len(results)} results"
        )
        return results

    def get_rate_limit_info(self) -> dict[str, Any]:
        return {
            "provider": "mock",
            "requests_made": self._requests_count,
            "is_rate_limited": False,
        }

    async def close(self) -> None:
        logger.debug("MockSearchProvider closed")
