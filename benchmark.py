"""Benchmark script — measure token usage across multiple searches."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field

# Add src to path so we can import directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from deepseek_search.client import search, DEFAULT_MODEL

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
class BenchmarkResult:
    total: int
    success: int
    fail: int
    input_tokens: int = 0
    output_tokens: int = 0
    results_count: int = 0
    search_requests: int = 0
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


def run_benchmark(rounds: int) -> BenchmarkResult:
    result = BenchmarkResult(total=rounds, success=0, fail=0)

    for i in range(rounds):
        query = QUERIES[i % len(QUERIES)]
        try:
            t0 = time.monotonic()
            resp = search(query, timeout=60)
            elapsed = time.monotonic() - t0

            result.success += 1
            result.total_time += elapsed
            result.input_tokens += resp.usage.get("input_tokens", 0)
            result.output_tokens += resp.usage.get("output_tokens", 0)
            result.results_count += resp.result_count
            result.search_requests += resp.total_search_requests

            status = "✅" if resp.result_count > 0 else "⚠️"
            print(
                f"  [{i+1:4d}/{rounds}] {status} "
                f"in={resp.usage.get('input_tokens',0):5d}  "
                f"out={resp.usage.get('output_tokens',0):5d}  "
                f"results={resp.result_count:3d}  "
                f"{elapsed:.1f}s  {query[:40]}"
            )

        except Exception as e:
            result.fail += 1
            result.errors.append(f"[{i+1}] {query}: {e}")
            print(f"  [{i+1:4d}/{rounds}] ❌ {e}")

    return result


def extrapolate(result: BenchmarkResult, counts: list[int]) -> None:
    """Extrapolate token usage to larger sample sizes."""
    if result.success == 0:
        return

    avg_in = result.avg_input
    avg_out = result.avg_output

    print(f"\n{'='*72}")
    print(f"  实测 {result.success} 次  →  外推至更大规模")
    print(f"{'='*72}")
    print(
        f"  {'规模':<10} {'输入 token':>14} {'输出 token':>14} {'估算费用(¥)':>14}"
    )
    print(f"  {'-'*10} {'-'*14} {'-'*14} {'-'*14}")

    for n in counts:
        in_tok = avg_in * n
        out_tok = avg_out * n
        # deepseek-v4-flash pricing: ¥1/M input, ¥2/M output
        cost = (in_tok / 1_000_000) * 1 + (out_tok / 1_000_000) * 2
        print(
            f"  {n:<10} {in_tok:>14,.0f} {out_tok:>14,.0f} {cost:>14.4f}"
        )


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    print(f"deepseek-search 基准测试  ·  {n} 次搜索  ·  模型: {DEFAULT_MODEL}\n")

    result = run_benchmark(n)

    print(f"\n{'='*72}")
    print(f"  统计摘要")
    print(f"{'='*72}")
    print(f"  总次数:      {result.total}")
    print(f"  成功:        {result.success}")
    print(f"  失败:        {result.fail}")
    print(f"  每次平均输入:  {result.avg_input:,.1f} token")
    print(f"  每次平均输出:  {result.avg_output:,.1f} token")
    print(f"  每次平均耗时:  {result.avg_time:.1f}s")
    print(f"  累计搜索结果:  {result.results_count:,} 条")
    print(f"  累计搜索请求:  {result.search_requests:,} 次")

    # Pricing: deepseek-v4-flash
    cost_per_search = (result.avg_input / 1_000_000) * 1 + (
        result.avg_output / 1_000_000
    ) * 2
    print(f"  每次平均费用:  ¥{cost_per_search:.6f}")

    if result.errors:
        print(f"\n  错误详情:")
        for e in result.errors:
            print(f"    {e}")

    extrapolate(result, [100, 200, 500, 1000])


if __name__ == "__main__":
    main()
