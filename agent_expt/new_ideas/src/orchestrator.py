import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from src.llm_client import LLMClient
from src.agents import AGENT_ROLES


@dataclass
class AgentResult:
    role: str
    content: str
    latency_ms: float
    error: str | None = None


@dataclass
class AnalysisReport:
    code_snippet: str
    agent_results: list[AgentResult] = field(default_factory=list)
    summary: str | None = None
    total_latency_ms: float = 0.0
    health_score: float = 5.0


class Orchestrator:
    """Runs 6 agent reviews in parallel via concurrent LLM calls."""

    REVIEWER_ROLES = [
        "security_reviewer",
        "performance_analyst",
        "architecture_critic",
        "test_coverage_checker",
        "style_auditor",
    ]
    SYNTHESIZER_ROLE = "summary_synthesizer"

    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    async def analyze(self, code: str, roles: list[str] | None = None) -> AnalysisReport:
        roles = roles or self.REVIEWER_ROLES
        report = AnalysisReport(code_snippet=code)
        start = time.monotonic()

        # Phase 1: Parallel agent reviews
        prompts = []
        for role in roles:
            template = AGENT_ROLES[role]["prompt"]
            prompts.append((role, template.format(code=code)))

        tasks = [self._run_agent(role, prompt) for role, prompt in prompts]
        results = await asyncio.gather(*tasks)
        report.agent_results = results

        # Phase 2: Synthesize summary
        reports_text = "\n\n".join(
            f"--- {r.role} ---\n{r.content}" for r in results
        )
        synth_prompt = AGENT_ROLES[self.SYNTHESIZER_ROLE]["prompt"].format(
            agent_reports=reports_text
        )
        summary_result = await self._run_agent(self.SYNTHESIZER_ROLE, synth_prompt)
        report.summary = summary_result.content

        report.total_latency_ms = (time.monotonic() - start) * 1000
        return report

    async def _run_agent(self, role: str, prompt: str) -> AgentResult:
        start = time.monotonic()
        try:
            content = await self.client.complete(prompt)
            latency = (time.monotonic() - start) * 1000
            return AgentResult(role=role, content=content, latency_ms=latency)
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return AgentResult(role=role, content="", latency_ms=latency, error=str(e))