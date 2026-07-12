import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.orchestrator import Orchestrator, AnalysisReport

app = FastAPI(title="Multi-Agent Code Analyzer", version="1.0.0")
orchestrator = Orchestrator()


class CodeRequest(BaseModel):
    code: str
    roles: list[str] | None = None


class FileRequest(BaseModel):
    file_path: str
    roles: list[str] | None = None


@app.post("/analyze")
async def analyze_code(request: CodeRequest) -> dict:
    """Analyze code with multi-agent review."""
    report = await orchestrator.analyze(request.code, request.roles)
    return {
        "summary": report.summary,
        "agent_results": [
            {"role": r.role, "content": r.content, "latency_ms": r.latency_ms, "error": r.error}
            for r in report.agent_results
        ],
        "total_latency_ms": report.total_latency_ms,
    }


@app.post("/analyze/file")
async def analyze_file(request: FileRequest) -> dict:
    """Analyze code from a file path."""
    path = Path(request.file_path)
    if not path.exists():
        raise HTTPException(404, f"File not found: {request.file_path}")
    code = path.read_text()
    report = await orchestrator.analyze(code, request.roles)
    return {
        "file": str(path),
        "summary": report.summary,
        "agent_results": [
            {"role": r.role, "content": r.content, "latency_ms": r.latency_ms, "error": r.error}
            for r in report.agent_results
        ],
        "total_latency_ms": report.total_latency_ms,
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": "qwen", "server": "http://localhost:8000"}


# CLI entry point
if __name__ == "__main__":
    import sys

    def run_cli(code: str) -> None:
        report = asyncio.run(orchestrator.analyze(code))
        print("\n" + "=" * 70)
        print("MULTI-AGENT CODE ANALYSIS REPORT")
        print("=" * 70)

        for result in report.agent_results:
            status = "✅" if not result.error else "❌"
            print(f"\n{status} [{result.role}] ({result.latency_ms:.0f}ms)")
            print("-" * 50)
            print(result.content[:800])
            if len(result.content) > 800:
                print("... (truncated)")

        if report.summary:
            print("\n" + "=" * 70)
            print("EXECUTIVE SUMMARY")
            print("=" * 70)
            print(report.summary)

        print(f"\nTotal latency: {report.total_latency_ms:.0f}ms")

    if len(sys.argv) < 2:
        print("Usage: python -m src.app <file.py>")
        sys.exit(1)

    code = Path(sys.argv[1]).read_text()
    run_cli(code)