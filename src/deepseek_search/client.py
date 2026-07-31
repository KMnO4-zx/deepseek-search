"""Core client for raw streaming search and optional model summaries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import httpx

from deepseek_search.config import resolve_api_key

# ── data types ──────────────────────────────────────────────────────────────


@dataclass
class SearchResult:
    """A single web search result."""

    title: str
    url: str
    page_age: str | None = None


@dataclass
class SearchResponse:
    """The complete search response, with an optional AI summary."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    total_search_requests: int = 0
    usage: dict = field(default_factory=dict)
    summary: str | None = None

    @property
    def result_count(self) -> int:
        return len(self.results)


# ── constants ───────────────────────────────────────────────────────────────

DEFAULT_ENDPOINT = "https://api.deepseek.com/anthropic/v1/messages"
DEFAULT_MODEL = "deepseek-v4-flash"
SSE_DATA = re.compile(r"^data:\s*(\{.*\})$")


def _parse_sse(line: str) -> dict | None:
    """Parse an SSE ``data:`` line into a dict, or None."""
    if not line.startswith("data:"):
        return None
    m = SSE_DATA.match(line)
    if not m:
        return None
    try:
        return json.loads(m.group(1))  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return None


# ── public API ──────────────────────────────────────────────────────────────


def search(
    query: str,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 30.0,
    force_search: bool = True,
    summarize: bool = False,
) -> SearchResponse:
    """
    Perform a web search via DeepSeek's API.

    By default the stream is aborted before the model generates a summary.
    Set ``summarize=True`` to keep reading and return the model's final text.

    Parameters
    ----------
    query:
        The search query.
    api_key:
        DeepSeek API key. Defaults to ``DEEPSEEK_API_KEY`` env var.
    model:
        Model name. Defaults to ``deepseek-v4-flash`` (cheapest).
    endpoint:
        API endpoint. Defaults to DeepSeek's Anthropic-compatible endpoint.
    timeout:
        HTTP timeout in seconds.
    force_search:
        If True, force the model to use web search via ``tool_choice: any``.
        If False, the model may choose to answer from its own knowledge
        without searching.
    summarize:
        If True, let the model generate a final summary after searching.
        This consumes output tokens. Defaults to False.
    """

    api_key = resolve_api_key(api_key)

    tool_def: dict = {
        "type": "web_search_20260209",
        "name": "web_search",
    }

    if summarize:
        system_prompt = (
            "You are a web search assistant. Always call the web_search tool "
            "before answering. After searching, answer the user's query with "
            "a concise summary grounded in the search results. Include source "
            "links when useful. Do not answer from your own knowledge."
        )
    else:
        system_prompt = (
            "You are a web search proxy. For every query, your first and only "
            "task is to call the web_search tool. Do not answer from your own "
            "knowledge. Always search first."
        )

    body: dict = {
        "model": model,
        "max_tokens": 2048,
        "system": system_prompt,
        "messages": [{"role": "user", "content": query}],
        "tools": [tool_def],
        "tool_choice": {"type": "any"} if force_search else {"type": "auto"},
        "stream": True,
    }

    results: list[SearchResult] = []
    search_queries: list[str] = []
    usage: dict = {}
    partial_query: list[str] = []
    summary_parts: list[str] = []

    current_block_type: str | None = None
    has_search_results = False  # only abort text after we've received results
    search_request_count = 0     # count web_search_tool_result blocks
    collecting_summary = False

    with httpx.stream(
        "POST",
        endpoint,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
        },
        json=body,
        timeout=timeout,
    ) as resp:
        resp.raise_for_status()

        for line in resp.iter_lines():
            event = _parse_sse(line)
            if event is None:
                continue

            etype = event.get("type")

            # ── message_start ──────────────────────────────────────────
            if etype == "message_start":
                msg = event.get("message", {})
                usage = dict(msg.get("usage", {}))

            # ── content block start ────────────────────────────────────
            elif etype == "content_block_start":
                block = event.get("content_block", {})
                current_block_type = block.get("type")

                if current_block_type == "text":
                    if has_search_results:
                        if not summarize:
                            break
                        collecting_summary = True
                        initial_text = block.get("text", "")
                        if initial_text:
                            summary_parts.append(initial_text)
                    elif summarize and not force_search:
                        # With automatic tool choice, a direct model answer is
                        # the final response when no search was performed.
                        collecting_summary = True
                        initial_text = block.get("text", "")
                        if initial_text:
                            summary_parts.append(initial_text)

                elif current_block_type == "server_tool_use":
                    collecting_summary = False
                    if summarize:
                        # Keep only text produced after the final search round.
                        summary_parts = []
                    search_queries.append(
                        block.get("input", {}).get("query", "")
                    )

                elif current_block_type == "web_search_tool_result":
                    has_search_results = True
                    search_request_count += 1
                    for item in block.get("content", []):
                        if item.get("type") == "web_search_result":
                            results.append(
                                SearchResult(
                                    title=item.get("title", ""),
                                    url=item.get("url", ""),
                                    page_age=item.get("page_age"),
                                )
                            )

            # ── content block delta ────────────────────────────────────
            elif etype == "content_block_delta":
                delta = event.get("delta", {})

                if delta.get("type") == "web_search_delta":
                    partial = delta.get("partial", {})
                    if partial.get("type") == "web_search_result":
                        results.append(
                            SearchResult(
                                title=partial.get("title", ""),
                                url=partial.get("url", ""),
                                page_age=partial.get("page_age"),
                            )
                        )

                elif delta.get("type") == "input_json_delta":
                    partial_query.append(delta.get("partial_json", ""))

                elif (
                    delta.get("type") == "text_delta"
                    and summarize
                    and collecting_summary
                ):
                    summary_parts.append(delta.get("text", ""))

            # ── content block stop ─────────────────────────────────────
            elif etype == "content_block_stop":
                if current_block_type == "server_tool_use":
                    # Try to parse the accumulated query JSON
                    if partial_query:
                        try:
                            parsed = json.loads("".join(partial_query))
                            q = parsed.get("query", "")
                            if q and (not search_queries or search_queries[-1] != q):
                                search_queries[-1] = q
                        except json.JSONDecodeError:
                            pass
                    partial_query = []

                elif current_block_type == "web_search_tool_result":
                    # Results done. Don't break — there may be more rounds.
                    pass

                elif current_block_type == "text":
                    collecting_summary = False

            # ── message delta / stop ──────────────────────────────────────
            elif etype == "message_delta":
                # Reached in summary mode; retained as a safety fallback in
                # raw-results mode if the server omits the final text block.
                usage.update(event.get("usage", {}))

            # ── message stop ───────────────────────────────────────────
            elif etype == "message_stop":
                break

            # ── error ──────────────────────────────────────────────────
            elif etype == "error":
                err = event.get("error", {})
                raise RuntimeError(
                    f"DeepSeek API error: {err.get('message', 'unknown')}"
                )

    return SearchResponse(
        query=query,
        results=results,
        search_queries=search_queries,
        total_search_requests=search_request_count,
        usage=usage,
        summary="".join(summary_parts).strip() or None,
    )
