# AI_PROMPTS.md — AI Tool Usage Log

This document records all AI prompts used during development, including iterations, accepted/rejected outputs, and where human judgment was required.

---

## 1. System Prompt Design for the Knowledge Assistant

### Prompt Used

```
Design a system prompt for an internal knowledge assistant RAG system.
Requirements:
- Must only answer from provided context
- Must refuse when context is insufficient
- Must cite sources
- Output must be structured JSON
- Must prevent hallucination
```

### Iterations

**Iteration 1 — Initial draft:**
The AI suggested a general-purpose assistant prompt like "You are a helpful assistant that answers questions about company documents." This was too broad — no guardrails, no structured output, no refusal mechanism.

**Rejected.** Too permissive. The model could hallucinate freely.

**Iteration 2 — Added constraints:**
Added rules about only using provided context and citing sources. The AI suggested natural language output with inline citations. 

**Partially accepted.** The grounding rules were good, but natural language output makes programmatic parsing unreliable.

**Iteration 3 — Final version (accepted):**
Specified strict JSON output schema with `refused` and `refused_reason` fields. Added explicit rules: "Never fabricate information, policies, dates, or numbers." Set temperature to 0.1.

**Accepted.** This version provides:
- Deterministic, parseable output
- Explicit refusal path (no guessing)
- Source citation for explainability
- Anti-hallucination guardrails

### Why Human Judgment Was Required

- The AI initially optimized for helpfulness over safety. I had to explicitly add the refusal mechanism and JSON structure.
- The AI suggested temperature=0.7 for "more natural" responses. I overrode this to 0.1 because factual consistency matters more than natural-sounding prose for policy questions.
- I added the "never fabricate" rule after testing showed the model would invent leave day counts not present in context.

---

## 2. Architecture Design Decisions

### Prompt Used

```
Design a multi-tenant RAG architecture for an internal knowledge assistant.
Must use: PostgreSQL, vector database, Redis.
Constraints: tenant isolation, cost control, auditability.
Should be runnable via Docker Compose.
```

### Iterations

**Iteration 1:** AI suggested PostgreSQL + Milvus + Redis as separate services. This added operational complexity (3 containers, 2 database management stories).

**Rejected.** Too many moving parts for a v1 system.

**Iteration 2 (accepted):** I specified pgvector (PostgreSQL extension) to combine relational and vector storage in one database. This simplifies Docker Compose to 3 containers (postgres, redis, backend) instead of 4.

### Why Human Judgment Was Required

- Deciding between pgvector vs. a dedicated vector DB is an engineering trade-off. AI defaulted to the "standard" recommendation (separate vector DB). I chose pgvector because:
  - Our scale (thousands of documents, not millions) doesn't need a specialized vector DB
  - One database = simpler backup, migration, and debugging
  - The HNSW index in pgvector is sufficient for our QPS

---

## 3. Document Chunking Strategy

### Prompt Used

```
What's the best chunking strategy for RAG on internal company documents (policies, guidelines)?
Consider: paragraph structure, chunk overlap, token size, retrieval precision.
```

### Iterations

**Iteration 1:** AI suggested fixed 512-character chunks. This broke mid-sentence and lost context.

**Rejected.** Character-based splitting ignores semantic boundaries.

**Iteration 2:** AI suggested recursive character splitting (LangChain-style) with `\n\n`, `\n`, `.` separators. Better, but still mechanical.

**Partially accepted.** The separator hierarchy was useful, but I simplified to paragraph-first splitting.

**Iteration 3 (accepted):** Paragraph-based splitting with accumulation up to 500 tokens and 1-sentence overlap between chunks.

### Why Human Judgment Was Required

- The AI didn't consider the document structure of company policies (headers → paragraphs → bullet lists). Paragraph splitting naturally preserves these semantic units.
- I chose 500 tokens (not 512 characters) as the chunk size because tokens map to LLM context limits, not character counts.
- The overlap strategy was my addition — AI suggested either no overlap or full-paragraph overlap, neither of which was optimal.

---

## 4. Data Model Design

### Prompt Used

```
Design a PostgreSQL schema for a multi-tenant knowledge assistant.
Tables needed: tenants, documents, document chunks (with pgvector), AI requests (audit), feedback.
Key: tenant_id must be enforced everywhere.
```

### Iterations

**Iteration 1:** AI generated normalized tables without `tenant_id` on `document_chunks` (only on `documents`).

**Rejected.** This requires a JOIN during vector search, adding latency to the most performance-critical query.

**Iteration 2 (accepted):** Denormalized `tenant_id` onto `document_chunks` for direct WHERE filtering during vector search. Added HNSW index with `vector_cosine_ops`.

### Why Human Judgment Was Required

- The AI prioritized normalization (correct in general) over query performance (critical for vector search). I chose deliberate denormalization for the hot path.
- I added the `cached` boolean and token tracking columns to `ai_requests` — the AI didn't consider cost observability in the initial schema.
- The HNSW index parameters (`m=16`, `ef_construction=64`) were my choice based on pgvector documentation for medium-scale datasets.

---

## 5. Redis Caching Strategy

### Prompt Used

```
Design a Redis caching layer for a RAG query system.
Requirements: tenant-scoped, invalidation on document changes, deterministic keys.
```

### Iterations

**Iteration 1:** AI suggested caching embedding vectors. 

**Rejected.** Embedding computation is cheap (single API call); the expensive operation is the LLM completion.

**Iteration 2 (accepted):** Cache the final answer keyed by `tenant_id + sha256(question)`. Invalidate all keys for a tenant when documents change.

### Why Human Judgment Was Required

- The AI initially cached at the wrong layer (embeddings instead of answers). I corrected this because the cost driver is LLM tokens, not embedding API calls.
- I added question normalization (lowercase, strip whitespace) before hashing to improve cache hit rates. "How many leave days?" and "how many leave days?" should hit the same cache entry.

---

## 6. Tenant Isolation Design

### Prompt Used

```
How to ensure tenant data isolation in a multi-tenant RAG system?
Attack vectors: cross-tenant context in prompts, cache poisoning, vector search leakage.
```

### Iterations

**Iteration 1:** AI suggested separate databases per tenant.

**Rejected.** Too expensive operationally for a SaaS with many small tenants.

**Iteration 2 (accepted):** Shared database with mandatory `tenant_id` filtering at every layer:
- API layer: header validation
- Service layer: WHERE clauses
- Cache: tenant-prefixed keys
- Future: PostgreSQL RLS for defense-in-depth

### Why Human Judgment Was Required

- Database-per-tenant vs. shared-database is a classic trade-off. AI defaulted to strongest isolation; I chose the pragmatic approach that scales to 1000s of tenants.
- I identified cache key isolation as an attack vector the AI initially missed — without tenant_id in the cache key, one tenant could receive another's answers.

---

## 7. Code Generation and Debugging

### Prompt Used

Various prompts for generating FastAPI routes, SQLAlchemy models, and service layer code.

### Key Human Judgments

1. **Dependency injection pattern**: AI generated inline database connections. I restructured to use FastAPI's `Depends()` pattern for testability and session lifecycle management.

2. **Error handling**: AI generated happy-path code. I added:
   - Tenant validation as a reusable dependency
   - 404 responses for missing documents/requests
   - Transaction rollback on exceptions
   - Graceful degradation when Redis is unavailable

3. **Async architecture**: AI mixed sync and async patterns. I ensured consistent async/await throughout (asyncpg, async Redis, async OpenAI client).

4. **Stub providers**: The AI didn't suggest stub implementations — this was my design decision to ensure the system runs end-to-end without API keys, making it easy for reviewers to test.

---

## Summary

| Area | AI Contribution | Human Override |
|---|---|---|
| System prompt | Initial structure | Refusal mechanism, JSON schema, temperature |
| Architecture | Component listing | pgvector decision, infra simplification |
| Chunking | Algorithm options | Paragraph-first strategy, overlap design |
| Data model | Table structure | Denormalization for vector search perf |
| Caching | General approach | Cache layer selection, key design |
| Tenant isolation | Security principles | Practical shared-DB implementation |
| Code | Boilerplate generation | Async patterns, error handling, stubs |

**Key takeaway**: AI tools excel at generating boilerplate and enumerating options. Human judgment is essential for trade-off decisions, system design, and safety-critical patterns like tenant isolation and hallucination prevention.
