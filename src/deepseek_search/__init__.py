"""Strip DeepSeek's web search out of the model."""

from deepseek_search.client import search, SearchResult, SearchResponse

__all__ = ["search", "SearchResult", "SearchResponse"]
__version__ = "0.2.0"
