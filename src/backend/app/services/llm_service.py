"""LLM service — generates answers from context + question.

Supports two providers:
  • stub   — returns templated answers for local dev
  • openai — real completions via OpenAI API
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from app.config import get_settings
from app.prompts.templates import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class LLMResult:
    answer: str
    refused: bool
    refused_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str


class LLMProvider(Protocol):
    async def generate(
        self, question: str, context_chunks: list[dict]
    ) -> LLMResult: ...


# ── Stub provider ─────────────────────────────────────────


class StubLLMProvider:
    """Deterministic stub that mimics LLM behaviour without API calls.
    Generates a structured answer referencing the supplied context."""

    MODEL_NAME = "stub-model-v1"

    async def generate(self, question: str, context_chunks: list[dict]) -> LLMResult:
        if not context_chunks:
            return LLMResult(
                answer="",
                refused=True,
                refused_reason="No relevant context found in the knowledge base to answer this question.",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                model=self.MODEL_NAME,
            )

        # Build a deterministic answer from the context
        source_titles = list({c["document_title"] for c in context_chunks})
        excerpts = [c["content"][:200] for c in context_chunks[:3]]

        answer_obj = {
            "answer": (
                f"Based on the available documentation ({', '.join(source_titles)}), "
                f"here is what I found regarding your question:\n\n"
                + "\n\n".join(f"- {e}" for e in excerpts)
            ),
            "confidence": "medium",
            "sources_used": len(context_chunks),
        }

        answer_text = answer_obj["answer"]
        estimated_tokens = len(answer_text.split()) + len(question.split())

        return LLMResult(
            answer=answer_text,
            refused=False,
            refused_reason=None,
            prompt_tokens=estimated_tokens // 2,
            completion_tokens=estimated_tokens // 2,
            total_tokens=estimated_tokens,
            model=self.MODEL_NAME,
        )


# ── OpenAI provider ──────────────────────────────────────


class OpenAILLMProvider:
    """Generates answers using OpenAI chat completions."""

    def __init__(self):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    async def generate(self, question: str, context_chunks: list[dict]) -> LLMResult:
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(question, context_chunks)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or "{}"
        usage = response.usage

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"answer": raw, "confidence": "low"}

        refused = parsed.get("refused", False)

        return LLMResult(
            answer=parsed.get("answer", raw),
            refused=refused,
            refused_reason=parsed.get("refused_reason"),
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            model=self.model,
        )


# ── Factory ──────────────────────────────────────────────


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAILLMProvider()
    return StubLLMProvider()
