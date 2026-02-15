# Internal Knowledge Assistant

A multi-tenant, RAG-powered internal knowledge assistant that answers employee questions using ingested documents, with source citations and hallucination guards.

**Option C — Internal Knowledge Assistant** | Built for the Aura Wellness AI Engineer assessment.

---

## Table of Contents

- [Approach](#approach)
- [Assumptions](#assumptions)
- [Trade-offs](#trade-offs)
- [Architecture](#architecture)
- [Section A — Core AI System Design](#section-a--core-ai-system-design)
- [Section B — RAG Design](#section-b--rag-design)
- [Section C — Cost Control Strategy](#section-c--cost-control-strategy)
- [Section D — Tenant Isolation Strategy](#section-d--tenant-isolation-strategy)
- [Section E — Execution Reality Check](#section-e--execution-reality-check)
- [Runbook](#runbook)
- [What I Would Improve With More Time](#what-i-would-improve-with-more-time)

---

## Approach

I chose **Option C — Internal Knowledge Assistant** because it exercises the broadest set of AI engineering skills: RAG pipeline design, vector search, prompt engineering with safety guardrails, multi-tenant data isolation, and caching for cost control.

**Core decisions:**

1. **Python + FastAPI** — fastest path to a production-quality async API with auto-generated OpenAPI docs.
2. **PostgreSQL + pgvector** — single database for both relational data and vector search. Simplifies ops, avoids a separate vector DB deployment, and pgvector's HNSW index handles our scale.
3. **Redis** — tenant-scoped query cache with TTL. Same question → same answer → skip the LLM call entirely.
4. **Stub providers** — LLM and embedding providers are pluggable. The stub mode generates deterministic outputs so the full pipeline runs end-to-end without an API key.

## Assumptions

- Documents are primarily markdown/text (no binary PDF parsing in v1).
- Tenants are pre-provisioned (not self-service registration).
- The stub LLM is acceptable for demonstrating the data flow; swapping to OpenAI requires only setting `LLM_PROVIDER=openai` and providing an API key.
- Embedding dimension of 384 is used for the stub; real OpenAI embeddings would use 1536 (configurable via `EMBEDDING_DIMENSION`).
- Authentication/authorization is simplified to a tenant header (`X-Tenant-Id`). Production would use JWT/OAuth.

## Trade-offs

| Decision | Benefit | Cost |
|---|---|---|
| pgvector instead of Milvus/Qdrant | Simpler infra, single DB | Less tuning for billion-scale datasets |
| Stub LLM provider | Runs anywhere, no API key needed | Answers are templated, not truly generative |
| Paragraph-based chunking | Preserves semantic coherence | May miss optimal split points |
| Header-based tenant auth | Simple, easy to test | Not production auth (needs JWT) |
| Sync seed script via HTTP | Tests the real API path | Requires backend to be running first |

---

## Architecture

```
┌──────────────┐     ┌──────────────────────────────────────────┐
│   Client     │────▶│           FastAPI (API Layer)            │
│  (curl/app)  │     │  ┌──────────┐  ┌──────────────────────┐  │
└──────────────┘     │  │  Routes  │  │  Dependencies        │  │
                     │  │  /ask    │  │  (tenant validation) │  │
                     │  │  /docs   │  └──────────────────────┘  │
                     │  └────┬─────┘                            │
                     │       │                                  │
                     │  ┌────▼─────────────────────────────────┐│
                     │  │           Service Layer              ││
                     │  │  ┌────────────┐  ┌────────────────┐  ││
                     │  │  │ Query Svc  │  │ Document Svc   │  ││
                     │  │  │ (RAG pipe) │  │ (ingest+chunk) │  ││
                     │  │  └─────┬──────┘  └───────┬────────┘  ││
                     │  │        │                 │           ││
                     │  │  ┌─────▼──────┐  ┌───────▼────────┐  ││
                     │  │  │ LLM Svc    │  │ Embedding Svc  │  ││
                     │  │  │(stub/openai)│ │(stub/openai)   │  ││
                     │  │  └────────────┘  └────────────────┘  ││
                     │  │        │                  │          ││
                     │  │  ┌─────▼──────────────────▼────────┐ ││
                     │  │  │       Cache Service (Redis)     │ ││
                     │  │  └─────────────────────────────────┘ ││
                     │  └──────────────────────────────────────┘│
                     └──────────────────────────────────────────┘
                             │                  │
                     ┌───────▼──────┐   ┌───────▼──────┐
                     │  PostgreSQL  │   │    Redis     │
                     │  + pgvector  │   │   (cache)    │
                     │              │   │              │
                     │ • tenants    │   │ • query cache│
                     │ • documents  │   │   (TTL-based)│
                     │ • chunks     │   │              │
                     │ • ai_requests│   └──────────────┘
                     │ • feedback   │
                     └──────────────┘
```

### RAG Pipeline Flow

```
 Question → Cache Check → Embed Question → Vector Search (tenant-scoped)
                                              │
                                              ▼
                                    Top-K Chunks Retrieved
                                              │
                                              ▼
                              Build Prompt (system + context + question)
                                              │
                                              ▼
                                    LLM Generate Answer
                                              │
                                              ▼
                              Audit Log → Cache Result → Respond
```

---

## Section A — Core AI System Design

### A1. Problem Framing

**Who is the user?**
Non-technical employees (HR, operations, marketing, support, recepptionists at the clinics) who need quick answers to internal questions — "How many vacation days do I get?", "What's the password policy?", "How do I submit expenses?", "What are the botox promotions available this month?", etc.

**What decision are they trying to make?**
They need to understand company policies, processes, and guidelines to make day-to-day operational decisions without waiting for HR/IT responses.

**Why is a rule-based system insufficient?**

1. **Natural language variability** — employees ask the same question dozens of ways ("annual leave", "vacation days", "PTO", "time off"). Rule-based systems require explicit keyword mapping for every variant.
2. **Cross-document reasoning** — answers may span multiple documents. An LLM can synthesize across chunks naturally.
3. **Evolving knowledge base** — policies are updated frequently. A RAG system adapts automatically when documents are re-ingested; a rule-based system needs manual rule updates.
4. **Conversational nuance** — "Can I take 3 weeks off next month?" requires understanding leave policy amounts, approval processes, and notice requirements simultaneously.

### A2. System Architecture

See the [Architecture](#architecture) section above for the full diagram. Key components:

- **API Layer**: FastAPI with async endpoints, OpenAPI auto-docs, tenant validation via dependency injection
- **LLM Usage**: Chat completions (GPT-4o-mini or stub) with structured JSON output, temperature=0.1 for consistency
- **Prompt Layer**: Modular templates in `app/prompts/templates.py` — system prompt sets guardrails, user prompt injects retrieved context
- **PostgreSQL Schema**: 5 tables (tenants, documents, document_chunks, ai_requests, feedback) with tenant_id foreign keys throughout
- **Vector DB (pgvector)**: HNSW index on `document_chunks.embedding` column, cosine distance, filtered by `tenant_id`
- **Redis**: Tenant-scoped query cache keyed on `ka:query:{tenant_id}:{hash(question)}`, TTL=3600s

### A3. Data Model

```sql
tenants
├── id (UUID PK)
├── name, slug (unique)
├── is_active
└── created_at, updated_at

documents
├── id (UUID PK)
├── tenant_id (FK → tenants)   -- TENANT ISOLATION
├── title, content, doc_type
├── metadata (JSONB)
└── created_at, updated_at

document_chunks
├── id (UUID PK)
├── document_id (FK → documents)
├── tenant_id (FK → tenants)   -- DENORMALIZED FOR FAST FILTERING
├── chunk_index
├── content, token_count
├── embedding (vector(384))    -- PGVECTOR
└── metadata (JSONB)

ai_requests
├── id (UUID PK)
├── tenant_id (FK → tenants)   -- TENANT ISOLATION
├── question, answer, sources (JSONB)
├── status (pending/completed/refused/error)
├── prompt_tokens, completion_tokens, total_tokens
├── model_used, latency_ms, cached
└── created_at

feedback
├── id (UUID PK)
├── request_id (FK → ai_requests)
├── tenant_id (FK → tenants)   -- TENANT ISOLATION
├── rating (1-5), comment
└── created_at
```

**TenantId enforcement:**
- Every table has a `tenant_id` column (foreign key to `tenants`).
- `document_chunks.tenant_id` is denormalized from `documents` for fast vector search filtering without JOINs.
- All API queries include `WHERE tenant_id = :tenant_id`.
- The `X-Tenant-Id` header is validated in a FastAPI dependency before any route handler executes.

### A4. Prompt Design

**System Prompt** (see `src/backend/app/prompts/templates.py`):

```
You are an Internal Knowledge Assistant for a company.
Your role is to answer employee questions using ONLY the provided context documents.

## STRICT RULES
1. Answer ONLY based on the provided context. Do NOT use external knowledge.
2. If the context does not contain enough information, you MUST refuse and explain why.
3. Always cite which document(s) your answer is based on.
4. Keep answers concise, professional, and actionable.
5. Never fabricate information, policies, dates, or numbers.
6. If the question is ambiguous, state your interpretation before answering.

## OUTPUT FORMAT
{
  "answer": "Your answer text here",
  "confidence": "high | medium | low",
  "sources_used": ["Document Title 1"],
  "refused": false,
  "refused_reason": null
}
```

**User Prompt:**

```
## CONTEXT DOCUMENTS
--- Document 1: Employee Leave Policy ---
[retrieved chunk content]

--- Document 2: Company Wellness Benefits ---
[retrieved chunk content]

## EMPLOYEE QUESTION
How many days of annual leave do I get?

Answer the question based ONLY on the context documents above.
```

**Why this structure:**

1. **Strict grounding** — rules 1, 2, 5 directly combat hallucination by forbidding external knowledge and fabrication.
2. **Structured JSON output** — enables programmatic parsing, quality scoring, and refusal detection without regex hacking.
3. **Source citation** — `sources_used` field makes the answer explainable to business users and auditable.
4. **Explicit refusal path** — the `refused` + `refused_reason` fields give the system a graceful way to say "I don't know" rather than guessing.
5. **Low temperature (0.1)** — reduces creative variation; we want factual consistency, not novelty.

---

## Section B — RAG Design

### How Documents Are Chunked

1. **Split by paragraphs** — double-newline (`\n\n`) preserves semantic boundaries (a section header + its content stay together).
2. **Accumulate until ~500 tokens** — small paragraphs are merged to avoid under-contextualized chunks that lose meaning in isolation.
3. **1-sentence overlap** — the last sentence of each chunk is prepended to the next chunk, ensuring continuity across chunk boundaries.
4. **Token counting** — estimated by `len(words) / 0.75`, which matches empirical token ratios for English text.

**Why this approach:**
- Fixed-size character splits break mid-sentence and lose context. Paragraph-based splitting preserves the author's logical grouping.
- 500-token chunks balance precision (not too large → diluted relevance) vs. context (not too small → missing information).
- Overlap prevents "boundary blindness" where relevant information spans two chunks.

### How Embeddings Are Stored

- Embeddings are stored as `vector(384)` columns in the `document_chunks` table using **pgvector**.
- An **HNSW index** (`vector_cosine_ops`) enables fast approximate nearest-neighbor search.
- Embeddings are generated at ingestion time (batch call to embedding provider) and stored alongside the chunk text.

### How Retrieval Is Filtered Per Tenant

```sql
SELECT chunk_id, content, similarity
FROM document_chunks dc
JOIN documents d ON d.id = dc.document_id
WHERE dc.tenant_id = :tenant_id                        -- HARD FILTER
  AND 1 - (dc.embedding <=> :query_vec) > 0.3          -- SIMILARITY THRESHOLD
ORDER BY dc.embedding <=> :query_vec
LIMIT 5
```

- **`tenant_id` is a hard WHERE clause** — applied *before* the vector search, not as a post-filter. This guarantees zero cross-tenant data leakage.
- The `tenant_id` is denormalized onto `document_chunks` specifically to avoid a JOIN during vector search.
- A minimum similarity threshold (0.3) filters out irrelevant matches — if no chunks pass, the LLM receives empty context and the system refuses to answer.

---

## Section C — Cost Control Strategy

### How Token Usage Is Limited

1. **Short, focused chunks (500 tokens)** — only relevant context is sent to the LLM, not entire documents.
2. **Top-K retrieval (K=5)** — caps context to ~2,500 tokens maximum, keeping prompt costs predictable.
3. **Compact system prompt** — ~200 tokens of instructions, not verbose chains of thought.
4. **`max_tokens=1024`** on completions — hard cap on response length.
5. **Structured JSON output** — forces concise answers; the model doesn't ramble.
6. **Token auditing** — every `ai_requests` row records `prompt_tokens`, `completion_tokens`, `total_tokens` for monitoring and alerting.

### When AI Responses Are Cached

- **Redis cache with tenant-scoped keys**: `ka:query:{tenant_id}:{sha256(question)[:16]}`
- **TTL = 1 hour** (configurable via `CACHE_TTL_SECONDS`).
- Cache is **invalidated per tenant** when documents are ingested or deleted (knowledge base changed).
- Cache hit flow: question → hash → Redis GET → if found, return immediately (no embedding, no vector search, no LLM call).
- This alone can reduce LLM costs by 60-80% for common repeated questions ("What's the password policy?" asked by 50 employees).

### When AI Should NOT Be Used

1. **Exact lookups** — "What's the HR email?" should be a database query, not an LLM call. V2 would add structured metadata search.
2. **Binary validations** — "Is my expense under $100?" is arithmetic, not AI.
3. **No relevant context** — if vector search returns zero chunks above threshold, the system refuses immediately without calling the LLM.
4. **Rate limiting** — production would add per-tenant rate limits in Redis to prevent runaway costs from misbehaving integrations.

---

## Section D — Tenant Isolation Strategy

### How Prompts Avoid Cross-Tenant Leakage

1. **Tenant validation at the edge** — `X-Tenant-Id` is extracted and validated in a FastAPI dependency *before* any route handler runs. Invalid/missing tenant = 400/404 immediately.
2. **All database queries include `WHERE tenant_id = :tenant_id`** — this is enforced at the service layer, not optional.
3. **Context is tenant-scoped** — the LLM only receives document chunks belonging to the requesting tenant. It physically cannot reference another tenant's data.
4. **Cache keys include tenant_id** — `ka:query:{tenant_id}:{hash}` prevents one tenant from reading another's cached answers.
5. **Audit trail is tenant-scoped** — request history API filters by tenant_id.

### How Vector Search Is Scoped

- `document_chunks.tenant_id` is a denormalized column indexed for fast filtering.
- The SQL query applies `WHERE dc.tenant_id = :tenant_id` as a pre-filter before the HNSW vector search.
- This is a **hard isolation boundary** — not a soft filter or post-processing step.
- In production, Row-Level Security (RLS) in PostgreSQL could add a defense-in-depth layer.

---

## Section E — Execution Reality Check

### 1. What would you ship in 2 weeks?

- The core RAG pipeline (ingest → chunk → embed → retrieve → answer) with the OpenAI provider.
- Multi-tenant document management API.
- Redis caching for repeated queries.
- JWT authentication (replacing the header-based approach).
- Basic monitoring dashboards (token usage per tenant, cache hit rates, latency P99).
- Seed script and admin UI for uploading documents.

### 2. What would you explicitly not build yet?

- **Conversational memory / follow-up questions** — adds complexity with session state; v1 is single-turn.
- **PDF/Word parsing** — stick to markdown/text; document conversion is a separate concern.
- **Fine-tuning or custom models** — GPT-4o-mini + good prompts covers 90% of use cases.
- **Real-time document sync** — v1 is push-based (API upload); watch-folder or webhook integration is v2.
- **User-facing UI** — API-first; the frontend team can build against OpenAPI docs.

### 3. What risks worry you the most?

1. **Hallucination on edge cases** — even with grounding instructions, LLMs can fabricate details on ambiguous questions. Mitigation: confidence scoring + mandatory source citation + human feedback loop.
2. **Embedding quality drift** — if the embedding model changes, all stored vectors need re-computation. Mitigation: track model version in chunk metadata.
3. **Cost blowup** — a popular question with no cache hit generates LLM costs per request. Mitigation: aggressive caching, rate limiting, token budgets per tenant.
4. **Stale answers** — cached answers persist after policies change. Mitigation: cache invalidation on document update, short TTLs for sensitive topics.

---

## Runbook

### Prerequisites

- **Docker** (v20+) and **Docker Compose** (v2+)
- No other dependencies — everything runs in containers.

### One-Command Startup

```bash
docker compose up --build
```

This starts:
- **PostgreSQL 16 + pgvector** on port 5432
- **Redis 7** on port 6379
- **FastAPI backend** on port 8000

### Environment Variables

Copy `.env.example` to `.env` to customize (optional — defaults work out of the box):

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `stub` | `stub` for local dev, `openai` for real LLM |
| `OPENAI_API_KEY` | _(empty)_ | Required only if `LLM_PROVIDER=openai` |
| `EMBEDDING_PROVIDER` | `stub` | `stub` for deterministic embeddings |
| `CACHE_TTL_SECONDS` | `3600` | How long to cache query results |

### Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy", "postgres": "ok", "redis": "ok", "version": "1.0.0"}
```

### Example API Calls

**1. List tenants (pre-seeded):**
```bash
curl http://localhost:8000/api/v1/tenants
```

**2. Ingest a document:**
```bash
curl -X POST http://localhost:8000/api/v1/documents \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11" \
  -d '{
    "title": "Employee Leave Policy",
    "content": "# Leave Policy\n\nAll employees get 20 days of annual leave.\n\nSick leave: 10 days per year.\n\nParental leave: 16 weeks for primary caregivers.",
    "doc_type": "markdown"
  }'
```

**3. Ask a question (core RAG flow):**
```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11" \
  -d '{"question": "How many days of annual leave do I get?"}'
```

**4. Submit feedback on an answer:**
```bash
curl -X POST http://localhost:8000/api/v1/requests/{request_id}/feedback \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11" \
  -d '{"rating": 5, "comment": "Accurate and well-sourced"}'
```

**5. View request history (audit trail):**
```bash
curl http://localhost:8000/api/v1/requests \
  -H "X-Tenant-Id: a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
```

### Seed Sample Data

After the system is running, load sample internal documents:

```bash
docker compose exec backend python -m app.seed_data
```

This loads 5 sample documents (leave policy, IT security, onboarding, expenses, wellness benefits) and confirms the full ingestion pipeline works.

### OpenAPI Documentation

Interactive API docs available at: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## What I Would Improve With More Time

1. **JWT/OAuth authentication** — replace the `X-Tenant-Id` header with proper token-based auth.
2. **Streaming responses** — SSE stream from the LLM for better UX on longer answers.
3. **Conversation context** — multi-turn conversations with session tracking.
4. **Document versioning** — track changes over time, diff-based re-embedding.
5. **Hybrid search** — combine vector similarity with BM25 keyword search for better retrieval.
6. **Evaluation pipeline** — automated tests comparing LLM outputs against golden answers.
7. **Observability** — OpenTelemetry tracing, Prometheus metrics, Grafana dashboards.
8. **Row-Level Security** — PostgreSQL RLS as defense-in-depth for tenant isolation.
9. **PDF/DOCX parsing** — extend ingestion to handle binary document formats.
10. **Admin dashboard** — UI for managing documents, reviewing feedback, monitoring costs.