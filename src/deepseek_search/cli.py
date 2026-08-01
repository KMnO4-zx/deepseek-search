"""CLI entry point."""

from __future__ import annotations

import argparse
import getpass
import json
import sys

from deepseek_search.client import search, DEFAULT_MODEL, DEFAULT_ENDPOINT
from deepseek_search.config import save_api_key, load_api_key, clear_api_key, resolve_api_key


def _cmd_login() -> None:
    """Save API key to config file."""
    existing = load_api_key()
    if existing:
        print(f"已保存的 API Key: {existing[:12]}...{existing[-4:]}")
        print()
        ans = input("要更新吗？[y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("已取消。")
            return

    print()
    print("请在 DeepSeek Platform 获取 API Key：")
    print("  https://platform.deepseek.com/api_keys")
    print()

    key = getpass.getpass("粘贴 API Key（输入不显示）: ").strip()
    if not key:
        print("未输入 API Key，已取消。")
        return
    if not key.startswith("sk-"):
        print("警告：API Key 通常以 sk- 开头，你输入的看起来不太对。", file=sys.stderr)

    path = save_api_key(key)
    print(f"\n✅ 已保存到 {path}")
    print(f"   文件权限已设为 600（仅你可读写）。")
    print(f"   现在可以直接运行 deepseek-search 了。")


def _cmd_logout() -> None:
    """Remove saved API key."""
    if clear_api_key():
        print("✅ 已删除保存的 API Key。")
    else:
        print("没有保存的 API Key。")


def _cmd_status() -> None:
    """Show where the API key is coming from."""
    key = load_api_key()
    if key:
        print(f"配置文件: ~/.config/deepseek-search/config.json")
        print(f"API Key:  {key[:12]}...{key[-4:]}")
    else:
        print("未保存 API Key。")
        print("运行 deepseek-search login 来设置。")


def main(argv: list[str] | None = None) -> None:
    # ── subcommand dispatch ──────────────────────────────────────────────
    # Check if the first arg is a known subcommand before falling into search mode.

    raw_args = sys.argv[1:] if argv is None else argv

    if raw_args and raw_args[0] in ("login", "logout", "status"):
        cmd = raw_args[0]
        if cmd == "login":
            _cmd_login()
        elif cmd == "logout":
            _cmd_logout()
        elif cmd == "status":
            _cmd_status()
        return

    # ── search mode ──────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        prog="deepseek-search",
        description=(
            "Web search via DeepSeek — raw results by default, "
            "with optional summary or constrained evidence."
        ),
    )

    parser.add_argument(
        "query",
        nargs="+",
        help="Search query string.",
    )

    parser.add_argument(
        "--api-key",
        default=None,
        help="DeepSeek API key. Falls back to $DEEPSEEK_API_KEY, then ~/.config/deepseek-search/config.json.",
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model to use (default: {DEFAULT_MODEL}).",
    )

    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="API endpoint URL.",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds (default: 30).",
    )

    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="Output raw JSON instead of pretty-printed text.",
    )

    output_mode = parser.add_mutually_exclusive_group()

    output_mode.add_argument(
        "--summary",
        "--summarize",
        dest="summarize",
        action="store_true",
        default=False,
        help="Let the model summarize the search results (uses output tokens).",
    )

    output_mode.add_argument(
        "--evidence",
        action="store_true",
        default=False,
        help="Return constrained source-titled evidence without a final answer.",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="deepseek-search 0.3.0",
    )

    args = parser.parse_args(argv) if argv else parser.parse_args()
    query = " ".join(args.query)

    try:
        response = search(
            query,
            api_key=resolve_api_key(args.api_key),
            model=args.model,
            endpoint=args.endpoint,
            timeout=args.timeout,
            summarize=args.summarize,
            mode="evidence" if args.evidence else None,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json_output:
        payload = {
            "query": response.query,
            "search_queries": response.search_queries,
            "total_search_requests": response.total_search_requests,
            "result_count": response.result_count,
            "results": [
                {
                    "title": r.title,
                    "url": r.url,
                    "page_age": r.page_age,
                }
                for r in response.results
            ],
            "usage": response.usage,
        }
        if args.summarize:
            payload["summary"] = response.summary
        elif args.evidence:
            payload["evidence"] = response.evidence
        print(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        if args.evidence:
            print(response.evidence or "(No evidence returned.)")
            return

        print(f"🔍  {response.query}")
        print(f"    {response.result_count} results  ·  {response.total_search_requests} search request(s)")
        if response.usage:
            input_tokens = response.usage.get("input_tokens", 0)
            output_tokens = response.usage.get("output_tokens", 0)
            print(f"    ~{input_tokens:,} input tokens  ·  ~{output_tokens:,} output tokens")
        print()
        if args.summarize:
            print("  Summary")
            print(f"  {response.summary or '(No summary returned.)'}")
        else:
            for i, r in enumerate(response.results, 1):
                age = f"  [{r.page_age}]" if r.page_age else ""
                print(f"  {i:2d}. {r.title}{age}")
                print(f"      {r.url}")


if __name__ == "__main__":
    main()
