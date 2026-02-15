"""Prompt templates for the Internal Knowledge Assistant.

Design rationale:
  1. System prompt sets strict guardrails — only answer from provided context
  2. Structured JSON output for programmatic consumption
  3. Explicit refusal instruction to combat hallucination
  4. Source citation requirement for explainability
"""

from __future__ import annotations


def build_system_prompt() -> str:
    """System prompt — sets behaviour, guardrails, and output format."""
    return """You are an Internal Knowledge Assistant for a company.
Your role is to answer employee questions using ONLY the provided context documents.

## STRICT RULES
1. Answer ONLY based on the provided context. Do NOT use external knowledge.
2. If the context does not contain enough information to answer the question,
   you MUST refuse to answer and explain why.
3. Always cite which document(s) your answer is based on.
4. Keep answers concise, professional, and actionable.
5. Never fabricate information, policies, dates, or numbers.
6. If the question is ambiguous, state your interpretation before answering.

## OUTPUT FORMAT
Respond with valid JSON matching this schema:
{
  "answer": "Your answer text here",
  "confidence": "high | medium | low",
  "sources_used": ["Document Title 1", "Document Title 2"],
  "refused": false,
  "refused_reason": null
}

If you cannot answer from context:
{
  "answer": "",
  "confidence": "none",
  "sources_used": [],
  "refused": true,
  "refused_reason": "Explanation of why the context is insufficient"
}"""


def build_user_prompt(question: str, context_chunks: list[dict]) -> str:
    """Constructs the user message with retrieved context and question."""
    context_parts: list[str] = []
    for i, chunk in enumerate(context_chunks, 1):
        title = chunk.get("document_title", "Unknown")
        content = chunk.get("content", "")
        context_parts.append(f"--- Document {i}: {title} ---\n{content}\n")

    context_block = (
        "\n".join(context_parts)
        if context_parts
        else "(No context documents available)"
    )

    return f"""## CONTEXT DOCUMENTS
{context_block}

## EMPLOYEE QUESTION
{question}

Answer the question based ONLY on the context documents above.
If the context is insufficient, refuse and explain why."""
