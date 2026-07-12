#!/usr/bin/env python3
"""Run the multi-agent analysis pipeline against the live vLLM server."""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm_client import LLMClient
from src.orchestrator import Orchestrator


def main():
    # Read demo code
    demo_file = Path(__file__).parent / "demo_code.py"
    code = demo_file.read_text()

    print("=" * 70)
    print("MULTI-AGENT CODE ANALYSIS PIPELINE")
    print("Target: vLLM Qwen3.6-27B @ localhost:8000")
    print(f"Input: {demo_file.name}")
    print("=" * 70)

    client = LLMClient(max_concurrent=6)
    orchestrator = Orchestrator(client)

    async def run():
        report = await orchestrator.analyze(code)

        print(f"\nPhase 1 - Parallel Agent Reviews: {len(report.agent_results)} agents")
        for result in report.agent_results:
            status = "✅" if not result.error else "❌"
            print(f"  {status} {result.role}: {result.latency_ms:.0f}ms")

        print(f"\nPhase 2 - Summary Synthesis:")
        synth = [r for r in report.agent_results if r.role == "summary_synthesizer"]
        if synth:
            print(f"  ✅ Synthesis: {synth[0].latency_ms:.0f}ms")

        print(f"\nTotal pipeline latency: {report.total_latency_ms:.0f}ms")
        print("=" * 70)

        # Print full results
        for result in report.agent_results:
            if result.role != "summary_synthesizer":
                print(f"\n{'=' * 70}")
                print(f"[{result.role.upper()}]")
                print("=" * 70)
                print(result.content)

        if report.summary:
            print(f"\n{'=' * 70}")
            print("EXECUTIVE SUMMARY")
            print("=" * 70)
            print(report.summary)

        return report

    report = asyncio.run(run())
    return report


if __name__ == "__main__":
    main()