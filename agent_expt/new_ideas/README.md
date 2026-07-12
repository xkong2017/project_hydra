# Multi-Agent Code Analysis Pipeline

A production-grade system that runs 6 specialized AI agents in parallel against a local LLM to produce comprehensive code reviews.

## Architecture

```
Code Input → Orchestrator → [6 Parallel Agents] → Synthesizer → Report
```

## Quick Start

```bash
# 1. Ensure vLLM server is running on port 8000
# 2. Install dependencies
pip install fastapi uvicorn openai pydantic pytest pytest-asyncio

# 3. Run tests
python3 -m pytest tests/ -v

# 4. Run analysis
python3 scripts/run_analysis.py

# 5. Or start the API
uvicorn src.app:app --host 0.0.0.0 --port 8080
```

## Agent Roles

| Role | Focus |
|------|-------|
| Security Reviewer | OWASP, secrets, injection |
| Performance Analyst | Complexity, bottlenecks |
| Architecture Critic | Coupling, patterns, scalability |
| Test Coverage Checker | Gaps, edge cases |
| Style Auditor | Naming, nesting, dead code |
| Summary Synthesizer | Executive summary |

## Key Metrics

- **2.9x speedup** via parallel execution (277s vs 800s sequential)
- **94% GPU utilization** on GB10
- **4/4 tests passing**
- **OpenAI-compatible** — works with vLLM, Ollama, LM Studio

## Project Structure

```
src/          Core engine and API
tests/        Test suite
scripts/      Demo and analysis scripts
docs/         Report and LinkedIn posts
```