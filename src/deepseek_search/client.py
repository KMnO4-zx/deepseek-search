"""Core client for raw search, summaries, and constrained evidence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

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
    """The complete search response, with optional generated text."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    total_search_requests: int = 0
    usage: dict = field(default_factory=dict)
    summary: str | None = None
    evidence: str | None = None

    @property
    def result_count(self) -> int:
        return len(self.results)


# ── constants ───────────────────────────────────────────────────────────────

DEFAULT_ENDPOINT = "https://api.deepseek.com/anthropic/v1/messages"
DEFAULT_MODEL = "deepseek-v4-flash"
SSE_DATA = re.compile(r"^data:\s*(\{.*\})$")
SearchMode = Literal["raw", "summary", "evidence"]

RAW_SYSTEM_PROMPT = (
    "You are a web search proxy. For every query, your first and only "
    "task is to call the web_search tool. Do not answer from your own "
    "knowledge. Always search first."
)

SUMMARY_SYSTEM_PROMPT = (
    "You are a web search assistant. Always call the web_search tool "
    "before answering. After searching, answer the user's query with "
    "a concise summary grounded in the search results. Include source "
    "links when useful. Do not answer from your own knowledge."
)

EVIDENCE_SYSTEM_PROMPT = """You are a web evidence retriever.

Always call the web_search tool before producing any text.
Use a single web search whenever possible.

Return only factual evidence explicitly supported by the retrieved search
results. Do not answer the user's original question. Do not provide a final
conclusion. Do not compare entities, determine which candidate is correct,
infer family relationships, temporal ordering, or causal relationships, or
combine facts across sources.

Return at most 8 independent evidence items. Each item must contain:
- the source title
- one or two concise factual sentences grounded in that source

Do not include URLs in the evidence text.
Do not use phrases such as "the answer is", "therefore", or "in conclusion".

Format:

[1] Source: <source title>
Evidence: <fact stated by this source>

[2] Source: <source title>
Evidence: <fact stated by this source>"""


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


def _resolve_mode(*, summarize: bool, mode: SearchMode | None) -> SearchMode:
    """Resolve the new mode switch while preserving the summarize API."""
    if mode is None:
        return "summary" if summarize else "raw"

    if mode not in ("raw", "summary", "evidence"):
        raise ValueError("mode must be one of: 'raw', 'summary', 'evidence'")

    if summarize and mode in ("raw", "evidence"):
        raise ValueError(
            f"summarize=True cannot be combined with mode={mode!r}; "
            "use mode='summary' or omit mode"
        )

    return mode


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
    mode: SearchMode | None = None,
) -> SearchResponse:
    """
    Perform a web search via DeepSeek's API.

    By default the stream is aborted before the model generates a summary.
    Set ``summarize=True`` or ``mode="summary"`` to return the model's final
    answer. Set ``mode="evidence"`` to return constrained, source-titled facts
    without asking the model to answer the original question.

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
    mode:
        Explicitly select ``"raw"``, ``"summary"``, or ``"evidence"``.
        When omitted, ``summarize`` preserves its existing behavior.
    """

    resolved_mode = _resolve_mode(summarize=summarize, mode=mode)

    api_key = resolve_api_key(api_key)

    tool_def: dict = {
        "type": "web_search_20260209",
        "name": "web_search",
    }

    system_prompt = {
        "raw": RAW_SYSTEM_PROMPT,
        "summary": SUMMARY_SYSTEM_PROMPT,
        "evidence": EVIDENCE_SYSTEM_PROMPT,
    }[resolved_mode]

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
    final_text_parts: list[str] = []

    current_block_type: str | None = None
    has_search_results = False  # only abort text after we've received results
    search_request_count = 0     # count web_search_tool_result blocks
    collecting_final_text = False

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
                        if resolved_mode == "raw":
                            break
                        collecting_final_text = True
                        initial_text = block.get("text", "")
                        if initial_text:
                            final_text_parts.append(initial_text)
                    elif resolved_mode == "summary" and not force_search:
                        # With automatic tool choice, a direct model answer is
                        # the final response when no search was performed.
                        collecting_final_text = True
                        initial_text = block.get("text", "")
                        if initial_text:
                            final_text_parts.append(initial_text)

                elif current_block_type == "server_tool_use":
                    collecting_final_text = False
                    if resolved_mode != "raw":
                        # Keep only text produced after the final search round.
                        final_text_parts = []
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
                    and resolved_mode != "raw"
                    and collecting_final_text
                ):
                    final_text_parts.append(delta.get("text", ""))

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
                    collecting_final_text = False

            # ── message delta / stop ──────────────────────────────────────
            elif etype == "message_delta":
                # Full-response modes reach final usage. This is retained as a
                # safety fallback in raw mode if the final text block is absent.
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

    final_text = "".join(final_text_parts).strip() or None

    return SearchResponse(
        query=query,
        results=results,
        search_queries=search_queries,
        total_search_requests=search_request_count,
        usage=usage,
        summary=final_text if resolved_mode == "summary" else None,
        evidence=final_text if resolved_mode == "evidence" else None,
    )
