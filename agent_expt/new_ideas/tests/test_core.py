import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from src.llm_client import LLMClient
from src.orchestrator import Orchestrator, AgentResult, AnalysisReport


@pytest.mark.asyncio
async def test_llm_client_complete():
    with patch("src.llm_client.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = AsyncMock(
            choices=[AsyncMock(message=AsyncMock(content="test response"))]
        )

        client = LLMClient()
        result = await client.complete("test prompt")
        assert result == "test response"


@pytest.mark.asyncio
async def test_llm_client_concurrent():
    with patch("src.llm_client.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = AsyncMock(
            choices=[AsyncMock(message=AsyncMock(content="response"))]
        )

        client = LLMClient(max_concurrent=3)
        prompts = ["p1", "p2", "p3", "p4", "p5", "p6"]
        results = await client.complete_many(prompts)
        assert len(results) == 6
        assert all(r == "response" for r in results)


@pytest.mark.asyncio
async def test_orchestrator_analyze():
    with patch("src.orchestrator.LLMClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value="agent result")
        MockClient.return_value = mock_client

        orch = Orchestrator()
        report = await orch.analyze("def hello(): pass")

        assert len(report.agent_results) == 5  # 5 reviewer agents
        assert report.summary is not None
        assert report.total_latency_ms > 0


def test_analysis_report_structure():
    report = AnalysisReport(code_snippet="test code")
    assert report.code_snippet == "test code"
    assert report.agent_results == []
    assert report.summary is None
    assert report.total_latency_ms == 0.0