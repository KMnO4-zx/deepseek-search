from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from deepseek_search.client import search


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}"


def _search_events(
    *,
    final_text_parts: tuple[str, ...] = ("A concise ", "summary."),
) -> list[str]:
    events = [
        _sse(
            {
                "type": "message_start",
                "message": {"usage": {"input_tokens": 9}},
            }
        ),
        _sse(
            {
                "type": "content_block_start",
                "content_block": {
                    "type": "server_tool_use",
                    "input": {"query": "server query"},
                },
            }
        ),
        _sse({"type": "content_block_stop"}),
        _sse(
            {
                "type": "content_block_start",
                "content_block": {
                    "type": "web_search_tool_result",
                    "content": [
                        {
                            "type": "web_search_result",
                            "title": "Result",
                            "url": "https://example.com/result",
                            "page_age": "1 day ago",
                        }
                    ],
                },
            }
        ),
        _sse({"type": "content_block_stop"}),
        _sse(
            {
                "type": "content_block_start",
                "content_block": {"type": "text", "text": ""},
            }
        ),
    ]
    events.extend(
        _sse(
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": text},
            }
        )
        for text in final_text_parts
    )
    events.extend(
        [
            _sse({"type": "content_block_stop"}),
            _sse(
                {
                    "type": "message_delta",
                    "usage": {"output_tokens": 4},
                }
            ),
            _sse({"type": "message_stop"}),
        ]
    )
    return events


class _FakeResponse:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.consumed: list[int] = []

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        pass

    def iter_lines(self):
        for index, event in enumerate(self.events):
            self.consumed.append(index)
            yield event


class SearchModeTests(unittest.TestCase):
    def _run_search(
        self,
        *,
        events: list[str] | None = None,
        **search_kwargs: object,
    ):
        response = _FakeResponse(events or _search_events())
        request: dict = {}

        def fake_stream(method: str, endpoint: str, **kwargs: object):
            request.update(
                method=method,
                endpoint=endpoint,
                body=kwargs["json"],
            )
            return response

        with patch("deepseek_search.client.httpx.stream", fake_stream):
            result = search(
                "user query",
                api_key="sk-redacted",
                **search_kwargs,
            )

        return result, response, request

    def test_default_mode_stops_before_summary_text(self) -> None:
        result, response, request = self._run_search()

        self.assertIsNone(result.summary)
        self.assertIsNone(result.evidence)
        self.assertEqual(response.consumed[-1], 5)
        self.assertEqual(result.usage, {"input_tokens": 9})
        self.assertNotIn("summary", request["body"]["system"].lower())
        self.assertEqual(request["body"]["max_tokens"], 2048)

    def test_explicit_raw_mode_keeps_early_disconnect_behavior(self) -> None:
        result, response, _ = self._run_search(mode="raw")

        self.assertIsNone(result.summary)
        self.assertIsNone(result.evidence)
        self.assertEqual(response.consumed[-1], 5)
        self.assertEqual(result.usage, {"input_tokens": 9})

    def test_summary_mode_collects_text_and_final_usage(self) -> None:
        result, response, request = self._run_search(summarize=True)

        self.assertEqual(result.summary, "A concise summary.")
        self.assertIsNone(result.evidence)
        self.assertEqual(response.consumed[-1], 10)
        self.assertEqual(
            result.usage,
            {"input_tokens": 9, "output_tokens": 4},
        )
        self.assertIn("summary", request["body"]["system"].lower())

    def test_explicit_summary_mode_matches_legacy_summary(self) -> None:
        result, _, _ = self._run_search(mode="summary")

        self.assertEqual(result.summary, "A concise summary.")
        self.assertIsNone(result.evidence)

    def test_evidence_mode_uses_dedicated_system_prompt(self) -> None:
        _, _, request = self._run_search(mode="evidence")

        prompt = request["body"]["system"].lower()
        for requirement in (
            "web evidence retriever",
            "always call the web_search tool",
            "single web search",
            "only factual evidence",
            "do not answer the user's original question",
            "do not compare entities",
            "family relationships",
            "temporal ordering",
            "causal relationships",
            "combine facts across sources",
            "at most 8 independent evidence items",
            "source title",
            "one or two concise factual sentences",
            "do not include urls",
            '"the answer is"',
            '"therefore"',
            '"in conclusion"',
        ):
            self.assertIn(requirement, prompt)

    def test_evidence_mode_concatenates_all_text_deltas(self) -> None:
        expected = (
            "[1] Source: Film page\n"
            "Evidence: The page identifies the film's director."
        )
        events = _search_events(
            final_text_parts=(
                "[1] Source: Film page\n",
                "Evidence: The page identifies ",
                "the film's director.",
            )
        )

        result, _, _ = self._run_search(events=events, mode="evidence")

        self.assertEqual(result.evidence, expected)
        self.assertIsNone(result.summary)

    def test_evidence_mode_stops_at_message_stop(self) -> None:
        events = _search_events()
        message_stop_index = len(events) - 1
        events.append(
            _sse(
                {
                    "type": "error",
                    "error": {"message": "must not be consumed"},
                }
            )
        )

        _, response, _ = self._run_search(events=events, mode="evidence")

        self.assertEqual(response.consumed[-1], message_stop_index)

    def test_evidence_mode_preserves_final_usage(self) -> None:
        result, _, _ = self._run_search(mode="evidence")

        self.assertEqual(
            result.usage,
            {"input_tokens": 9, "output_tokens": 4},
        )

    def test_evidence_mode_preserves_results_without_adding_urls_to_text(self) -> None:
        evidence = "[1] Source: Result\nEvidence: A source-backed fact."
        events = _search_events(final_text_parts=(evidence,))

        result, _, _ = self._run_search(events=events, mode="evidence")

        self.assertEqual(result.result_count, 1)
        self.assertEqual(result.total_search_requests, 1)
        self.assertEqual(result.search_queries, ["server query"])
        self.assertEqual(result.results[0].title, "Result")
        self.assertEqual(result.results[0].url, "https://example.com/result")
        self.assertNotIn("https://", result.evidence or "")
        self.assertNotIn("example.com", result.evidence or "")

    def test_legacy_summarize_false_and_true_remain_compatible(self) -> None:
        raw, raw_response, _ = self._run_search(summarize=False)
        summary, summary_response, _ = self._run_search(summarize=True)

        self.assertIsNone(raw.summary)
        self.assertIsNone(raw.evidence)
        self.assertEqual(raw_response.consumed[-1], 5)
        self.assertEqual(summary.summary, "A concise summary.")
        self.assertIsNone(summary.evidence)
        self.assertEqual(summary_response.consumed[-1], 10)

    def test_conflicting_summarize_and_mode_raise_clear_errors(self) -> None:
        for mode in ("raw", "evidence"):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(
                    ValueError,
                    rf"summarize=True cannot be combined with mode='{mode}'",
                ):
                    search(
                        "user query",
                        api_key="sk-redacted",
                        summarize=True,
                        mode=mode,
                    )

    def test_invalid_mode_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "mode must be one of: 'raw', 'summary', 'evidence'",
        ):
            search(
                "user query",
                api_key="sk-redacted",
                mode="invalid",  # type: ignore[arg-type]
            )

    def test_summary_mode_can_collect_direct_answer_with_auto_tool_choice(self) -> None:
        events = [
            _sse(
                {
                    "type": "content_block_start",
                    "content_block": {"type": "text", "text": "Direct "},
                }
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "answer."},
                }
            ),
            _sse({"type": "content_block_stop"}),
            _sse({"type": "message_stop"}),
        ]
        response = _FakeResponse(events)

        with patch(
            "deepseek_search.client.httpx.stream",
            return_value=response,
        ):
            result = search(
                "user query",
                api_key="sk-redacted",
                force_search=False,
                summarize=True,
            )

        self.assertEqual(result.summary, "Direct answer.")


if __name__ == "__main__":
    unittest.main()
