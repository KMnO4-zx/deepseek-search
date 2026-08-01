from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from deepseek_search.cli import main
from deepseek_search.client import SearchResponse, SearchResult


class CliModeTests(unittest.TestCase):
    def test_summary_flag_is_forwarded_and_added_to_json(self) -> None:
        response = SearchResponse(
            query="topic",
            results=[
                SearchResult(
                    title="Result",
                    url="https://example.com/result",
                )
            ],
            summary="The summary.",
        )
        output = io.StringIO()

        with (
            patch("deepseek_search.cli.resolve_api_key", return_value="sk-redacted"),
            patch("deepseek_search.cli.search", return_value=response) as mocked_search,
            contextlib.redirect_stdout(output),
        ):
            main(["--summary", "--json", "topic"])

        self.assertTrue(mocked_search.call_args.kwargs["summarize"])
        self.assertIsNone(mocked_search.call_args.kwargs["mode"])
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["summary"], "The summary.")
        self.assertNotIn("evidence", payload)

    def test_default_json_schema_does_not_add_summary(self) -> None:
        response = SearchResponse(query="topic")
        output = io.StringIO()

        with (
            patch("deepseek_search.cli.resolve_api_key", return_value="sk-redacted"),
            patch("deepseek_search.cli.search", return_value=response),
            contextlib.redirect_stdout(output),
        ):
            main(["--json", "topic"])

        payload = json.loads(output.getvalue())
        self.assertNotIn("summary", payload)
        self.assertNotIn("evidence", payload)

    def test_evidence_flag_is_forwarded_and_added_to_json(self) -> None:
        evidence = "[1] Source: Result\nEvidence: A source-backed fact."
        response = SearchResponse(
            query="topic",
            results=[
                SearchResult(
                    title="Result",
                    url="https://example.com/result",
                )
            ],
            total_search_requests=1,
            usage={"input_tokens": 9, "output_tokens": 4},
            evidence=evidence,
        )
        output = io.StringIO()

        with (
            patch("deepseek_search.cli.resolve_api_key", return_value="sk-redacted"),
            patch("deepseek_search.cli.search", return_value=response) as mocked_search,
            contextlib.redirect_stdout(output),
        ):
            main(["--evidence", "--json", "topic"])

        call = mocked_search.call_args.kwargs
        self.assertFalse(call["summarize"])
        self.assertEqual(call["mode"], "evidence")
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["evidence"], evidence)
        self.assertEqual(payload["total_search_requests"], 1)
        self.assertEqual(payload["result_count"], 1)
        self.assertEqual(
            payload["usage"],
            {"input_tokens": 9, "output_tokens": 4},
        )
        self.assertEqual(
            payload["results"][0]["url"],
            "https://example.com/result",
        )
        self.assertNotIn("summary", payload)

    def test_evidence_text_output_only_shows_evidence(self) -> None:
        evidence = "[1] Source: Result\nEvidence: A source-backed fact."
        response = SearchResponse(
            query="topic",
            results=[
                SearchResult(
                    title="Hidden result",
                    url="https://example.com/hidden",
                )
            ],
            evidence=evidence,
        )
        output = io.StringIO()

        with (
            patch("deepseek_search.cli.resolve_api_key", return_value="sk-redacted"),
            patch("deepseek_search.cli.search", return_value=response),
            contextlib.redirect_stdout(output),
        ):
            main(["--evidence", "topic"])

        self.assertEqual(output.getvalue(), f"{evidence}\n")

    def test_summary_and_evidence_flags_are_mutually_exclusive(self) -> None:
        for summary_flag in ("--summary", "--summarize"):
            with self.subTest(summary_flag=summary_flag):
                stderr = io.StringIO()

                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        main([summary_flag, "--evidence", "topic"])

                self.assertEqual(raised.exception.code, 2)
                self.assertIn("not allowed with argument", stderr.getvalue())

    def test_summary_text_output_does_not_append_search_results(self) -> None:
        response = SearchResponse(
            query="topic",
            results=[
                SearchResult(
                    title="Result that should stay hidden",
                    url="https://example.com/hidden",
                )
            ],
            summary="The summary.",
        )
        output = io.StringIO()

        with (
            patch("deepseek_search.cli.resolve_api_key", return_value="sk-redacted"),
            patch("deepseek_search.cli.search", return_value=response),
            contextlib.redirect_stdout(output),
        ):
            main(["--summary", "topic"])

        rendered = output.getvalue()
        self.assertIn("The summary.", rendered)
        self.assertNotIn("Search results", rendered)
        self.assertNotIn("Result that should stay hidden", rendered)
        self.assertNotIn("https://example.com/hidden", rendered)


if __name__ == "__main__":
    unittest.main()
