"""Benchmark raw-search and summary modes with the same query set."""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

# Add src to path so we can import directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from deepseek_search.client import search, DEFAULT_MODEL

INPUT_PRICE_PER_MILLION = 1.0
OUTPUT_PRICE_PER_MILLION = 2.0
EXTRAPOLATION_COUNTS = [100, 200, 500, 1000]

QUERIES = [
    "Python 3.14 new features",
    "Rust async programming tutorial",
    "DeepSeek V4 API pricing",
    "latest machine learning research 2026",
    "中国芯片产业最新进展",
    "climate change policy updates",
    "OpenAI GPT-5 release date",
    "量子计算最新突破",
    "日本地震最新消息",
    "best laptops for programming 2026",
    "Kubernetes vs Docker Swarm 2026",
    "typescript 7.0 features",
    "Nobel Prize 2026 predictions",
    "electric vehicle battery technology advances",
    "全球股市今日行情",
    "COVID variant latest update 2026",
    "Llama 5 release date Meta",
    "法国大选最新结果",
    "mars exploration NASA 2026",
    "golang 2.0 generics",
    "北京今日天气",
    "Samsung Galaxy S26 review",
    "PostgreSQL 18 performance benchmarks",
    "最便宜的云服务器推荐 2026",
    "webassembly 最新进展",
    "Bitcoin price prediction 2026",
    "Apple Vision Pro 3 review",
    "React 20 new features",
    "非洲经济发展趋势 2026",
    "fusion energy breakthrough",
]


@dataclass
class SampleResult:
    index: int
    query: str
    elapsed: float
    input_tokens: int = 0
    output_tokens: int = 0
    results_count: int = 0
    search_requests: int = 0
    summary_chars: int = 0
    error: str | None = None


@dataclass
class BenchmarkResult:
    summarize: bool
    total: int
    success: int = 0
    fail: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    results_count: int = 0
    search_requests: int = 0
    summary_chars: int = 0
    total_time: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def avg_input(self) -> float:
        return self.input_tokens / self.success if self.success else 0

    @property
    def avg_output(self) -> float:
        return self.output_tokens / self.success if self.success else 0

    @property
    def avg_time(self) -> float:
        return self.total_time / self.success if self.success else 0

    @property
    def mode_label(self) -> str:
        return "开启 summary" if self.summarize else "关闭 summary"


def estimate_cost(input_tokens: float, output_tokens: float) -> float:
    """Estimate CNY cost using cache-miss input pricing."""
    return (
        input_tokens / 1_000_000 * INPUT_PRICE_PER_MILLION
        + output_tokens / 1_000_000 * OUTPUT_PRICE_PER_MILLION
    )


def _run_one(
    index: int,
    query: str,
    *,
    summarize: bool,
    timeout: float,
) -> SampleResult:
    t0 = time.monotonic()
    try:
        response = search(
            query,
            timeout=timeout,
            summarize=summarize,
        )
        return SampleResult(
            index=index,
            query=query,
            elapsed=time.monotonic() - t0,
            input_tokens=response.usage.get("input_tokens", 0),
            output_tokens=response.usage.get("output_tokens", 0),
            results_count=response.result_count,
            search_requests=response.total_search_requests,
            summary_chars=len(response.summary or ""),
        )
    except Exception as exc:
        return SampleResult(
            index=index,
            query=query,
            elapsed=time.monotonic() - t0,
            error=str(exc),
        )


def run_benchmark(
    rounds: int,
    *,
    summarize: bool,
    workers: int,
    timeout: float,
) -> BenchmarkResult:
    result = BenchmarkResult(summarize=summarize, total=rounds)
    mode = result.mode_label
    print(f"\n{'='*88}")
    print(f"  {mode}  ·  {rounds} 个查询  ·  workers={workers}")
    print(f"{'='*88}")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                _run_one,
                index,
                QUERIES[(index - 1) % len(QUERIES)],
                summarize=summarize,
                timeout=timeout,
            )
            for index in range(1, rounds + 1)
        ]

        for future in as_completed(futures):
            sample = future.result()
            if sample.error is not None:
                result.fail += 1
                result.errors.append(
                    f"[{sample.index}] {sample.query}: {sample.error}"
                )
                print(
                    f"  [{sample.index:3d}/{rounds}] ❌ "
                    f"{sample.elapsed:6.1f}s  {sample.error}"
                )
                continue

            result.success += 1
            result.total_time += sample.elapsed
            result.input_tokens += sample.input_tokens
            result.output_tokens += sample.output_tokens
            result.results_count += sample.results_count
            result.search_requests += sample.search_requests
            result.summary_chars += sample.summary_chars

            status = "✅" if sample.results_count > 0 else "⚠️"
            print(
                f"  [{sample.index:3d}/{rounds}] {status} "
                f"in={sample.input_tokens:6d}  "
                f"out={sample.output_tokens:5d}  "
                f"results={sample.results_count:3d}  "
                f"requests={sample.search_requests:2d}  "
                f"{sample.elapsed:6.1f}s  {sample.query[:34]}"
            )

    return result


def print_summary(result: BenchmarkResult) -> None:
    print(f"\n  {result.mode_label}统计")
    print(f"  成功/失败:       {result.success}/{result.fail}")
    print(f"  每次平均输入:    {result.avg_input:,.1f} token")
    print(f"  每次平均输出:    {result.avg_output:,.1f} token")
    print(f"  每次平均耗时:    {result.avg_time:.1f}s")
    print(f"  累计搜索结果:    {result.results_count:,} 条")
    print(f"  累计搜索请求:    {result.search_requests:,} 次")
    if result.summarize and result.success:
        print(
            f"  每次平均总结:    "
            f"{result.summary_chars / result.success:,.1f} 字符"
        )
    print(
        f"  每次估算费用:    "
        f"¥{estimate_cost(result.avg_input, result.avg_output):.6f}"
    )

    if result.errors:
        print("  错误详情:")
        for error in result.errors:
            print(f"    {error}")


def print_markdown_table(results: list[BenchmarkResult]) -> None:
    print("\nREADME Markdown 表格")
    print("| 模式 | 搜索次数 | 输入 token | 输出 token | 估算费用 |")
    print("|---|---:|---:|---:|---:|")
    for result in results:
        if result.success == 0:
            continue
        for count in EXTRAPOLATION_COUNTS:
            input_tokens = result.avg_input * count
            output_tokens = result.avg_output * count
            cost = estimate_cost(input_tokens, output_tokens)
            print(
                f"| {result.mode_label} | {count:,} | "
                f"~{input_tokens:,.0f} | ~{output_tokens:,.0f} | "
                f"¥{cost:.4f} |"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark raw-search and summary modes.",
    )
    parser.add_argument("rounds", nargs="?", type=int, default=30)
    parser.add_argument(
        "--mode",
        choices=("raw", "summary", "both"),
        default="both",
    )
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    if args.rounds < 1:
        parser.error("rounds must be at least 1")
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    print(
        f"deepseek-search 基准测试  ·  模型: {DEFAULT_MODEL}  ·  "
        f"每组 {args.rounds} 个查询"
    )
    print(
        "计价: 缓存未命中输入 ¥1/百万 token，输出 ¥2/百万 token"
    )

    summarize_modes = {
        "raw": [False],
        "summary": [True],
        "both": [False, True],
    }[args.mode]

    results: list[BenchmarkResult] = []
    for summarize in summarize_modes:
        result = run_benchmark(
            args.rounds,
            summarize=summarize,
            workers=args.workers,
            timeout=args.timeout,
        )
        results.append(result)
        print_summary(result)

    print_markdown_table(results)
    if any(not result.summarize for result in results):
        print(
            "\n注意：关闭 summary 会在最终 usage 到达前提前断流，"
            "其 token 与费用只是客户端可见值，不代表最终账单。"
        )


if __name__ == "__main__":
    main()
