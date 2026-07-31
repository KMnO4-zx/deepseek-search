from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from deepseek_search.cli import main
from deepseek_search.client import SearchResponse, SearchResult


class CliSummaryTests(unittest.TestCase):
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
        self.assertEqual(json.loads(output.getvalue())["summary"], "The summary.")

    def test_default_json_schema_does_not_add_summary(self) -> None:
        response = SearchResponse(query="topic")
        output = io.StringIO()

        with (
            patch("deepseek_search.cli.resolve_api_key", return_value="sk-redacted"),
            patch("deepseek_search.cli.search", return_value=response),
            contextlib.redirect_stdout(output),
        ):
            main(["--json", "topic"])

        self.assertNotIn("summary", json.loads(output.getvalue()))

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
