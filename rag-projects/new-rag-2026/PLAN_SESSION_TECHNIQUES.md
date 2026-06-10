# PLAN_SESSION_TECHNIQUES.md
# Session Techniques: graphrag-assistant → new-rag-2026 (PLAN_V2)

> **Companion to `PLAN_LEARNING.md`** — that document covers the session-level learning loop
> (fact extraction, gap detection, `LearnedFact` persistence). This document covers everything
> *around* learning: how sessions are modelled, stored, windowed, rewritten, classified,
> retrieved against, verified, and logged. Together they form the complete session layer of PLAN_V2.

---

## Overview

The existing `graphrag-assistant` project contains 10 proven session techniques.
This document reviews each one and maps it into `new-rag-2026` under one of three dispositions:

| Disposition | Meaning |
|---|---|
| **Carry over** | Copy the pattern verbatim — it fits directly |
| **Adapt** | The logic is right but the execution context changes (async, multi-agent, MS GraphRAG schema) |
| **Upgrade** | The new project can do meaningfully better |

---

## Technique 1 — Session State Model

**Source**: `models/session.py`

### What the existing project does

```python
class SessionMessage(BaseModel):
    role: str           # "user" | "assistant"
    content: str
    timestamp: datetime # UTC, set at append time

class SessionState(BaseModel):
    session_id: str
    created_at: datetime
    last_active: datetime   # updated on every get_session() call
    messages: list[SessionMessage]
```

`last_active` drives TTL eviction — every `get_session()` call refreshes it so the clock
only counts idle time, not total session age.

### Disposition: **Adapt**

The core shape is correct. PLAN_V2 extends both models with multi-agent metadata.

#### `SessionMessage` additions

```python
class SessionMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime
    agent: str | None = None          # which domain agent produced this reply
    sources: list[str] | None = None  # source IDs (TextUnit IDs) cited
```

`agent` is `None` for user messages and orchestrator-synthesized replies.
It is set (e.g. `"policy"`, `"hr"`) only when a single domain agent owns the reply without synthesis.
`sources` enables per-turn citation replay in the UI.

#### `SessionState` additions

```python
class AgentTraceEntry(BaseModel):
    domain: str
    rewritten_query: str
    reply: str
    confidence: int          # 1–5 from verification
    token_count: int         # prompt + completion for this agent call

class SessionState(BaseModel):
    session_id: str
    created_at: datetime
    last_active: datetime
    messages: list[SessionMessage]
    # --- new fields ---
    agent_trace: list[AgentTraceEntry] = []   # per-turn domain agent log (PLAN_V2 §9)
    query_type: str = "LOCAL"                 # last used query type
    active_domains: list[str] = []            # domains used in last turn
    message_count: int = 0                    # updated on append; triggers learning at threshold

    @property
    def turn_count(self) -> int:
        return len([m for m in self.messages if m.role == "user"])
```

`agent_trace` is reset each turn (not accumulated across turns) — it is a debug/trace
artifact for the current request, not a history store.
`message_count` is used by `LearningService` to decide when to run fact extraction
(see `PLAN_LEARNING.md` §3).

**File**: `new-rag-2026/models/session.py`

---

## Technique 2 — Session Store: Thread-Safe In-Memory Service

**Source**: `services/session_service.py`

### What the existing project does

```python
class SessionService:
    def __init__(self, ttl: int = 3600):
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True
        )
        self._cleanup_thread.start()

    def _cleanup_loop(self):
        while True:
            time.sleep(300)
            self._evict_expired()

    def _evict_expired(self):
        now = datetime.utcnow()
        with self._lock:
            expired = [
                sid for sid, s in self._sessions.items()
                if (now - s.last_active).total_seconds() > self._ttl
            ]
            for sid in expired:
                del self._sessions[sid]
        logger.info("sessions_evicted", count=len(expired))
```

### Disposition: **Adapt**

The new project is async-first (FastAPI + asyncio). `threading.Lock()` blocks the event loop
if held during IO. Replace with async primitives throughout.

#### Async rewrite

```python
import asyncio
import aiosqlite
from contextlib import asynccontextmanager

class SessionService:
    def __init__(self, ttl: int = 3600):
        self._sessions: dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl
        self._learning_service: LearningService | None = None   # injected post-init

    async def start(self):
        """Call from FastAPI lifespan — replaces daemon thread."""
        asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(300)
            await self._evict_expired()

    async def _evict_expired(self):
        now = datetime.utcnow()
        async with self._lock:
            expired = [
                sid for sid, s in self._sessions.items()
                if (now - s.last_active).total_seconds() > self._ttl
            ]
            sessions_to_learn = []
            for sid in expired:
                session = self._sessions.pop(sid)
                if session.message_count >= 4 and self._learning_service:
                    sessions_to_learn.append(session)

        logger.info("sessions_evicted", count=len(expired))

        # Fire learning tasks AFTER releasing the lock
        for session in sessions_to_learn:
            asyncio.create_task(
                self._learning_service.process_session(session)
            )
```

**Key changes from existing**:

1. `threading.Lock()` → `asyncio.Lock()` — never blocks the event loop
2. `threading.Thread(daemon=True)` → `asyncio.create_task()` in FastAPI lifespan
3. On expiry with `message_count >= 4`: fire `learning_service.process_session(session)` as a
   background task (see `PLAN_LEARNING.md`) — the existing project has no equivalent
4. Learning tasks are fired *after* the lock is released to avoid deadlock

#### FastAPI lifespan wiring

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await session_service.start()   # starts cleanup loop
    yield
    # graceful shutdown: cancel cleanup task if needed

app = FastAPI(lifespan=lifespan)
```

**File**: `new-rag-2026/services/session_service.py`

---

## Technique 3 — History Windowing

**Source**: `graph_rag_service.py:35-38`

### What the existing project does

```python
# graph_rag_service.py:35-38
recent_history = session.messages[-10:]  # last 10 messages = 5 turns
```

Only the last 10 messages are passed to the LLM for each request. This prevents:
- Context bloat as sessions grow
- Conflicting information from stale early turns being weighted equally

### Disposition: **Carry over** (with one upgrade for domain agents)

The 10-message window is the right default for the orchestrator. In multi-agent, domain
agents receive an even shorter window because their system prompt is already domain-focused
and the combined prompt (system + history + query + retrieved context) is larger.

```python
# orchestrator_agent.py — same as existing
ORCHESTRATOR_HISTORY_WINDOW = 10   # last 10 messages (5 turns)

# domain_agent.py — shorter window
DOMAIN_HISTORY_WINDOW = 6          # last 6 messages (3 turns)

# Usage in orchestrator
orchestrator_history = session.messages[-ORCHESTRATOR_HISTORY_WINDOW:]

# Usage in each domain agent
domain_history = session.messages[-DOMAIN_HISTORY_WINDOW:]
```

Both windows are applied *before* query rewriting and *before* answer generation —
same as lines 35-38 in the existing project.

**File**: `new-rag-2026/core/constants.py` (window sizes as named constants)

---

## Technique 4 — Multi-Turn Query Rewriting

**Source**: `llm_service.py:181-198`

### What the existing project does

```python
# llm_service.py:181-198
async def rewrite_query(self, history: list[SessionMessage], question: str) -> str:
    if not history:
        return question   # turn 1: skip rewrite

    messages = [
        *[{"role": m.role, "content": m.content} for m in history[-6:]],
        {"role": "user", "content": (
            f"Câu hỏi gốc: {question}\n\n"
            "Viết lại câu hỏi thành một câu hỏi độc lập, đầy đủ ngữ cảnh, "
            "không cần đọc lịch sử trước đó để hiểu. "
            "Chỉ trả về câu hỏi đã viết lại, không giải thích."
        )}
    ]
    try:
        response = await self._call_llm(messages, temperature=0.0)
        return response.strip()
    except Exception:
        return question   # fallback: original message
```

`temperature=0.0` for deterministic rewrites. Last 6 messages used (not the full window).
Falls back to original message on any error.

### Disposition: **Carry over** + **Adapt** for multi-agent routing

The Vietnamese prompt is copied verbatim. The adaptation is *where* rewriting happens:
in the existing project, rewriting happens inside the retrieval service. In PLAN_V2,
rewriting happens in the orchestrator *before* routing, so all domain agents receive
the same rewritten query. This prevents inconsistent disambiguation per agent.

#### Adapted flow

```python
# orchestrator_agent.py

async def handle(self, session: SessionState, message: str) -> str:
    history = session.messages[-ORCHESTRATOR_HISTORY_WINDOW:]

    # Step 1: rewrite — same prompt as existing project
    rewritten = await self.llm.rewrite_query(history[-6:], message)

    # Step 2: classify domains (new — see Technique 5)
    query_type, domains = await self.llm.classify(rewritten)

    # Step 3: dispatch to domain agents with the rewritten query
    agents = [self.domain_agents[d] for d in domains]

    if len(agents) == 1:
        reply = await agents[0].answer(
            query=rewritten,
            history=session.messages[-DOMAIN_HISTORY_WINDOW:],
            query_type=query_type,
        )
    else:
        # Parallel dispatch — all agents get the same rewritten query
        replies = await asyncio.gather(*[
            a.answer(
                query=rewritten,
                history=session.messages[-DOMAIN_HISTORY_WINDOW:],
                query_type=query_type,
            )
            for a in agents
        ])
        reply = await self.llm.synthesize(rewritten, replies)

    return reply
```

**Why centralized rewriting matters**: if each domain agent rewrote independently,
agent A might resolve "họ" (they) to one entity and agent B to another, causing
the synthesized reply to mix referents. One rewrite, one canonical query.

**File**: `new-rag-2026/services/llm_service.py` (rewrite method copied from existing)
**File**: `new-rag-2026/agents/orchestrator_agent.py` (rewrite called here, not in retrieval)

---

## Technique 5 — Query Classification

**Source**: `llm_service.py:167-179`

### What the existing project does

Binary classification — one LLM call, JSON output:

```python
# llm_service.py:167-179
# Prompt (translated): "Classify this query. LOCAL = specific entity question.
#                       GLOBAL = broad/comparative. Reply only with JSON."
# Response schema: {"query_type": "LOCAL" | "GLOBAL"}
# Fallback: "LOCAL" on parse error
```

### Disposition: **Upgrade** — binary → two-step multi-domain

PLAN_V2 classifies in two steps, both in the orchestrator:

#### Step 1: LOCAL vs GLOBAL (identical to existing)

```python
# Prompt (Vietnamese, same as existing project)
CLASSIFY_TYPE_PROMPT = """
Phân loại câu hỏi sau:
- LOCAL: câu hỏi về một thực thể cụ thể, quy tắc, chính sách, hoặc người
- GLOBAL: câu hỏi tổng quan, so sánh, hoặc xu hướng

Câu hỏi: {query}

Trả lời chỉ bằng JSON: {{"query_type": "LOCAL" | "GLOBAL"}}
"""
# temperature=0.0, fallback="LOCAL"
```

#### Step 2: Domain classification (new — LOCAL queries only)

```python
CLASSIFY_DOMAIN_PROMPT = """
Câu hỏi sau thuộc về những lĩnh vực nào trong hệ thống?
Lĩnh vực có thể: {available_domains}

Câu hỏi: {query}

Trả lời chỉ bằng JSON: {{"domains": ["domain1", "domain2"]}}
Chỉ liệt kê các lĩnh vực thực sự liên quan. Tối thiểu 1, tối đa 3.
"""
# temperature=0.0
# fallback: ["general"]
```

GLOBAL queries bypass domain classification and go to a single "global" agent
that runs community summary retrieval.

#### Combined classifier method

```python
# llm_service.py
async def classify(self, query: str) -> tuple[str, list[str]]:
    query_type = await self._classify_type(query)   # "LOCAL" | "GLOBAL"
    if query_type == "GLOBAL":
        return "GLOBAL", ["global"]
    domains = await self._classify_domains(query)    # ["hr", "policy", ...]
    return "LOCAL", domains
```

**File**: `new-rag-2026/services/llm_service.py`

---

## Technique 6 — Two-Stage Retrieval with Type-Aware Entity Seeding

**Source**: `graph_rag_service.py:79-140`

### What the existing project does

Three-stage pipeline per query:

1. **Vector search** → overfetch `rerank_candidate_pool` chunks
2. **Entity augmentation**: seed entities from matched chunks → fetch linked chunks
   - Specific entity types (`QUY_TAC`, `CHINH_SACH`) → `min_entity_hits=1`
   - Generic entity types (`VAI_TRO`, `PHONG_BAN`) → `min_entity_hits=2`
3. **Cohere cross-encoder rerank** → top `max_local_chunks` (optional)
4. Seed entities re-anchored POST-rerank (winning chunks → winning entities)

### Disposition: **Adapt** for Microsoft GraphRAG schema + **Upgrade** with `LearnedFact` injection

The retrieval *logic* is identical. The *schema* changes because Microsoft GraphRAG
builds the graph with its own node/relationship types instead of the project's custom Cypher.

#### Schema mapping

| Existing (custom graph) | PLAN_V2 (Microsoft GraphRAG) |
|---|---|
| `Chunk` node | `TextUnit` node |
| `Entity` node | `Entity` node (same name, different properties) |
| Custom vector index on chunks | Vector index on `TextUnit.embedding` |
| `HAS_ENTITY` relationship | `MENTIONS` relationship |
| Custom Cypher traversal | Cypher using MS GraphRAG schema |

#### Adapted retrieval (per domain agent)

```python
# domain_agent.py

async def retrieve(
    self,
    query: str,
    query_type: str,
    domain: str,
) -> tuple[list[TextUnit], list[Entity], list[Triple]]:

    if query_type == "GLOBAL":
        # Community summary retrieval — different path, not shown here
        return await self._retrieve_global(query)

    # Stage 1: vector search on TextUnit nodes (replaces custom vector_search_chunks)
    candidate_units = await self.neo4j.vector_search_text_units(
        query_embedding=await self.llm.embed(query),
        domain_filter=domain,
        limit=self.config.rerank_candidate_pool,
    )

    # Stage 2: entity augmentation via MENTIONS relationships (same logic, new schema)
    seed_entities = self._extract_seed_entities(candidate_units)
    augmented_units = await self._augment_with_entity_neighbors(
        units=candidate_units,
        seed_entities=seed_entities,
    )

    # Type-aware thresholds — carried over exactly from existing project
    filtered_entities = self._apply_entity_type_thresholds(seed_entities)
    # QUY_TAC / CHINH_SACH → min_entity_hits=1
    # VAI_TRO / PHONG_BAN   → min_entity_hits=2

    # Stage 3: optional Cohere rerank (same as existing — carry over)
    if self.config.enable_rerank:
        augmented_units = await self.reranker.rerank(query, augmented_units)
        augmented_units = augmented_units[:self.config.max_local_chunks]

    # Re-anchor seed entities to winning chunks (same as existing)
    final_entities = self._reanchor_seed_entities(augmented_units)

    # NEW: append LearnedFact nodes at lower confidence weight
    learned_facts = await self.neo4j.search_learned_facts(
        query_embedding=await self.llm.embed(query),
        domain=domain,
        limit=5,
    )

    return augmented_units, final_entities, learned_facts
```

The `LearnedFact` injection (from `PLAN_LEARNING.md`) is appended *after* reranking
so it does not interfere with chunk scoring. Facts are passed to the LLM with a
lower-confidence prefix: `"[Learned context, confidence lower]: {fact.content}"`.

**File**: `new-rag-2026/agents/domain_agent.py`
**File**: `new-rag-2026/services/neo4j_service.py` (Cypher adapted for MS GraphRAG schema)

---

## Technique 7 — Seed-Entity Triple Filtering

**Source**: `graph_rag_service.py:158-169`

### What the existing project does

```python
# graph_rag_service.py:158-169
# Only include triples where BOTH source AND target are seed entities
# from matched chunks. 2-hop neighbors generate unrelated triples
# that cause the LLM to hallucinate non-existent rules.

def filter_triples(
    triples: list[Triple],
    seed_entity_ids: set[str],
) -> list[Triple]:
    return [
        t for t in triples
        if t.source_id in seed_entity_ids and t.target_id in seed_entity_ids
    ]
```

### Disposition: **Carry over exactly**

This is a proven quality guard. The reasoning — 2-hop noise causes hallucination —
applies identically to Microsoft GraphRAG's entity graph. The filter logic is copied
verbatim. Entity IDs may use a different property name in the MS GraphRAG schema
(`id` vs a custom field), but the filter predicate is identical.

```python
# new-rag-2026/agents/domain_agent.py
# Copied from graph_rag_service.py:158-169

def _filter_triples(
    self,
    triples: list[Triple],
    seed_entity_ids: set[str],
) -> list[Triple]:
    return [
        t for t in triples
        if t.source_id in seed_entity_ids and t.target_id in seed_entity_ids
    ]
```

Do not relax this filter. The only acceptable change is adapting the entity ID
field name to match the MS GraphRAG `Entity` node schema.

**File**: `new-rag-2026/agents/domain_agent.py`

---

## Technique 8 — Answer Verification

**Source**: `llm_service.py:200-222`

### What the existing project does

```python
# llm_service.py:200-222
# Controlled by ENABLE_ANSWER_VERIFICATION env var
# Context truncated to 4000 chars (cost control)
# JSON output: {is_grounded: bool, confidence: 1-5, issues: []}
# If is_grounded=false OR confidence < 3 → return FALLBACK_ANSWER (Vietnamese)

FALLBACK_ANSWER = (
    "Xin lỗi, tôi không tìm thấy thông tin đáng tin cậy để trả lời câu hỏi này. "
    "Vui lòng liên hệ bộ phận liên quan để được hỗ trợ."
)
```

### Disposition: **Adapt** — two-level verification for multi-agent

In the existing project, one verification call gates the final reply.
In PLAN_V2, verification happens at two levels:

#### Level 1: Domain agent verification (new)

Each domain agent verifies its own reply before returning it to the orchestrator.
This catches domain-specific hallucinations before they reach synthesis.

```python
# domain_agent.py

DOMAIN_VERIFY_PROMPT = """
Kiểm tra xem câu trả lời có dựa trên ngữ cảnh được cung cấp không.

Ngữ cảnh (tối đa 4000 ký tự):
{context}

Câu trả lời:
{answer}

Lĩnh vực: {domain}

Trả lời chỉ bằng JSON:
{{
  "is_grounded": true | false,
  "confidence": 1-5,
  "issues": ["..."],
  "domain": "{domain}"
}}
"""

async def answer(self, query: str, history: list, query_type: str) -> DomainReply:
    context, entities, facts = await self.retrieve(query, query_type, self.domain)
    raw_reply = await self.llm.generate(query, context, history)

    if self.config.enable_answer_verification:
        verification = await self.llm.verify(
            context=context[:4000],    # same truncation as existing
            answer=raw_reply,
            domain=self.domain,
        )
        if not verification.is_grounded or verification.confidence < 3:
            raw_reply = FALLBACK_ANSWER
            verification.confidence = 0

    return DomainReply(
        domain=self.domain,
        reply=raw_reply,
        confidence=verification.confidence if self.config.enable_answer_verification else 5,
        context_units=context,
    )
```

#### Level 2: Orchestrator verification (same as existing, applied to synthesized reply)

```python
# orchestrator_agent.py

synthesized = await self.llm.synthesize(rewritten, domain_replies)

if self.config.enable_answer_verification:
    final_verification = await self.llm.verify(
        context=self._merge_contexts(domain_replies)[:4000],
        answer=synthesized,
        domain="orchestrator",
    )
    if not final_verification.is_grounded or final_verification.confidence < 3:
        synthesized = FALLBACK_ANSWER
```

**JSON schema** (both levels — `domain` field is new):

```json
{
  "is_grounded": true,
  "confidence": 4,
  "issues": [],
  "domain": "hr"
}
```

`ENABLE_ANSWER_VERIFICATION` env var still controls both levels — one flag, consistent behaviour.
`FALLBACK_ANSWER` Vietnamese string is copied verbatim from the existing project.

**File**: `new-rag-2026/services/llm_service.py` (verify method)
**File**: `new-rag-2026/agents/domain_agent.py` (level 1)
**File**: `new-rag-2026/agents/orchestrator_agent.py` (level 2)

---

## Technique 9 — Token Logging

**Source**: `services/token_log_service.py`

### What the existing project does

Every LLM call logs to SQLite:

```python
# Columns: provider, model, call_type, prompt_tokens, completion_tokens, created_at
```

Used for cost tracking and debugging latency spikes.

### Disposition: **Upgrade** — add domain attribution + async

```python
# new-rag-2026/services/token_log_service.py

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS token_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT,
    provider         TEXT NOT NULL,
    model            TEXT NOT NULL,
    call_type        TEXT NOT NULL,
    domain           TEXT,          -- NEW: which domain agent made this call
    prompt_tokens    INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    created_at       TEXT NOT NULL
)
"""

class TokenLogService:
    def __init__(self, db_path: str):
        self._db_path = db_path

    async def log(
        self,
        session_id: str,
        provider: str,
        model: str,
        call_type: str,
        prompt_tokens: int,
        completion_tokens: int,
        domain: str | None = None,   # NEW
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO token_log
                   (session_id, provider, model, call_type, domain,
                    prompt_tokens, completion_tokens, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, provider, model, call_type, domain,
                 prompt_tokens, completion_tokens,
                 datetime.utcnow().isoformat()),
            )
            await db.commit()
```

**Why `domain` matters**: broad "general" domain queries cost significantly more than
targeted domain queries. The `domain` column makes it possible to identify expensive
domains per session and tune prompt lengths or routing rules accordingly.

`call_type` values in PLAN_V2 (extends existing set):

| call_type | Description |
|---|---|
| `rewrite` | Orchestrator query rewrite |
| `classify_type` | LOCAL/GLOBAL classification |
| `classify_domain` | Domain classification |
| `domain_generate` | Domain agent answer generation |
| `domain_verify` | Domain agent verification |
| `synthesize` | Orchestrator synthesis |
| `orchestrator_verify` | Orchestrator verification |
| `embed` | Embedding call |
| `learn_extract` | LearningService fact extraction (see PLAN_LEARNING) |

**File**: `new-rag-2026/services/token_log_service.py`
**Storage**: SQLite with `aiosqlite` (same DB engine as existing, async driver)

---

## Technique 10 — Structured Logging with structlog

**Source**: All services in existing project

### What the existing project does

```python
import structlog
logger = structlog.get_logger()

# Example events (existing):
logger.info("query_classified", query_type="LOCAL")
logger.info("retrieval_query_rewritten", original=q, rewritten=r)
logger.info("sessions_evicted", count=N)
logger.info("rerank_complete", input_chunks=N, output_chunks=M)
```

JSON-compatible output, key-value structured events.

### Disposition: **Carry over** + **Enrich** with multi-agent events

`structlog` configuration is copied from the existing project. New log events added for
multi-agent operations:

```python
# orchestrator_agent.py
logger.info("orchestrator_classified",
    query_type=query_type,
    domains=domains,
    rewritten_query_length=len(rewritten),
)

logger.info("agent_dispatched",
    domain=domain,
    rewritten_query=rewritten[:120],   # truncated for log safety
)

# domain_agent.py
logger.info("agent_completed",
    domain=domain,
    reply_length=len(reply),
    verification_confidence=confidence,
    is_grounded=is_grounded,
)

# orchestrator_agent.py (after synthesis)
logger.info("synthesis_completed",
    domain_count=len(domains),
    final_confidence=final_verification.confidence,
)

# session_service.py (on expiry + learning trigger)
logger.info("session_learned",
    session_id=session_id,
    message_count=session.message_count,
    # facts_count and gaps_count logged by LearningService itself
)
```

Existing events (`query_classified`, `retrieval_query_rewritten`, `sessions_evicted`,
`rerank_complete`) are retained with the same key names for log pipeline compatibility.

**File**: All service and agent files in `new-rag-2026/`

---

## Section 11 — What's New in PLAN_V2 (No Existing Equivalent)

These capabilities are net-new and do not come from `graphrag-assistant`:

### 1. Per-domain rerank

In the existing project, one rerank call gates all chunks for one query.
In PLAN_V2, each domain agent reranks its own candidate pool independently.
The orchestrator receives pre-ranked context per domain rather than a flat chunk list.
This matters because Cohere's cross-encoder scores are relative — mixing chunks from
different domains into one pool would disadvantage domain-specific terminology.

### 2. Domain agent token attribution

`call_type` + `domain` on every token log row means cost is attributable per domain
per session. The existing project has no domain concept, so all calls are attributed
to a single retrieval pipeline.

### 3. Session-level learning loop

Described in `PLAN_LEARNING.md`. No equivalent in `graphrag-assistant`.
Triggered by session expiry with `message_count >= 4`.
Produces `LearnedFact` nodes in Neo4j and `KnowledgeGap` records in SQLite.

### 4. Siliconflow as third LLM provider

The existing project supports OpenAI and Anthropic.
PLAN_V2 adds Siliconflow for cost-sensitive calls (embeddings, classification, verification)
while keeping a higher-capability model for generation and synthesis.
The `TokenLogService.provider` column captures which provider served each call.

---

## Section 12 — Implementation Checklist

| # | Technique | File in new-rag-2026 | Status |
|---|---|---|---|
| 1 | Session state model | `models/session.py` | Adapted from existing |
| 2 | Async session store | `services/session_service.py` | Adapted from existing |
| 3 | History windowing (orchestrator: 10, domain: 6) | `core/constants.py` | Carry over + minor upgrade |
| 4 | Multi-turn query rewrite | `services/llm_service.py`, `agents/orchestrator_agent.py` | Carry over (prompt), adapted (location) |
| 5 | Two-step classification | `services/llm_service.py` | Upgraded from binary |
| 6 | Two-stage retrieval + LearnedFact injection | `agents/domain_agent.py`, `services/neo4j_service.py` | Adapted (MS GraphRAG schema) + upgraded |
| 7 | Seed-entity triple filter | `agents/domain_agent.py` | Carry over exactly |
| 8 | Two-level answer verification | `services/llm_service.py`, `agents/domain_agent.py`, `agents/orchestrator_agent.py` | Adapted (two-level) |
| 9 | Token logging + domain attribution | `services/token_log_service.py` | Upgraded |
| 10 | structlog + multi-agent events | All service/agent files | Carry over + enriched |
| 11a | Per-domain rerank | `agents/domain_agent.py` | New code |
| 11b | Domain token attribution | `services/token_log_service.py` | New code |
| 11c | Session learning loop | See `PLAN_LEARNING.md` | New code |
| 11d | Siliconflow provider | `services/llm_service.py` | New code |

---

*End of PLAN_SESSION_TECHNIQUES.md*
