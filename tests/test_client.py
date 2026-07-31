from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from deepseek_search.client import search


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}"


def _search_events() -> list[str]:
    return [
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
        _sse(
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "A concise "},
            }
        ),
        _sse(
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "summary."},
            }
        ),
        _sse({"type": "content_block_stop"}),
        _sse(
            {
                "type": "message_delta",
                "usage": {"output_tokens": 4},
            }
        ),
        _sse({"type": "message_stop"}),
    ]


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


class SearchSummaryTests(unittest.TestCase):
    def _run_search(self, *, summarize: bool):
        response = _FakeResponse(_search_events())
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
                summarize=summarize,
            )

        return result, response, request

    def test_default_mode_stops_before_summary_text(self) -> None:
        result, response, request = self._run_search(summarize=False)

        self.assertIsNone(result.summary)
        self.assertEqual(response.consumed[-1], 5)
        self.assertEqual(result.usage, {"input_tokens": 9})
        self.assertNotIn("summary", request["body"]["system"].lower())
        self.assertEqual(request["body"]["max_tokens"], 2048)

    def test_summary_mode_collects_text_and_final_usage(self) -> None:
        result, response, request = self._run_search(summarize=True)

        self.assertEqual(result.summary, "A concise summary.")
        self.assertEqual(response.consumed[-1], 10)
        self.assertEqual(
            result.usage,
            {"input_tokens": 9, "output_tokens": 4},
        )
        self.assertIn("summary", request["body"]["system"].lower())

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
