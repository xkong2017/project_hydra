import asyncio
from openai import AsyncOpenAI


class LLMClient:
    """Concurrent LLM client for vLLM server with rate limiting."""

    def __init__(self, base_url: str = "http://localhost:8000/v1", model: str = "qwen", max_concurrent: int = 6):
        self.client = AsyncOpenAI(base_url=base_url, api_key="sk-fake")
        self.model = model
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def complete(self, prompt: str, **kwargs) -> str:
        async with self.semaphore:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4096,
                **kwargs,
            )
            content = response.choices[0].message.content
            if content:
                return content

            # Retry with system prompt framing if content is None
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful analyst. Provide a detailed response."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
                **kwargs,
            )
            return response.choices[0].message.content or ""

    async def complete_many(self, prompts: list[str], **kwargs) -> list[str]:
        tasks = [self.complete(p, **kwargs) for p in prompts]
        return await asyncio.gather(*tasks)