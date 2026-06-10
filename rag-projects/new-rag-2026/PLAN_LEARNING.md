# Implementation Plan: Per-Session Learning Loop

> **Project**: `new-rag-2026`
> **Depends on**: `PLAN_V2.md` (multi-agent, Neo4j, GraphRAG, Vietnamese prompts, multi-LLM)
> **Date**: 2026-06-07
> **Purpose**: Add a continuous learning loop that extracts new knowledge from chat sessions and writes it back to Neo4j — making the knowledge graph richer with every conversation without triggering a full re-index.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Learning Extraction LLM Prompt](#2-learning-extraction-llm-prompt)
3. [`learning_service.py` Design](#3-learning_servicepy-design)
4. [Neo4j Schema Additions](#4-neo4j-schema-additions)
5. [Modified Retrieval — Blending Learned Facts with Indexed Chunks](#5-modified-retrieval--blending-learned-facts-with-indexed-chunks)
6. [Knowledge Gap Tracking](#6-knowledge-gap-tracking)
7. [New API Endpoints](#7-new-api-endpoints)
8. [Frontend Additions](#8-frontend-additions)
9. [Privacy and Quality Guardrails](#9-privacy-and-quality-guardrails)
10. [Implementation Order](#10-implementation-order)

---

## 1. Overview

### What Session Learning Is

After each chat session ends — or periodically during a long session — the system analyzes the full conversation history to extract knowledge not already in the graph. Extracted knowledge is written back to Neo4j as new nodes. Future sessions can immediately retrieve this knowledge through the same vector search path that retrieves `TextUnit` nodes from the indexed corpus.

This closes a loop that standard RAG systems leave open: knowledge that users state, correct, or confirm during conversation is normally discarded when the session ends. Here it becomes permanent.

### Why It Matters

- **No full re-index required.** Adding a document via `POST /admin/ingest` + `POST /admin/index` takes minutes and costs many LLM calls. Session learning is incremental — one lightweight LLM call per session, writing at most a handful of new nodes.
- **User-generated corrections propagate.** If a policy was updated last week but the documents haven't been re-indexed yet, a user who states the correction in one session makes it available to all future sessions immediately.
- **Knowledge gap visibility.** Questions the system cannot answer today become `KnowledgeGap` nodes that admins can see and address by uploading missing documents.
- **Positive reinforcement.** Answers that users confirm as correct increase the confidence of the underlying `TextUnit` nodes, gradually surfacing the most-trusted content.

### Four Learning Types

| Type | Trigger pattern | Action |
|---|---|---|
| **New fact** | User states a fact not in the documents | Create `LearnedFact` node, link to `Entity` nodes |
| **Correction** | User corrects an assistant answer | Create correcting `LearnedFact`, mark original `TextUnit` as `stale=true` |
| **Knowledge gap** | Assistant returns a fallback / "I don't know" answer | Create `KnowledgeGap` node |
| **Positive reinforcement** | User explicitly confirms an answer is correct | Increment `confidence` on `TextUnit` nodes used in that answer |

### Feedback Loop Diagram

```
User chat session
       │
       ▼
OrchestratorAgent answers questions
       │
       │ (session ends or session.finalize() called)
       ▼
learning_service.extract_session_learnings(session)
       │   (one LLM call, Gemini/GPT-4 class model)
       ▼
SessionLearnings {
  learned_facts,       ─────────────────────────────┐
  corrections,         ──────────────────────────┐  │
  knowledge_gaps,      ───────────────────────┐  │  │
  positive_reinforcements                     │  │  │
}                                             │  │  │
       │                                      │  │  │
       ▼                                      ▼  ▼  ▼
learning_service.persist_learnings()
       │
       ├── MERGE (:LearnedFact) nodes + embed
       ├── MERGE (:KnowledgeGap) nodes
       ├── SET (:TextUnit).stale = true        ← corrections
       └── SET (:TextUnit).confidence += 0.1  ← positive reinforcement
       │
       ▼
Neo4j (graph grows)
       │
       ▼  (next session)
graphrag_service.py LocalSearch
  → fetches TextUnit + LearnedFact nodes
  → blends by confidence score
  → richer answer
```

---

## 2. Learning Extraction LLM Prompt

### Why This Needs a Capable Model

The extraction task requires multi-step reasoning: identifying speakers, distinguishing assertions from questions, detecting implicit corrections ("thực ra là..." without the user saying "bạn sai rồi"), and assigning confidence based on assertion strength. Haiku-class or small models (≤7B) produce too many false positives and hallucinated entity names. Use Gemini 2.0 Flash (default), GPT-4o, or DeepSeek-V3. Do **not** route this to a cost-optimized 1.5 Flash or mini model.

The `LEARNING_LLM_MODEL` env var (see Section 9) allows a separate, more powerful model for extraction while keeping the chat layer cheaper.

### Prompt: `prompts/learning_extraction_prompt.py`

```python
# backend/app/prompts/learning_extraction_prompt.py

LEARNING_EXTRACTION_PROMPT = '''Bạn là một hệ thống trích xuất tri thức chuyên nghiệp. Nhiệm vụ của bạn là phân tích một lịch sử hội thoại và trích xuất các tri thức mới mà NGƯỜI DÙNG cung cấp — không phải những gì trợ lý đã nói.

## Quy tắc phân tích

1. **Chỉ trích xuất từ lượt nói của NGƯỜI DÙNG** (role: "user"). Bỏ qua hoàn toàn lượt nói của trợ lý (role: "assistant").
2. **Sự kiện mới** là những khẳng định người dùng đưa ra như sự thật, không phải câu hỏi.
3. **Sửa chữa** xảy ra khi người dùng phủ nhận hoặc chỉnh sửa câu trả lời của trợ lý.
   - Dấu hiệu: "thực ra là...", "nhưng thực tế...", "cập nhật rồi...", "không đúng...", "sai rồi...", "hiện tại là...", "mới nhất là...", "đã thay đổi thành..."
4. **Lỗ hổng tri thức** xảy ra khi trợ lý trả lời rằng không có thông tin (ví dụ: "tôi không có thông tin về...", "tài liệu không đề cập...", "tôi không biết...").
5. **Xác nhận tích cực** xảy ra khi người dùng nói rõ câu trả lời là đúng.
   - Dấu hiệu: "đúng rồi", "chính xác", "đúng vậy", "phải rồi", "yes", "correct", "đúng", "vâng đúng"

## Thang điểm tin cậy (confidence)

- **0.9–1.0**: Người dùng khẳng định mạnh mẽ với số liệu cụ thể ("chính sách X đã được cập nhật lên Y vào tháng Z")
- **0.7–0.89**: Người dùng khẳng định không có số liệu cụ thể ("chính sách đó đã thay đổi rồi")
- **0.5–0.69**: Người dùng nói có vẻ đúng nhưng không chắc ("hình như là...", "tôi nghĩ là...")
- **< 0.5**: Người dùng đặt câu hỏi giả định hoặc suy đoán — KHÔNG trích xuất làm sự kiện

## Định dạng đầu ra

Trả về CHÍNH XÁC một JSON object theo schema sau, không có text thêm:

```json
{
  "learned_facts": [
    {
      "text": "<phát biểu sự thật bằng tiếng Việt, ngắn gọn, đầy đủ>",
      "source": "user",
      "entities": ["<tên thực thể 1>", "<tên thực thể 2>"],
      "confidence": 0.85,
      "fact_type": "new_fact"
    }
  ],
  "corrections": [
    {
      "correction_text": "<nội dung sửa chữa bằng tiếng Việt>",
      "corrects_assistant_statement": "<câu trả lời sai của trợ lý được sửa>",
      "entities": ["<tên thực thể>"],
      "confidence": 0.9
    }
  ],
  "knowledge_gaps": [
    {
      "question": "<câu hỏi người dùng mà trợ lý không trả lời được>",
      "domain_hint": "<hr|benefits|it|finance|compliance|procedures|general>"
    }
  ],
  "positive_reinforcements": [
    {
      "confirmed_statement": "<nội dung người dùng xác nhận là đúng>",
      "context": "<câu trả lời trợ lý được xác nhận>"
    }
  ]
}
```

Nếu không có gì để trích xuất trong một mục, trả về mảng rỗng [].

---

## Ví dụ 1: Sự kiện mới + Sửa chữa

**Hội thoại:**
```
User: Chính sách thai sản của công ty là bao nhiêu tháng?
Assistant: Theo tài liệu hiện tại, chính sách thai sản là 4 tháng.
User: Thực ra là chính sách đó đã được cập nhật lên 6 tháng vào tháng 3 năm 2026 rồi.
Assistant: Cảm ơn bạn đã thông báo.
```

**Kết quả mong đợi:**
```json
{
  "learned_facts": [
    {
      "text": "Chính sách thai sản đã được cập nhật lên 6 tháng kể từ tháng 3 năm 2026.",
      "source": "user",
      "entities": ["Chính sách thai sản"],
      "confidence": 0.92,
      "fact_type": "correction_fact"
    }
  ],
  "corrections": [
    {
      "correction_text": "Chính sách thai sản hiện tại là 6 tháng (không phải 4 tháng), cập nhật tháng 3 năm 2026.",
      "corrects_assistant_statement": "chính sách thai sản là 4 tháng",
      "entities": ["Chính sách thai sản"],
      "confidence": 0.92
    }
  ],
  "knowledge_gaps": [],
  "positive_reinforcements": []
}
```

---

## Ví dụ 2: Lỗ hổng tri thức + Xác nhận tích cực

**Hội thoại:**
```
User: Quy trình xin nghỉ phép bệnh khẩn cấp ngoài giờ hành chính là gì?
Assistant: Tôi không có thông tin về quy trình xin nghỉ phép bệnh khẩn cấp ngoài giờ hành chính trong tài liệu hiện tại.
User: Nhân viên cần gọi trực tiếp cho quản lý và báo qua email trong vòng 2 giờ.
Assistant: Cảm ơn thông tin. Theo bạn cung cấp, nhân viên cần gọi trực tiếp cho quản lý và gửi email trong vòng 2 giờ khi nghỉ khẩn cấp ngoài giờ.
User: Đúng rồi, đó là quy trình chuẩn.
```

**Kết quả mong đợi:**
```json
{
  "learned_facts": [
    {
      "text": "Khi xin nghỉ phép bệnh khẩn cấp ngoài giờ hành chính, nhân viên phải gọi trực tiếp cho quản lý và báo cáo qua email trong vòng 2 giờ.",
      "source": "user",
      "entities": ["Quy trình nghỉ phép bệnh khẩn cấp", "Quản lý"],
      "confidence": 0.95,
      "fact_type": "new_fact"
    }
  ],
  "corrections": [],
  "knowledge_gaps": [
    {
      "question": "Quy trình xin nghỉ phép bệnh khẩn cấp ngoài giờ hành chính là gì?",
      "domain_hint": "hr"
    }
  ],
  "positive_reinforcements": [
    {
      "confirmed_statement": "nhân viên phải gọi trực tiếp cho quản lý và gửi email trong vòng 2 giờ",
      "context": "Theo bạn cung cấp, nhân viên cần gọi trực tiếp cho quản lý và gửi email trong vòng 2 giờ khi nghỉ khẩn cấp ngoài giờ."
    }
  ]
}
```

---

## Ví dụ 3: Không có gì để học

**Hội thoại:**
```
User: Chính sách bảo mật mật khẩu là gì?
Assistant: Mật khẩu phải có ít nhất 12 ký tự, bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt. Mật khẩu phải được đổi mỗi 90 ngày.
User: Ok cảm ơn.
```

**Kết quả mong đợi:**
```json
{
  "learned_facts": [],
  "corrections": [],
  "knowledge_gaps": [],
  "positive_reinforcements": []
}
```

---

## Hội thoại cần phân tích:

{conversation_history}

## Kết quả JSON:
'''
```

### Calling the Prompt

The conversation history is formatted as a numbered transcript before injection:

```python
def _format_conversation(messages: list[dict]) -> str:
    """Format session messages as a readable transcript for the extraction prompt."""
    lines = []
    for i, msg in enumerate(messages, 1):
        role_vi = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"[{i}] {role_vi}: {msg['content']}")
    return "\n".join(lines)
```

---

## 3. `learning_service.py` Design

### File: `backend/app/services/learning_service.py`

```python
# backend/app/services/learning_service.py

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.learning import (
    KnowledgeGap,
    LearnedFact,
    SessionLearnings,
)
from app.prompts.learning_extraction_prompt import (
    LEARNING_EXTRACTION_PROMPT,
    _format_conversation,
)
from app.services.llm_service import create_llm_service
from app.services.neo4j_store import Neo4jStore

logger = logging.getLogger(__name__)

# Minimum confidence to persist a learned fact to Neo4j.
# Facts below this threshold are logged but not written.
CONFIDENCE_THRESHOLD = float(os.environ.get("LEARNING_CONFIDENCE_THRESHOLD", "0.7"))

# Minimum number of messages in a session to attempt learning extraction.
# A 1-turn session (2 messages) has almost nothing to learn from.
MIN_MESSAGES_TO_LEARN = int(os.environ.get("LEARNING_MIN_MESSAGES", "4"))

# If true, learned facts are created with is_reviewed=false and will not
# surface in retrieval until an admin approves them.
REQUIRE_FACT_REVIEW = os.environ.get("REQUIRE_FACT_REVIEW", "false").lower() == "true"


class LearningService:
    """
    Extracts new knowledge from completed chat sessions and persists it to Neo4j.

    Called by:
    - session_service._cleanup_expired() for automatic TTL-triggered learning
    - POST /api/v1/session/{id}/finalize for manual triggering
    """

    def __init__(self, neo4j: Neo4jStore) -> None:
        self._neo4j = neo4j
        # Use a separate, potentially more powerful model for extraction.
        # Defaults to LLM_PROVIDER if LEARNING_LLM_PROVIDER is not set.
        learning_provider = os.environ.get("LEARNING_LLM_PROVIDER")
        self._llm = create_llm_service(learning_provider)

    # ──────────────────────────────────────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────────────────────────────────────

    async def process_session(self, session_id: str, messages: list[dict]) -> SessionLearnings:
        """
        Full learning pipeline for one session.
        Safe to call as an asyncio background task — never raises, logs errors.

        Args:
            session_id: The session UUID.
            messages: List of {"role": "user"|"assistant", "content": str} dicts.

        Returns:
            SessionLearnings (also persisted to Neo4j as a side effect).
        """
        if len(messages) < MIN_MESSAGES_TO_LEARN:
            logger.debug(
                "Session %s has %d messages — below threshold, skipping learning.",
                session_id, len(messages),
            )
            return SessionLearnings(
                session_id=session_id,
                learned_facts=[],
                corrections=[],
                knowledge_gaps=[],
                positive_reinforcements=[],
            )

        try:
            learnings = await self.extract_session_learnings(session_id, messages)
            await self.persist_learnings(learnings)
            logger.info(
                "Session %s learning complete: %d facts, %d corrections, %d gaps, %d reinforcements.",
                session_id,
                len(learnings.learned_facts),
                len(learnings.corrections),
                len(learnings.knowledge_gaps),
                len(learnings.positive_reinforcements),
            )
            return learnings
        except Exception:
            logger.exception("Learning extraction failed for session %s — continuing.", session_id)
            return SessionLearnings(
                session_id=session_id,
                learned_facts=[],
                corrections=[],
                knowledge_gaps=[],
                positive_reinforcements=[],
            )

    async def extract_session_learnings(
        self, session_id: str, messages: list[dict]
    ) -> SessionLearnings:
        """
        Call the LLM with the extraction prompt and parse the JSON response.
        Uses structured output (response_format=json_object) when the provider
        supports it, otherwise relies on prompt-level JSON instruction.
        """
        conversation_text = _format_conversation(messages)
        prompt = LEARNING_EXTRACTION_PROMPT.format(
            conversation_history=conversation_text
        )

        # Use temperature=0 — extraction is deterministic classification, not creative.
        raw = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=3000,
        )

        parsed = self._parse_llm_response(raw)

        now = datetime.now(timezone.utc)

        learned_facts = []
        for item in parsed.get("learned_facts", []):
            confidence = float(item.get("confidence", 0.0))
            if confidence < CONFIDENCE_THRESHOLD:
                logger.debug("Skipping fact with confidence %.2f: %s", confidence, item.get("text"))
                continue
            learned_facts.append(
                LearnedFact(
                    id=str(uuid.uuid4()),
                    text=item["text"],
                    source=item.get("source", "user"),
                    entities=item.get("entities", []),
                    confidence=confidence,
                    session_id=session_id,
                    created_at=now,
                    is_reviewed=not REQUIRE_FACT_REVIEW,
                )
            )

        corrections = parsed.get("corrections", [])

        knowledge_gaps = []
        for item in parsed.get("knowledge_gaps", []):
            knowledge_gaps.append(
                KnowledgeGap(
                    id=str(uuid.uuid4()),
                    question=item["question"],
                    session_id=session_id,
                    timestamp=now,
                    domain_hint=item.get("domain_hint", "general"),
                    resolved=False,
                )
            )

        positive_reinforcements = [
            pr.get("confirmed_statement", "")
            for pr in parsed.get("positive_reinforcements", [])
            if pr.get("confirmed_statement")
        ]

        return SessionLearnings(
            session_id=session_id,
            learned_facts=learned_facts,
            corrections=corrections,
            knowledge_gaps=knowledge_gaps,
            positive_reinforcements=positive_reinforcements,
        )

    async def persist_learnings(self, learnings: SessionLearnings) -> None:
        """
        Write all extracted knowledge to Neo4j.
        Uses MERGE to avoid creating duplicates if called more than once.
        """
        tasks = []

        # 1. Write LearnedFact nodes and their Entity/Session links
        for fact in learnings.learned_facts:
            tasks.append(self._persist_learned_fact(fact))

        # 2. Write KnowledgeGap nodes
        for gap in learnings.knowledge_gaps:
            tasks.append(self._persist_knowledge_gap(gap))

        # 3. Apply corrections — mark old TextUnits as stale
        for correction in learnings.corrections:
            tasks.append(self._apply_correction(correction, learnings.session_id))

        # 4. Apply positive reinforcement — boost confidence on TextUnit nodes
        if learnings.positive_reinforcements:
            tasks.append(
                self._apply_positive_reinforcement(
                    learnings.positive_reinforcements,
                    learnings.session_id,
                )
            )

        if tasks:
            await asyncio.gather(*tasks)

    async def mark_knowledge_gap(self, question: str, session_id: str, domain_hint: str = "general") -> str:
        """
        Directly create a KnowledgeGap node. Called by domain agents when
        they detect a fallback answer at response time (before session ends).
        Returns the new gap's ID.
        """
        gap = KnowledgeGap(
            id=str(uuid.uuid4()),
            question=question,
            session_id=session_id,
            timestamp=datetime.now(timezone.utc),
            domain_hint=domain_hint,
            resolved=False,
        )
        await self._persist_knowledge_gap(gap)
        return gap.id

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _parse_llm_response(self, raw: str) -> dict[str, Any]:
        """
        Parse the LLM's JSON response. Strips markdown code fences if present.
        Falls back to empty structure on parse error.
        """
        text = raw.strip()
        # Strip ```json ... ``` wrappers that some models add despite instructions
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse learning extraction JSON. Raw response: %s", raw[:500])
            return {
                "learned_facts": [],
                "corrections": [],
                "knowledge_gaps": [],
                "positive_reinforcements": [],
            }

    async def _persist_learned_fact(self, fact: LearnedFact) -> None:
        """
        MERGE a LearnedFact node and its relationships into Neo4j.
        Embeds the fact text and stores the embedding on the node.
        """
        # Embed the fact text
        try:
            embeddings = await self._llm.embed([fact.text])
            embedding = embeddings[0]
        except Exception:
            logger.warning("Embedding failed for fact %s — storing without embedding.", fact.id)
            embedding = None

        await self._neo4j.run_write(
            """
            MERGE (f:LearnedFact {id: $id})
            SET f.text = $text,
                f.source = $source,
                f.confidence = $confidence,
                f.session_id = $session_id,
                f.created_at = $created_at,
                f.is_reviewed = $is_reviewed,
                f.embedding = $embedding
            """,
            id=fact.id,
            text=fact.text,
            source=fact.source,
            confidence=fact.confidence,
            session_id=fact.session_id,
            created_at=fact.created_at.isoformat(),
            is_reviewed=fact.is_reviewed,
            embedding=embedding,
        )

        # Link to session
        await self._neo4j.run_write(
            """
            MATCH (f:LearnedFact {id: $fact_id})
            MERGE (s:Session {id: $session_id})
            MERGE (f)-[:DERIVED_FROM_SESSION]->(s)
            """,
            fact_id=fact.id,
            session_id=fact.session_id,
        )

        # Link to entity nodes that already exist in the graph
        for entity_name in fact.entities:
            await self._neo4j.run_write(
                """
                MATCH (f:LearnedFact {id: $fact_id})
                OPTIONAL MATCH (e:Entity)
                  WHERE toLower(e.name) = toLower($entity_name)
                FOREACH (_ IN CASE WHEN e IS NOT NULL THEN [1] ELSE [] END |
                  MERGE (f)-[:MENTIONS]->(e)
                )
                """,
                fact_id=fact.id,
                entity_name=entity_name,
            )

    async def _persist_knowledge_gap(self, gap: KnowledgeGap) -> None:
        """MERGE a KnowledgeGap node."""
        await self._neo4j.run_write(
            """
            MERGE (g:KnowledgeGap {id: $id})
            SET g.question = $question,
                g.session_id = $session_id,
                g.timestamp = $timestamp,
                g.domain_hint = $domain_hint,
                g.resolved = $resolved
            """,
            id=gap.id,
            question=gap.question,
            session_id=gap.session_id,
            timestamp=gap.timestamp.isoformat(),
            domain_hint=gap.domain_hint,
            resolved=gap.resolved,
        )

    async def _apply_correction(self, correction: dict, session_id: str) -> None:
        """
        For each correction:
        1. Create a LearnedFact with the corrected text.
        2. Find TextUnit nodes whose text closely matches the incorrect statement
           and mark them stale.

        The stale match uses a simple substring heuristic — exact deduplication
        is the job of the re-indexing pipeline, not the learning loop.
        """
        corrected_text = correction.get("correction_text", "")
        incorrect_stmt = correction.get("corrects_assistant_statement", "")

        if not corrected_text:
            return

        # Create a LearnedFact for the correction
        fact = LearnedFact(
            id=str(uuid.uuid4()),
            text=corrected_text,
            source="user",
            entities=correction.get("entities", []),
            confidence=float(correction.get("confidence", 0.8)),
            session_id=session_id,
            created_at=datetime.now(timezone.utc),
            is_reviewed=not REQUIRE_FACT_REVIEW,
        )
        await self._persist_learned_fact(fact)

        # Mark matching TextUnit nodes as stale (best-effort, won't fail the pipeline)
        if incorrect_stmt:
            # Extract key phrase: first 80 chars, avoid matching too broadly
            key_phrase = incorrect_stmt.strip()[:80]
            try:
                await self._neo4j.run_write(
                    """
                    MATCH (t:TextUnit)
                    WHERE toLower(t.text) CONTAINS toLower($key_phrase)
                    SET t.stale = true
                    WITH t
                    MATCH (f:LearnedFact {id: $fact_id})
                    MERGE (f)-[:CORRECTS]->(t)
                    MERGE (t)-[:SUPERSEDED_BY]->(f)
                    """,
                    key_phrase=key_phrase,
                    fact_id=fact.id,
                )
            except Exception:
                logger.warning(
                    "Could not mark TextUnit as stale for correction: %s", key_phrase[:60]
                )

    async def _apply_positive_reinforcement(
        self,
        confirmed_statements: list[str],
        session_id: str,
    ) -> None:
        """
        For each confirmed statement, find TextUnit nodes whose text
        contains a key phrase and increment their confidence score by 0.05.
        Confidence is capped at 1.0.
        """
        for stmt in confirmed_statements:
            key_phrase = stmt.strip()[:80]
            if not key_phrase:
                continue
            try:
                await self._neo4j.run_write(
                    """
                    MATCH (t:TextUnit)
                    WHERE toLower(t.text) CONTAINS toLower($key_phrase)
                      AND (t.stale IS NULL OR t.stale = false)
                    SET t.confidence = CASE
                        WHEN t.confidence IS NULL THEN 1.05
                        WHEN t.confidence + 0.05 > 1.0 THEN 1.0
                        ELSE t.confidence + 0.05
                    END
                    """,
                    key_phrase=key_phrase,
                )
            except Exception:
                logger.warning("Positive reinforcement failed for statement: %s", key_phrase[:60])
```

### Pydantic Models: `backend/app/models/learning.py`

```python
# backend/app/models/learning.py

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LearnedFact(BaseModel):
    id: str
    text: str                        # the learned statement in Vietnamese
    source: Literal["user", "inferred"] = "user"
    entities: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    session_id: str
    created_at: datetime
    is_reviewed: bool = True         # False when REQUIRE_FACT_REVIEW=true


class KnowledgeGap(BaseModel):
    id: str
    question: str
    session_id: str
    timestamp: datetime
    domain_hint: str = "general"
    resolved: bool = False


class SessionLearnings(BaseModel):
    session_id: str
    learned_facts: list[LearnedFact] = Field(default_factory=list)
    corrections: list[dict] = Field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = Field(default_factory=list)
    positive_reinforcements: list[str] = Field(default_factory=list)


# ── API response models ──────────────────────────────────────────────────────

class LearnedFactResponse(BaseModel):
    id: str
    text: str
    confidence: float
    session_id: str
    created_at: datetime
    is_reviewed: bool
    entity_names: list[str] = Field(default_factory=list)


class KnowledgeGapResponse(BaseModel):
    id: str
    question: str
    session_id: str
    timestamp: datetime
    domain_hint: str
    resolved: bool


class LearningStatsResponse(BaseModel):
    total_learned_facts: int
    total_knowledge_gaps: int
    unresolved_gaps: int
    facts_pending_review: int
```

### Adding `run_write` to `Neo4jStore`

The `LearningService` calls `neo4j.run_write(query, **params)`. Add this method to `Neo4jStore` in `neo4j_store.py`:

```python
# Add to Neo4jStore in backend/app/services/neo4j_store.py

async def run_write(self, query: str, **params) -> None:
    """Execute a write Cypher query. Parameters passed as keyword args."""
    async with self._driver.session() as session:
        await session.run(query, **params)

async def run_read(self, query: str, **params) -> list[dict]:
    """Execute a read Cypher query. Returns list of row dicts."""
    async with self._driver.session() as session:
        result = await session.run(query, **params)
        return [dict(r) async for r in result]
```

### Integration into `session_service.py`

Add background learning extraction to the TTL cleanup loop and the session deletion path:

```python
# In backend/app/services/session_service.py

import asyncio
from app.services.learning_service import LearningService

# Injected at startup (see main.py lifespan)
_learning_service: LearningService | None = None

def set_learning_service(svc: LearningService) -> None:
    global _learning_service
    _learning_service = svc


async def _cleanup_expired() -> None:
    """Called by the TTL background loop in main.py."""
    now = datetime.now(timezone.utc)
    expired = [
        (sid, session)
        for sid, session in _sessions.items()
        if (now - session.last_active).total_seconds() > settings.SESSION_TTL_MINUTES * 60
    ]
    for session_id, session in expired:
        # Fire-and-forget learning extraction for sessions with enough messages.
        # Must NOT block the cleanup loop.
        if _learning_service and len(session.messages) >= 4:
            asyncio.create_task(
                _learning_service.process_session(session_id, session.messages)
            )
        del _sessions[session_id]
        logger.info("Session %s expired and cleaned up.", session_id)


async def delete_session(session_id: str) -> None:
    """Called by DELETE /api/v1/session/{id}."""
    session = _sessions.get(session_id)
    if session and _learning_service and len(session.messages) >= 4:
        asyncio.create_task(
            _learning_service.process_session(session_id, session.messages)
        )
    _sessions.pop(session_id, None)
```

---

## 4. Neo4j Schema Additions

### New Node Types

| Label | Properties | Description |
|---|---|---|
| `LearnedFact` | `id`, `text`, `confidence`, `session_id`, `created_at`, `is_reviewed`, `embedding` | A factual statement extracted from a user conversation |
| `KnowledgeGap` | `id`, `question`, `session_id`, `timestamp`, `domain_hint`, `resolved` | A question the assistant could not answer |
| `Session` | `id` | Lightweight session node (created by MERGE, used for linking only) |

### New Relationship Types

| Type | Pattern | Description |
|---|---|---|
| `DERIVED_FROM_SESSION` | `(LearnedFact)-[:DERIVED_FROM_SESSION]->(Session)` | Provenance — which session produced this fact |
| `MENTIONS` | `(LearnedFact)-[:MENTIONS]->(Entity)` | Same relationship used by `TextUnit`; learned facts mention entities |
| `CORRECTS` | `(LearnedFact)-[:CORRECTS]->(TextUnit)` | This fact supersedes an indexed text unit |
| `SUPERSEDED_BY` | `(TextUnit)-[:SUPERSEDED_BY]->(LearnedFact)` | Inverse of `CORRECTS`; used to filter stale units at query time |

### Cypher: Constraints and Indexes

Run these after the existing schema creation from PLAN_V2.md Section 8:

```cypher
-- Constraints
CREATE CONSTRAINT learned_fact_id IF NOT EXISTS
  FOR (f:LearnedFact) REQUIRE f.id IS UNIQUE;

CREATE CONSTRAINT knowledge_gap_id IF NOT EXISTS
  FOR (g:KnowledgeGap) REQUIRE g.id IS UNIQUE;

CREATE CONSTRAINT session_node_id IF NOT EXISTS
  FOR (s:Session) REQUIRE s.id IS UNIQUE;

-- Property indexes
CREATE INDEX learned_fact_session IF NOT EXISTS
  FOR (f:LearnedFact) ON (f.session_id);

CREATE INDEX learned_fact_confidence IF NOT EXISTS
  FOR (f:LearnedFact) ON (f.confidence);

CREATE INDEX learned_fact_reviewed IF NOT EXISTS
  FOR (f:LearnedFact) ON (f.is_reviewed);

CREATE INDEX knowledge_gap_resolved IF NOT EXISTS
  FOR (g:KnowledgeGap) ON (g.resolved);

CREATE INDEX knowledge_gap_domain IF NOT EXISTS
  FOR (g:KnowledgeGap) ON (g.domain_hint);

-- TextUnit additions (run once, idempotent)
-- Add stale and confidence properties with defaults if not present
MATCH (t:TextUnit)
WHERE t.stale IS NULL
SET t.stale = false;

MATCH (t:TextUnit)
WHERE t.confidence IS NULL
SET t.confidence = 1.0;

-- Vector index for LearnedFact (same dimensionality as Entity — use EMBEDDING_DIM env)
-- Replace 768 with your EMBEDDING_DIM value
CREATE VECTOR INDEX learned_fact_embedding IF NOT EXISTS
FOR (f:LearnedFact) ON (f.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
}};
```

### How `LearnedFact` Mirrors `TextUnit` in the Query Layer

Both `TextUnit` and `LearnedFact` are retrievable via vector search. They share:
- An `embedding` property (same dimensionality, same model)
- A `MENTIONS` relationship to `Entity` nodes
- A `text`/`text` property holding the actual content

The retrieval layer (Section 5) treats them uniformly: embed the query, run two parallel vector searches, merge and rank the results before building the LLM context.

---

## 5. Modified Retrieval — Blending Learned Facts with Indexed Chunks

### Goal

When a user asks a question, the context sent to the domain agent should include both:
- High-confidence `TextUnit` nodes from the indexed corpus
- Relevant `LearnedFact` nodes from prior sessions

Learned facts appear below indexed chunks unless their confidence exceeds the indexed chunk's confidence, or the indexed chunk is marked stale.

### Changes to `Neo4jStore`

Add two new methods:

```python
# Add to Neo4jStore in backend/app/services/neo4j_store.py

async def search_learned_facts(
    self,
    query_embedding: list[float],
    top_k: int = 5,
    min_confidence: float = 0.7,
) -> list[dict[str, Any]]:
    """
    Vector search over LearnedFact nodes.
    Only returns facts that are reviewed (or review not required) and
    meet the minimum confidence threshold.
    """
    async with self._driver.session() as session:
        result = await session.run(
            """
            CALL db.index.vector.queryNodes(
                'learned_fact_embedding', $k, $embedding
            ) YIELD node, score
            WHERE node.confidence >= $min_confidence
              AND (node.is_reviewed = true)
            RETURN node.id AS id,
                   node.text AS text,
                   node.confidence AS confidence,
                   node.session_id AS session_id,
                   node.created_at AS created_at,
                   score
            ORDER BY (node.confidence * score) DESC
            """,
            k=top_k,
            embedding=query_embedding,
            min_confidence=min_confidence,
        )
        return [dict(r) async for r in result]

async def search_text_units(
    self,
    query_embedding: list[float],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """
    Direct vector search over TextUnit nodes, excluding stale units.
    Complements GraphRAG's LocalSearch by providing a simple fallback
    when the LocalSearch engine is not yet loaded.
    """
    async with self._driver.session() as session:
        result = await session.run(
            """
            CALL db.index.vector.queryNodes(
                'entity_embedding', $k, $embedding
            ) YIELD node, score
            MATCH (t:TextUnit)-[:MENTIONS]->(node)
            WHERE (t.stale IS NULL OR t.stale = false)
            RETURN DISTINCT t.id AS id,
                   t.text AS text,
                   COALESCE(t.confidence, 1.0) AS confidence,
                   score
            ORDER BY (COALESCE(t.confidence, 1.0) * score) DESC
            LIMIT $k
            """,
            k=top_k,
            embedding=query_embedding,
        )
        return [dict(r) async for r in result]
```

### Changes to `GraphRAGService`

Add `_augment_with_learned_facts()` and integrate into the `search()` method:

```python
# Modified search() in backend/app/services/graphrag_service.py

async def search(
    self,
    question: str,
    mode: SearchMode,
    query_embedding: list[float] | None = None,
) -> dict[str, Any]:
    """
    Run GraphRAG search and augment results with LearnedFact nodes.

    Args:
        question: The user query.
        mode: LOCAL or GLOBAL.
        query_embedding: Pre-computed embedding. If None, computed here.

    Returns:
        {reply, sources} where sources contains both TextUnit and LearnedFact entries.
    """
    # Run GraphRAG search (existing behaviour)
    engine = self._local_search if mode == SearchMode.LOCAL else self._global_search
    if engine is None:
        raise RuntimeError("GraphRAG not ready. Run indexing and import first.")
    graphrag_result = await engine.asearch(question)

    # Compute query embedding for learned-fact lookup
    if query_embedding is None:
        embeddings = await asyncio.to_thread(
            self._embedder().embed, [question]
        )
        query_embedding = embeddings[0] if embeddings else []

    # Augment with learned facts
    learned_facts = []
    if query_embedding:
        learned_facts = await self._neo4j.search_learned_facts(
            query_embedding, top_k=5
        )

    # Extract GraphRAG sources (TextUnit + CommunityReport)
    graphrag_sources = self._extract_sources(graphrag_result.context_data)

    # Merge: learned facts inserted after indexed chunks but before community reports
    merged_sources = _merge_sources(graphrag_sources, learned_facts)

    return {
        "reply": graphrag_result.response,
        "sources": merged_sources,
    }


def _merge_sources(
    graphrag_sources: list[dict],
    learned_facts: list[dict],
) -> list[dict]:
    """
    Merge GraphRAG TextUnit sources with LearnedFact results.

    Ordering rules:
    1. Non-stale TextUnit sources with confidence >= 0.9  (highest trust)
    2. LearnedFact sources with confidence >= 0.9         (user-confirmed, high trust)
    3. Non-stale TextUnit sources with confidence < 0.9   (normal indexed content)
    4. LearnedFact sources with confidence < 0.9          (lower confidence learned content)
    5. Community report sources                            (global context, always last)
    """
    text_units = [s for s in graphrag_sources if s.get("type") == "text_unit"]
    community_reports = [s for s in graphrag_sources if s.get("type") == "community_report"]

    # Annotate learned facts with a type marker
    for lf in learned_facts:
        lf["type"] = "learned_fact"

    high_conf_tu = [s for s in text_units if s.get("confidence", 1.0) >= 0.9]
    low_conf_tu = [s for s in text_units if s.get("confidence", 1.0) < 0.9]
    high_conf_lf = [s for s in learned_facts if s.get("confidence", 0.0) >= 0.9]
    low_conf_lf = [s for s in learned_facts if s.get("confidence", 0.0) < 0.9]

    return high_conf_tu + high_conf_lf + low_conf_tu + low_conf_lf + community_reports
```

### How Domain Agents Use the Blended Context

No changes required in domain agent code. The `context_chunks` list passed to `_build_user_message()` already contains both TextUnit and LearnedFact texts — agents consume them identically. Optionally, agents can inspect `source["type"] == "learned_fact"` to prefix learned content with a note like "*(Thông tin từ người dùng trước đây)*" for transparency.

---

## 6. Knowledge Gap Tracking

### Creation

Knowledge gaps are created in two ways:

**Automatic (post-session):** The `learning_service.extract_session_learnings()` LLM call identifies turns where the assistant said it had no information. These are written as `KnowledgeGap` nodes during `persist_learnings()`.

**Real-time (during session):** Domain agents can call `learning_service.mark_knowledge_gap()` directly when they detect a fallback answer pattern. Add this to `BaseDomainAgent.answer()`:

```python
# In base_agent.py — inside answer() after receiving the LLM reply

FALLBACK_PATTERNS_VI = [
    "tôi không có thông tin",
    "tài liệu không đề cập",
    "tôi không biết",
    "không tìm thấy thông tin",
    "nằm ngoài phạm vi tài liệu",
]

async def answer(self, question: str, ..., session_id: str | None = None) -> AgentResult:
    ...
    reply_lower = reply.lower()
    is_fallback = any(p in reply_lower for p in FALLBACK_PATTERNS_VI)

    if is_fallback and session_id and _learning_service:
        asyncio.create_task(
            _learning_service.mark_knowledge_gap(
                question=question,
                session_id=session_id,
                domain_hint=self.domain_key,
            )
        )
    ...
```

### Admin Visibility

Admins see knowledge gaps at `GET /api/v1/knowledge-gaps`. The response groups gaps by `domain_hint` so the admin can see which domains lack coverage.

### Resolution Flow

When an admin uploads a document covering a knowledge gap topic and re-indexes:

1. Upload via `POST /api/v1/admin/ingest`
2. Index via `POST /api/v1/admin/index` — this triggers `graphrag index` + `import_to_neo4j.py` + `graphrag_service.reload()`
3. Admin manually calls `DELETE /api/v1/knowledge-gaps/{id}` to mark the gap resolved, OR
4. (Optional enhancement) The system auto-resolves gaps after re-indexing: query the new `TextUnit` nodes and check if any of them cover the gap question using a quick embedding similarity check:

```python
# Optional: auto-resolve gaps after re-index
# In indexing_service.py, after graphrag_service.reload():

async def _auto_resolve_knowledge_gaps(neo4j: Neo4jStore, llm: BaseLLMService) -> None:
    """After re-index, check if newly added TextUnits resolve any open gaps."""
    gaps = await neo4j.run_read(
        "MATCH (g:KnowledgeGap {resolved: false}) RETURN g.id AS id, g.question AS question"
    )
    for gap in gaps:
        q_embedding = (await llm.embed([gap["question"]]))[0]
        results = await neo4j.search_text_units(q_embedding, top_k=3)
        # If any result has similarity > 0.85, consider the gap resolved
        if results and results[0].get("score", 0) > 0.85:
            await neo4j.run_write(
                "MATCH (g:KnowledgeGap {id: $id}) SET g.resolved = true",
                id=gap["id"],
            )
            logger.info("Auto-resolved KnowledgeGap %s", gap["id"])
```

---

## 7. New API Endpoints

All endpoints prefixed `/api/v1`. Add to `backend/app/routers/learning.py` and register in `main.py`.

### `POST /api/v1/session/{session_id}/finalize`

Manually trigger learning extraction for a session. Returns immediately; extraction runs as a background task.

**Request:** No body required.

**Response `202 Accepted`:**
```json
{
  "session_id": "uuid4",
  "message": "Learning extraction started in background.",
  "messages_in_session": 12
}
```

**Implementation:**
```python
@router.post("/session/{session_id}/finalize", status_code=202)
async def finalize_session(session_id: str):
    session = session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    asyncio.create_task(
        learning_service.process_session(session_id, session.messages)
    )
    return {
        "session_id": session_id,
        "message": "Learning extraction started in background.",
        "messages_in_session": len(session.messages),
    }
```

---

### `GET /api/v1/knowledge-gaps`

List all unresolved (or all) knowledge gaps.

**Query params:**
- `resolved: bool = false` — filter by resolution status
- `domain: str | null` — filter by `domain_hint`
- `limit: int = 50`
- `offset: int = 0`

**Response `200`:**
```json
{
  "total": 14,
  "items": [
    {
      "id": "uuid4",
      "question": "Quy trình xin nghỉ phép bệnh khẩn cấp ngoài giờ hành chính là gì?",
      "session_id": "uuid4",
      "timestamp": "2026-06-07T09:12:00Z",
      "domain_hint": "hr",
      "resolved": false
    }
  ]
}
```

**Cypher:**
```cypher
MATCH (g:KnowledgeGap)
WHERE g.resolved = $resolved
  AND ($domain IS NULL OR g.domain_hint = $domain)
RETURN g
ORDER BY g.timestamp DESC
SKIP $offset LIMIT $limit
```

---

### `DELETE /api/v1/knowledge-gaps/{gap_id}`

Mark a gap as resolved. Does not delete the node — keeps history.

**Response `200`:**
```json
{
  "id": "uuid4",
  "resolved": true,
  "message": "Knowledge gap marked as resolved."
}
```

---

### `GET /api/v1/learned-facts`

List all learned facts, paginated.

**Query params:**
- `session_id: str | null` — filter by session
- `min_confidence: float = 0.0`
- `is_reviewed: bool | null` — null means return all
- `limit: int = 50`
- `offset: int = 0`

**Response `200`:**
```json
{
  "total": 37,
  "items": [
    {
      "id": "uuid4",
      "text": "Chính sách thai sản đã được cập nhật lên 6 tháng kể từ tháng 3 năm 2026.",
      "confidence": 0.92,
      "session_id": "uuid4",
      "created_at": "2026-06-07T10:05:00Z",
      "is_reviewed": true,
      "entity_names": ["Chính sách thai sản"]
    }
  ]
}
```

**Cypher:**
```cypher
MATCH (f:LearnedFact)
WHERE f.confidence >= $min_confidence
  AND ($session_id IS NULL OR f.session_id = $session_id)
  AND ($is_reviewed IS NULL OR f.is_reviewed = $is_reviewed)
OPTIONAL MATCH (f)-[:MENTIONS]->(e:Entity)
RETURN f, collect(e.name) AS entity_names
ORDER BY f.created_at DESC
SKIP $offset LIMIT $limit
```

---

### `DELETE /api/v1/learned-facts/{fact_id}`

Remove a bad learned fact from Neo4j entirely (hard delete).

**Response `200`:**
```json
{
  "id": "uuid4",
  "deleted": true
}
```

**Cypher:**
```cypher
MATCH (f:LearnedFact {id: $id})
DETACH DELETE f
```

---

### `POST /api/v1/learned-facts/{fact_id}/approve`

Approve a fact pending review (only relevant when `REQUIRE_FACT_REVIEW=true`).

**Response `200`:**
```json
{
  "id": "uuid4",
  "is_reviewed": true
}
```

**Cypher:**
```cypher
MATCH (f:LearnedFact {id: $id})
SET f.is_reviewed = true
RETURN f
```

---

## 8. Frontend Additions

### Admin Panel: "Learned Facts" Tab

**Component:** `frontend/src/components/admin/LearnedFactsPanel.tsx`

Displays a table of `LearnedFact` nodes. Each row shows:
- Confidence badge (color-coded: green ≥ 0.9, yellow 0.7–0.89, gray pending review)
- Fact text (truncated to 120 chars, expandable)
- Session ID (linked to session trace if available)
- Created date
- Entity tags
- Actions: **Xóa** (delete) / **Duyệt** (approve, if `is_reviewed=false`)

Fetches from `GET /api/v1/learned-facts`. Supports filtering by minimum confidence and review status.

Vietnamese UI labels:
```
Tab title:        "Tri thức học được"
Column headers:   "Nội dung" | "Độ tin cậy" | "Thực thể" | "Phiên" | "Ngày tạo" | "Thao tác"
Empty state:      "Chưa có tri thức nào được học từ hội thoại."
Delete confirm:   "Bạn có chắc muốn xóa tri thức này không?"
Approve button:   "Duyệt"
Delete button:    "Xóa"
Filter label:     "Độ tin cậy tối thiểu:"
Review filter:    "Chờ duyệt" / "Đã duyệt" / "Tất cả"
```

---

### Admin Panel: "Knowledge Gaps" Tab

**Component:** `frontend/src/components/admin/KnowledgeGapsPanel.tsx`

Displays unresolved gaps grouped by domain. Each row shows:
- Question text
- Domain badge (color matches domain from PLAN_V2.md)
- Timestamp
- Actions: **Đánh dấu đã giải quyết** (mark resolved)

Vietnamese UI labels:
```
Tab title:          "Câu hỏi chưa có câu trả lời"
Column headers:     "Câu hỏi" | "Lĩnh vực" | "Thời gian" | "Thao tác"
Empty state:        "Không có câu hỏi nào chưa được trả lời. Hệ thống đang hoạt động tốt!"
Resolve button:     "Đánh dấu đã giải quyết"
Resolved badge:     "Đã giải quyết"
Domain filter:      "Lọc theo lĩnh vực:"
Show resolved:      "Hiển thị đã giải quyết"
```

---

### Session-End Banner

**Component:** `frontend/src/components/chat/LearningBanner.tsx`

Displayed briefly (5 seconds, then fades) when `POST /session/{id}/finalize` returns and the background task completes. The frontend polls `GET /api/v1/learned-facts?session_id={id}` once after session close to get the count.

```tsx
// Learning banner shown at session end
// Only shown if learned_count > 0

<div className="learning-banner">
  <span className="learning-icon">✨</span>
  <span>
    Học được {learnedCount} điều mới từ cuộc trò chuyện này.{" "}
    {knowledgeGapCount > 0 && (
      <span>Ghi nhận {knowledgeGapCount} câu hỏi chưa có câu trả lời.</span>
    )}
  </span>
</div>
```

Vietnamese strings:
```
"Học được {n} điều mới từ cuộc trò chuyện này."
"Ghi nhận {n} câu hỏi chưa có câu trả lời."
"Không có tri thức mới nào được học từ cuộc trò chuyện này."
```

---

## 9. Privacy and Quality Guardrails

### Guardrail 1: Review Gate (`REQUIRE_FACT_REVIEW`)

When `REQUIRE_FACT_REVIEW=true`, new `LearnedFact` nodes are created with `is_reviewed=false`. The retrieval query in `search_learned_facts()` filters on `node.is_reviewed = true`, so unreviewed facts are invisible to future sessions until an admin approves them via `POST /api/v1/learned-facts/{id}/approve`.

Default: `REQUIRE_FACT_REVIEW=false` (facts go live immediately). Enable for regulated environments where unverified user statements must not affect other users' answers.

### Guardrail 2: Confidence Threshold

Only facts with `confidence >= LEARNING_CONFIDENCE_THRESHOLD` (default `0.7`) are written to Neo4j at all. Facts below threshold are logged at DEBUG level and discarded. Set `LEARNING_CONFIDENCE_THRESHOLD=0.85` for stricter filtering.

### Guardrail 3: Correction Verification

Stale-marking of `TextUnit` nodes uses a best-effort substring match. A `TextUnit` is only marked stale if the key phrase from the incorrect assistant statement actually appears in its text. If no `TextUnit` is matched, the correction `LearnedFact` is still created (providing the corrected information) but no existing node is marked stale. This prevents false-positive staleness from vague corrections.

### Guardrail 4: Session-Level Bulk Delete

Admins can delete all learned facts from a specific session:

```cypher
MATCH (f:LearnedFact {session_id: $session_id})
DETACH DELETE f
```

Expose this via `DELETE /api/v1/learned-facts?session_id={id}` (add to the router). Useful when a session contained bad data or a test session that should not affect production.

### Guardrail 5: Model Quality

Use `LEARNING_LLM_PROVIDER` to override the extraction model independently of `LLM_PROVIDER`. Recommended: always use Gemini 2.0 Flash, GPT-4o, or DeepSeek-V3 for extraction — never Flash-Lite or Haiku.

```bash
# .env additions
LEARNING_LLM_PROVIDER=gemini          # overrides LLM_PROVIDER for extraction only
LEARNING_CONFIDENCE_THRESHOLD=0.7     # minimum confidence to persist a fact
LEARNING_MIN_MESSAGES=4               # minimum messages before attempting extraction
REQUIRE_FACT_REVIEW=false             # true = facts need admin approval before use
```

### Guardrail 6: Embedding Consistency

`LearnedFact` embeddings must use the same model as `TextUnit` and `Entity` embeddings (same provider, same model, same `EMBEDDING_DIM`). The `LearningService` uses `self._llm.embed()` which maps to the same embedding model configured for the agent layer. If you switch embedding models mid-project, you must re-embed all `LearnedFact` nodes (add a migration script alongside `import_to_neo4j.py`).

### Config Additions for `config.py`

```python
# Add to Settings in backend/app/config.py

LEARNING_LLM_PROVIDER: str = ""          # empty = use LLM_PROVIDER
LEARNING_CONFIDENCE_THRESHOLD: float = 0.7
LEARNING_MIN_MESSAGES: int = 4
REQUIRE_FACT_REVIEW: bool = False
```

---

## 10. Implementation Order

Work through these steps sequentially. Each step is independently testable before moving on.

**Step 1 — Pydantic models**
Create `backend/app/models/__init__.py` and `backend/app/models/learning.py` with `LearnedFact`, `KnowledgeGap`, `SessionLearnings`, and the three response models. No dependencies. Run `python -c "from app.models.learning import SessionLearnings; print('ok')"`.

**Step 2 — Neo4j schema additions**
Run the Cypher from Section 4 against the running Neo4j instance. Verify with:
```cypher
SHOW INDEXES YIELD name, labelsOrTypes, properties
WHERE name IN ['learned_fact_embedding', 'knowledge_gap_resolved', 'learned_fact_session']
```
Also run the `TextUnit` property backfill (`SET t.stale = false`, `SET t.confidence = 1.0`).

**Step 3 — `neo4j_store.py` additions**
Add `run_write()`, `run_read()`, `search_learned_facts()`, and `search_text_units()` to `Neo4jStore`. Unit test `search_learned_facts()` with an empty graph (should return `[]`).

**Step 4 — Learning extraction prompt**
Create `backend/app/prompts/learning_extraction_prompt.py`. Write a standalone test that calls the LLM with a hard-coded conversation and prints the parsed JSON. Verify all four extraction types work correctly against real conversation examples before wiring into the service.

**Step 5 — `learning_service.py`**
Implement `LearningService` with all methods. Test `extract_session_learnings()` in isolation first (mocked Neo4j). Then test `persist_learnings()` against Neo4j with a known fact, verify the node appears with:
```cypher
MATCH (f:LearnedFact) RETURN f.text, f.confidence ORDER BY f.created_at DESC LIMIT 5
```

**Step 6 — Config additions**
Add `LEARNING_LLM_PROVIDER`, `LEARNING_CONFIDENCE_THRESHOLD`, `LEARNING_MIN_MESSAGES`, and `REQUIRE_FACT_REVIEW` to `config.py`. Update `.env.example`.

**Step 7 — `session_service.py` integration**
Add `set_learning_service()`, the `_cleanup_expired()` changes, and the `delete_session()` changes. The background task creation must be wrapped in `try/except` to prevent cleanup loop crashes.

**Step 8 — `graphrag_service.py` modifications**
Add `query_embedding` parameter to `search()`. Add `_augment_with_learned_facts()` call and `_merge_sources()` function. Test that a `LearnedFact` node created in Step 5 now appears in search results for a relevant query.

**Step 9 — `BaseDomainAgent` real-time gap detection**
Add `FALLBACK_PATTERNS_VI` list and the real-time `mark_knowledge_gap()` task creation to `BaseDomainAgent.answer()`. Pass `session_id` through the agent call chain (add as optional parameter to `answer()` and thread it from `OrchestratorAgent.run()`).

**Step 10 — New router: `learning.py`**
Implement all 6 endpoints from Section 7. Register the router in `main.py`. Add `learning_service` to the lifespan startup block:
```python
# In main.py lifespan
learning_svc = LearningService(neo4j=neo4j_store)
session_service.set_learning_service(learning_svc)
```

**Step 11 — Frontend: Learned Facts panel**
Implement `LearnedFactsPanel.tsx`. Wire to the admin layout. Verify the panel loads and shows facts from test sessions.

**Step 12 — Frontend: Knowledge Gaps panel**
Implement `KnowledgeGapsPanel.tsx`. Wire resolve action to `DELETE /api/v1/knowledge-gaps/{id}`.

**Step 13 — Frontend: Session-end banner**
Implement `LearningBanner.tsx`. Trigger it in the chat component when the session is deleted or finalized. Use a 5-second auto-dismiss.

**Step 14 — End-to-end verification**
Run through this scenario:
1. Start a session.
2. Ask a question the system can answer — verify no gap is recorded.
3. Ask a question the system cannot answer — verify a `KnowledgeGap` node is created in Neo4j.
4. State a new fact ("Thực ra chính sách X đã thay đổi thành Y").
5. End the session (call `DELETE /session/{id}`).
6. Wait 3–5 seconds for background task to complete.
7. Query Neo4j: `MATCH (f:LearnedFact) RETURN f.text, f.confidence` — verify the fact is there.
8. Start a new session and ask a question related to the learned fact — verify it appears in the answer context.
9. Open admin panel → "Tri thức học được" — verify the fact appears in the table.
10. Open admin panel → "Câu hỏi chưa có câu trả lời" — verify the gap appears.
