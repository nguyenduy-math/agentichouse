# Implementation Plan V2: Multi-Agent Virtual Assistant with Microsoft GraphRAG + Neo4j

> **Project**: `new-rag-2026`
> **Supersedes**: `PLAN.md` (single-agent, Parquet/LanceDB storage)
> **Date**: 2026-06-07
> **Key additions over V1**: multi-agent orchestration, Neo4j graph/vector storage, Vietnamese prompts throughout, switchable LLM provider (Gemini / OpenAI / Siliconflow), LangChain integration for LLM abstraction and Neo4j vector store

---

## Table of Contents

1. [Overview](#1-overview)
2. [Microsoft GraphRAG + Neo4j Integration](#2-microsoft-graphrag--neo4j-integration)
3. [Chunking Strategy](#3-chunking-strategy)
4. [`settings.yaml` with Vietnamese Prompts](#4-settingsyaml-with-vietnamese-prompts)
5. [Vietnamese Prompt Templates](#5-vietnamese-prompt-templates)
6. [LangChain Integration](#6-langchain-integration)
7. [Multi-LLM Service Design (LangChain-backed)](#7-multi-llm-service-design-langchain-backed)
8. [Multi-Agent Design](#8-multi-agent-design)
9. [GraphRAG Query Integration](#9-graphrag-query-integration)
10. [Retrieval Quality Pipeline](#10-retrieval-quality-pipeline)
11. [LangSmith Observability](#11-langsmith-observability)
12. [Neo4j Schema](#12-neo4j-schema)
13. [API Endpoints](#13-api-endpoints)
14. [Environment Variables](#14-environment-variables)
15. [`requirements.txt`](#15-requirementstxt)
16. [`docker-compose.yml`](#16-docker-composeyml)
17. [Comparison Table](#17-comparison-table)
18. [Implementation Order](#18-implementation-order)

---

## 1. Overview

### What This Plan Builds

A production-ready multi-agent virtual assistant that combines:

- **Microsoft GraphRAG** (`graphrag>=2.0.0`) for knowledge graph construction and retrieval
- **Neo4j** as the graph and vector database, replacing ephemeral Parquet/LanceDB artifacts
- **Multi-agent architecture** with a single `OrchestratorAgent` routing to 7 domain specialist agents
- **Vietnamese prompts** for all system prompts, GraphRAG extraction templates, and answer generation
- **Multi-LLM support** switchable at runtime via `LLM_PROVIDER` env var (Gemini, OpenAI, Siliconflow)

### Why This Design

**Multi-agent over single-agent**: Domain specialist agents carry focused, domain-specific system prompts and document scopes. A question about IT security gets an agent that knows exactly what IT security means in this organization's context — not a generalist agent juggling seven domains at once. Cross-domain questions get parallel fan-out with synthesized answers rather than a single agent that has to context-switch mid-response.

**Neo4j over Parquet/LanceDB**: Parquet artifacts are a flat file cache — they enable GraphRAG's query engine but provide no persistent graph that backend services can query directly. Neo4j stores entities, relationships, communities, and text units as a live graph, enabling rich Cypher traversals (e.g., "find all IT policies connected to this compliance entity") that LanceDB vector search cannot express. Vector indexes on `Entity.embedding` and `Community.embedding` replace LanceDB for similarity search.

**Vietnamese prompts**: All system prompts, GraphRAG extraction templates, and answer synthesis prompts are written in Vietnamese. This improves extraction quality on Vietnamese-language documents and ensures the assistant's responses are natural Vietnamese rather than machine-translated English answers.

**Multi-LLM**: Different providers have different cost/quality tradeoffs. Gemini is the default (best Vietnamese quality, generous free tier for development). OpenAI is available for production deployments where consistency matters. Siliconflow (DeepSeek-V3, Qwen2.5-72B) is available for cost-sensitive or air-gapped deployments. Switching requires only changing one env var.

### Reference Projects

This plan draws patterns from two existing projects:

- **`lightrag-company-policy-assistant`**: Multi-agent orchestration pattern, 10 domain agents, Gemini LLM integration, Vietnamese system prompts
- **`graphrag-assistant`**: Custom GraphRAG + Neo4j integration, LOCAL/GLOBAL search patterns, Neo4j Cypher query design

### Project Directory Structure

```
new-rag-2026/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── schemas.py
│   │   ├── domains.py              # single source of truth for domain list
│   │   ├── agents/
│   │   │   ├── base_agent.py       # BaseDomainAgent ABC
│   │   │   ├── orchestrator.py     # OrchestratorAgent
│   │   │   ├── hr_agent.py
│   │   │   ├── benefits_agent.py
│   │   │   ├── it_agent.py
│   │   │   ├── finance_agent.py
│   │   │   ├── compliance_agent.py
│   │   │   ├── procedures_agent.py
│   │   │   └── general_agent.py
│   │   ├── services/
│   │   │   ├── graphrag_service.py # wraps graphrag LocalSearch + GlobalSearch
│   │   │   ├── indexing_service.py
│   │   │   ├── neo4j_store.py      # Neo4j driver + vector search
│   │   │   ├── llm_service.py      # BaseLLMService + 3 implementations
│   │   │   └── session_service.py
│   │   ├── prompts/
│   │   │   ├── system_prompts.py   # Vietnamese system prompts per domain
│   │   │   ├── extraction_prompts.py
│   │   │   ├── orchestrator_prompts.py
│   │   │   └── synthesis_prompts.py
│   │   └── routers/
│   │       ├── chat.py
│   │       ├── admin.py
│   │       ├── session.py
│   │       └── health.py
│   ├── graphrag_workspace/
│   │   ├── settings.yaml
│   │   ├── input/
│   │   ├── output/
│   │   └── prompts/                # Vietnamese extraction prompt templates
│   │       ├── entity_extraction.txt
│   │       ├── community_report.txt
│   │       └── summarize_descriptions.txt
│   ├── scripts/
│   │   ├── run_index.py
│   │   └── import_to_neo4j.py      # Parquet → Neo4j bulk import
│   ├── data/documents/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── components/
│       │   ├── chat/
│       │   ├── sources/
│       │   └── admin/
│       ├── hooks/
│       └── store/
└── docker-compose.yml
```

---

## 2. Microsoft GraphRAG + Neo4j Integration

GraphRAG 2.x provides two paths for Neo4j integration. Both are documented here. **Option B (hybrid) is the recommended default** because Neo4j native storage in GraphRAG 2.x is still evolving and may not be stable across minor releases.

### Option A — Native Neo4j Storage (preferred if stable)

GraphRAG 2.x introduced a `storage.type: neo4j` backend. When enabled, the indexer writes entities, relationships, communities, and text units directly to Neo4j nodes and relationships during the indexing run. No separate import step is needed.

**`settings.yaml` changes for Option A**:

```yaml
storage:
  type: neo4j
  url: ${NEO4J_URI}
  username: ${NEO4J_USER}
  password: ${NEO4J_PASSWORD}
  database: neo4j

vector_store:
  type: neo4j
  url: ${NEO4J_URI}
  username: ${NEO4J_USER}
  password: ${NEO4J_PASSWORD}
  database: neo4j
```

**Verification**: After `graphrag index`, open Neo4j Browser and run:
```cypher
MATCH (n) RETURN labels(n), count(n) ORDER BY count(n) DESC
```
You should see `Entity`, `Community`, `TextUnit`, `Document`, `Covariate` node types.

**Risk**: If `storage.type: neo4j` is not yet fully stable in your pinned `graphrag` version, the indexer may fall back to Parquet silently or error mid-run. Test with a small 2–3 document corpus before committing to Option A in production.

### Option B — Hybrid / Parquet + Import (safe fallback, recommended)

This is the safe default. GraphRAG indexing writes Parquet artifacts as in V1. A post-indexing script reads those Parquet files with pandas and bulk-imports them into Neo4j. The query layer then reads from Neo4j instead of LanceDB.

**Flow**:

```
graphrag index --root ./graphrag_workspace
      │
      ▼
output/artifacts/*.parquet  (intermediate, on disk)
      │
      ▼
scripts/import_to_neo4j.py  (pandas → Neo4j bulk import)
      │
      ├── CREATE (:Entity)  nodes with embedding property
      ├── CREATE (:Community) nodes with embedding property
      ├── CREATE (:TextUnit) nodes
      ├── CREATE (:Document) nodes
      ├── CREATE (:Entity)-[:RELATED_TO]->(:Entity)
      ├── CREATE (:Entity)-[:IN_COMMUNITY]->(:Community)
      └── CREATE (:TextUnit)-[:MENTIONS]->(:Entity)
      │
      ▼
Neo4j vector indexes created:
  entity_embedding  (Entity.embedding, 768-dim, cosine)
  community_embedding (Community.embedding, 768-dim, cosine)
```

**`scripts/import_to_neo4j.py`**:

```python
"""
Bulk-import GraphRAG Parquet artifacts into Neo4j.
Run after `graphrag index` completes.

Usage:
    python scripts/import_to_neo4j.py \
        --artifacts ./graphrag_workspace/output/artifacts \
        --uri bolt://localhost:7687 \
        --user neo4j \
        --password <password>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--artifacts", required=True)
    p.add_argument("--uri", default="bolt://localhost:7687")
    p.add_argument("--user", default="neo4j")
    p.add_argument("--password", required=True)
    return p.parse_args()


def _embedding_list(val) -> list[float] | None:
    """Parse embedding from parquet (may be list, np.ndarray, or JSON string)."""
    if val is None:
        return None
    if isinstance(val, str):
        return json.loads(val)
    try:
        return list(val)
    except TypeError:
        return None


def import_entities(tx, df: pd.DataFrame) -> None:
    records = []
    for _, row in df.iterrows():
        records.append({
            "id": str(row["id"]),
            "name": str(row.get("name", "")),
            "type": str(row.get("type", "")),
            "description": str(row.get("description", "")),
            "embedding": _embedding_list(row.get("description_embedding")),
        })
    tx.run(
        """
        UNWIND $records AS r
        MERGE (e:Entity {id: r.id})
        SET e.name = r.name,
            e.type = r.type,
            e.description = r.description,
            e.embedding = r.embedding
        """,
        records=records,
    )


def import_relationships(tx, df: pd.DataFrame) -> None:
    records = []
    for _, row in df.iterrows():
        records.append({
            "source": str(row["source"]),
            "target": str(row["target"]),
            "description": str(row.get("description", "")),
            "weight": float(row.get("weight", 1.0)),
        })
    tx.run(
        """
        UNWIND $records AS r
        MATCH (src:Entity {id: r.source})
        MATCH (tgt:Entity {id: r.target})
        MERGE (src)-[rel:RELATED_TO]->(tgt)
        SET rel.description = r.description,
            rel.weight = r.weight
        """,
        records=records,
    )


def import_communities(tx, df: pd.DataFrame, report_df: pd.DataFrame) -> None:
    # Merge community report text into community df
    if "community" in report_df.columns:
        report_df = report_df.rename(columns={"community": "id"})
    merged = df.merge(
        report_df[["id", "title", "summary", "full_content", "embedding"]],
        on="id", how="left"
    )
    records = []
    for _, row in merged.iterrows():
        records.append({
            "id": str(row["id"]),
            "level": int(row.get("level", 0)),
            "title": str(row.get("title", "")),
            "summary": str(row.get("summary", "")),
            "embedding": _embedding_list(row.get("embedding")),
        })
    tx.run(
        """
        UNWIND $records AS r
        MERGE (c:Community {id: r.id})
        SET c.level = r.level,
            c.title = r.title,
            c.summary = r.summary,
            c.embedding = r.embedding
        """,
        records=records,
    )


def import_community_membership(tx, entity_df: pd.DataFrame) -> None:
    """Link entities to their community (from community column in entity table)."""
    records = []
    for _, row in entity_df.iterrows():
        community = row.get("community")
        if community is not None and str(community) != "nan":
            records.append({"entity_id": str(row["id"]), "community_id": str(community)})
    tx.run(
        """
        UNWIND $records AS r
        MATCH (e:Entity {id: r.entity_id})
        MATCH (c:Community {id: r.community_id})
        MERGE (e)-[:IN_COMMUNITY]->(c)
        """,
        records=records,
    )


def import_text_units(tx, df: pd.DataFrame) -> None:
    records = []
    for _, row in df.iterrows():
        records.append({
            "id": str(row["id"]),
            "text": str(row.get("text", "")),
            "document_id": str(row.get("document_ids", [""])[0] if isinstance(row.get("document_ids"), list) else ""),
        })
    tx.run(
        """
        UNWIND $records AS r
        MERGE (t:TextUnit {id: r.id})
        SET t.text = r.text,
            t.document_id = r.document_id
        """,
        records=records,
    )


def import_text_unit_entity_links(tx, entity_df: pd.DataFrame) -> None:
    """Link text units to entities via MENTIONS."""
    records = []
    for _, row in entity_df.iterrows():
        for tu_id in (row.get("text_unit_ids") or []):
            records.append({"tu_id": str(tu_id), "entity_id": str(row["id"])})
    if not records:
        return
    tx.run(
        """
        UNWIND $records AS r
        MATCH (t:TextUnit {id: r.tu_id})
        MATCH (e:Entity {id: r.entity_id})
        MERGE (t)-[:MENTIONS]->(e)
        """,
        records=records,
    )


def create_vector_indexes(driver, dim: int = 768) -> None:
    with driver.session() as session:
        session.run(
            f"""
            CREATE VECTOR INDEX entity_embedding IF NOT EXISTS
            FOR (e:Entity) ON (e.embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {dim},
                `vector.similarity_function`: 'cosine'
            }}}}
            """
        )
        session.run(
            f"""
            CREATE VECTOR INDEX community_embedding IF NOT EXISTS
            FOR (c:Community) ON (c.embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {dim},
                `vector.similarity_function`: 'cosine'
            }}}}
            """
        )
    print(f"Vector indexes created (dim={dim}).")


def main() -> None:
    args = parse_args()
    artifacts = Path(args.artifacts)
    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))

    print("Reading Parquet artifacts...")
    entity_df = pd.read_parquet(artifacts / "create_final_entities.parquet")
    rel_df = pd.read_parquet(artifacts / "create_final_relationships.parquet")
    community_df = pd.read_parquet(artifacts / "create_final_communities.parquet")
    report_df = pd.read_parquet(artifacts / "create_final_community_reports.parquet")
    text_unit_df = pd.read_parquet(artifacts / "create_final_text_units.parquet")

    print(f"  Entities: {len(entity_df)}")
    print(f"  Relationships: {len(rel_df)}")
    print(f"  Communities: {len(community_df)}")
    print(f"  Text units: {len(text_unit_df)}")

    BATCH = 500
    with driver.session() as session:
        # Entities
        for i in range(0, len(entity_df), BATCH):
            session.execute_write(import_entities, entity_df.iloc[i:i+BATCH])
        print("Entities imported.")

        # Relationships
        for i in range(0, len(rel_df), BATCH):
            session.execute_write(import_relationships, rel_df.iloc[i:i+BATCH])
        print("Relationships imported.")

        # Communities + reports
        session.execute_write(import_communities, community_df, report_df)
        print("Communities imported.")

        # Entity → community membership
        session.execute_write(import_community_membership, entity_df)
        print("Community membership links created.")

        # Text units
        for i in range(0, len(text_unit_df), BATCH):
            session.execute_write(import_text_units, text_unit_df.iloc[i:i+BATCH])
        print("Text units imported.")

        # TextUnit → Entity MENTIONS
        session.execute_write(import_text_unit_entity_links, entity_df)
        print("MENTIONS links created.")

    create_vector_indexes(driver, dim=768)
    driver.close()
    print("Import complete.")


if __name__ == "__main__":
    main()
```

### Deciding Between Option A and Option B

| Criterion | Option A (Native Neo4j) | Option B (Hybrid) |
|---|---|---|
| Import step needed | No | Yes (`import_to_neo4j.py`) |
| GraphRAG 2.x stability | Uncertain | Stable |
| Query layer | Neo4j vector search | Neo4j vector search |
| Parquet artifacts kept | No (if native) | Yes (kept as backup) |
| Recommended for | Future (when API stabilizes) | **Now (default)** |

**Decision**: Use Option B. After `graphrag index` completes, call `import_to_neo4j.py`. The `IndexingService` triggers this automatically after the subprocess exits successfully.

---

## 3. Chunking Strategy

Chunking is one of the most impactful decisions in a GraphRAG pipeline. Microsoft GraphRAG calls chunks **text units** — they are the atomic units that get embedded, entity-extracted, and linked to the graph. Chunk size directly controls extraction quality, retrieval precision, and token costs.

The existing `graphrag-assistant` project (`utils/text_splitter.py`, `utils/document_parser.py`) contains several proven techniques that this project adopts and adapts.

---

### 3.1 Techniques from the existing project

#### Technique 1 — Structure-aware splitting (`split_by_article`)

The existing project uses a **three-tier splitting strategy** (`text_splitter.py:9-22`) that respects the natural structure of Vietnamese policy documents instead of blindly splitting at token boundaries:

```python
def split_by_article(text: str, max_chunk_size: int = 2800) -> list[str]:
    # Tier 1: Split at Vietnamese article boundaries ("Điều N.")
    if _DIEU.search(text):
        return _split_on_pattern(text, r"(?m)^(?=Điều \d+\.)", max_chunk_size)
    # Tier 2: Split at section markers ("=== SECTION ===")
    if _SECTION.search(text):
        return _split_on_pattern(text, r"(?m)^(?====)", max_chunk_size)
    # Tier 3 fallback: fixed-size sliding window with sentence-boundary snapping
    return split_text(text, max_chunk_size, max_chunk_size // 7)
```

**Why this matters**: Vietnamese legal and policy documents are structured around numbered articles (`Điều 1.`, `Điều 2.`, etc.). Splitting at `Điều` boundaries ensures each chunk contains exactly one article — a self-contained policy rule — rather than cutting mid-rule across two chunks. This dramatically improves entity extraction accuracy because the LLM receives a coherent, complete policy statement.

**Adopted for new project**: The `indexing_service.py` pre-processor runs this same tier logic before handing text to GraphRAG's chunker. When GraphRAG's chunker receives pre-split text (one article per "document"), its `size: 600` window never splits a single article in half.

#### Technique 2 — Sentence-boundary snapping in the fallback splitter

When fixed-size splitting is needed (no `Điều` pattern), the existing `split_text()` function (`text_splitter.py:46-74`) snaps chunk boundaries to the nearest sentence end:

```python
last_break = max(
    chunk.rfind(".\n"),   # Vietnamese sentence ending with newline
    chunk.rfind("\n\n"),  # paragraph break
    chunk.rfind(". "),    # inline sentence end
)
if last_break > chunk_size // 2:
    end = start + last_break + 1
    chunk = text[start:end]
```

**Why this matters**: Hard token cuts mid-sentence produce incomplete entities. Snapping to the nearest sentence boundary (only if it's past the halfway point of the chunk) keeps chunks semantically complete while staying within the size limit.

**Adopted for new project**: The pre-processor applies this same logic when no article structure is detected.

#### Technique 3 — Chunk size: 2800 chars with 400-char overlap

The existing project uses `chunk_size: 2800` (characters, not tokens) with `chunk_overlap: 400` — roughly equivalent to 600–700 tokens and 85-token overlap with Vietnamese text at ~4 chars/token.

```python
# config.py
chunk_size: int = 2800
chunk_overlap: int = 400
```

**Why 2800 chars**: This was tuned empirically for the Vietnamese policy document corpus. A single `Điều` article typically runs 400–2000 characters. The 2800-char ceiling handles even the longest articles (multi-paragraph rules with sub-clauses) without truncation.

**Translation to GraphRAG tokens**: `2800 chars ÷ 4 chars/token ≈ 700 tokens`. The new project uses `size: 700` in `settings.yaml` to match this.

#### Technique 4 — PDF parsing with dual-library fallback

The existing `document_parser.py:12-37` tries `pdfplumber` first and falls back to `pymupdf (fitz)`:

```python
def _parse_pdf(file_path: str) -> list[dict[str, Any]]:
    try:
        import pdfplumber  # better for text-heavy PDFs with complex layouts
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                ...
    except Exception:
        pass
    try:
        import fitz  # pymupdf fallback — more robust for scanned or protected PDFs
        doc = fitz.open(file_path)
        ...
```

**Why two libraries**: `pdfplumber` handles multi-column layouts and tables better; `pymupdf` is more robust for scanned PDFs and unusual encodings. The dual-fallback ensures near-100% extraction success across diverse document types.

**Adopted unchanged**: The new project's `indexing_service.py` uses the same dual-fallback pattern.

#### Technique 5 — DOCX table extraction

The existing parser extracts text from both paragraphs AND table cells (`document_parser.py:47-52`):

```python
for para in doc.paragraphs:
    if para.text.strip():
        all_text.append(para.text)
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            if cell.text.strip():
                all_text.append(cell.text)
```

**Why this matters**: HR policy documents often store benefit tables (leave entitlements, salary bands) as DOCX tables. Skipping tables means missing structured entity data (e.g., "Phép năm: 12 ngày — áp dụng cho nhân viên thử việc xong").

**Adopted unchanged**.

#### Technique 6 — NFC normalization on all extracted text

Every parser immediately normalizes text with `unicodedata.normalize("NFC", text)` (`document_parser.py:8-9`).

**Why this matters**: Vietnamese has two Unicode representations for the same character — precomposed (NFC) and decomposed (NFD). PDF extractors and Word documents often mix them, causing entity deduplication failures (two occurrences of the same word look different to the LLM tokenizer). NFC normalization ensures all Vietnamese diacritics are stored in precomposed form.

**Adopted unchanged**: applied immediately after any text extraction.

---

### 3.2 Adapted settings for Microsoft GraphRAG

Microsoft GraphRAG's chunker works in **tokens** (not characters). The pre-processing pipeline converts documents to clean plain text per-article before handing them to GraphRAG. Since each input "document" fed to GraphRAG is already one article (≤2800 chars ≈ 700 tokens), GraphRAG's chunker rarely needs to split further.

```yaml
# graphrag_workspace/settings.yaml
chunks:
  size: 700              # tokens — matches ~2800 chars from existing project
  overlap: 100           # ~400 chars equivalent; lower than existing because pre-splitting reduces need
  group_by_columns:
    - id
  encoding_model: cl100k_base
```

**Why lower overlap (100 vs 400 chars from existing)**: The existing project's 400-char overlap was designed for raw documents where mid-sentence cuts were common. With structure-aware pre-splitting (each input is one complete article), overlap mainly protects against the rare case where GraphRAG still splits a long article. 100-token overlap is sufficient.

---

### 3.3 Pre-processing pipeline (`indexing_service.py`)

The full pipeline before text reaches GraphRAG's `input/` directory:

```python
# backend/app/services/indexing_service.py — prepare_for_graphrag()

import unicodedata
import re
from pathlib import Path
from app.utils.document_parser import parse_document   # adopted from existing project
from app.utils.text_splitter import split_by_article   # adopted from existing project


def prepare_for_graphrag(file_path: Path, output_dir: Path) -> list[Path]:
    """
    Convert a PDF/DOCX/TXT to one or more plain-text files for GraphRAG input.
    Each output file is one article/section (≤ 2800 chars).
    Returns list of written .txt file paths.
    """
    pages = parse_document(str(file_path))              # dual-library PDF, DOCX tables, NFC normalization
    all_text = "\n\n".join(p["text"] for p in pages)

    # Split at Điều boundaries (or section markers, or fixed-size fallback)
    articles = split_by_article(all_text, max_chunk_size=2800)

    output_paths = []
    stem = file_path.stem
    for i, article_text in enumerate(articles):
        out = output_dir / f"{stem}_part{i:04d}.txt"
        out.write_text(article_text, encoding="utf-8")
        output_paths.append(out)

    return output_paths
```

**Output**: GraphRAG's `input/` directory receives many small `.txt` files, each containing one coherent article. GraphRAG's chunker treats each file as one document and creates 1–2 text units per file at `size: 700`.

---

### 3.4 Chunk size impact table

| Metric | Existing project (2800 chars) | New project GraphRAG (700 tokens) | Notes |
|---|---|---|---|
| Avg chunk size | ~2800 chars (~700 tokens) | ~700 tokens | Equivalent |
| Overlap | 400 chars (~100 tokens) | 100 tokens | Lower — pre-splitting reduces need |
| Split strategy | Structure-aware (Điều → section → fixed) | Structure-aware pre-split → GraphRAG fixed | Same logic, different layer |
| LLM calls per 100-page doc | ~300 (fewer, larger chunks) | ~400 (after article split) | Slightly more due to article granularity |
| Extraction quality | High (article-aligned) | **Higher** (article-aligned + MSFT GraphRAG extractor) | |
| Retrieval precision | High | **High** (one article per text unit = precise retrieval) | |

---

### 3.5 Per-domain considerations

The existing project uses a flat `DOC_TYPES` list (`indexing_service.py:24`): `["handbooks", "hr_policies", "conduct", "benefits", "procedures"]`. Each document type is processed identically with the same chunk size.

For the new project: use the same flat approach for v1. The article-aware splitter naturally adapts to each document type — HR policies have `Điều` structure, handbooks have `===` section structure, and procedures fall back to fixed-size. No per-domain chunk size configuration is needed.

**Advanced option** (post-v1): tag each `TextUnit` node in Neo4j with its `domain` property so domain agents can filter: `MATCH (t:TextUnit {domain: 'hr'})` — giving each agent a domain-scoped vector search index.

---

## 4. `settings.yaml` with Vietnamese Prompts

Full `settings.yaml` for Option B (Parquet output + custom Vietnamese prompts). Swap the `storage` block for Option A when ready.

```yaml
# graphrag_workspace/settings.yaml

# ─── LLM (indexing: entity extraction, community summarization) ───────────────
llm:
  api_key: ${GEMINI_API_KEY}
  type: openai_chat
  model: gemini-2.0-flash
  api_base: https://generativelanguage.googleapis.com/v1beta/openai/
  max_tokens: 4000
  temperature: 0
  request_timeout: 180.0
  max_retries: 10
  max_retry_wait: 10.0
  sleep_on_rate_limit_recommendation: true
  concurrent_requests: 4

# ─── Embeddings ───────────────────────────────────────────────────────────────
embeddings:
  llm:
    api_key: ${GEMINI_API_KEY}
    type: openai_embedding
    model: text-embedding-004
    api_base: https://generativelanguage.googleapis.com/v1beta/openai/
    max_retries: 10
    request_timeout: 60.0
    concurrent_requests: 8
  vector_store:
    # Option B: LanceDB (temporary; import_to_neo4j.py migrates to Neo4j)
    type: lancedb
    db_uri: output/lancedb
    container_name: default
    # Option A (uncomment when ready):
    # type: neo4j
    # url: ${NEO4J_URI}
    # username: ${NEO4J_USER}
    # password: ${NEO4J_PASSWORD}

# ─── Input ────────────────────────────────────────────────────────────────────
input:
  type: file
  file_type: text
  base_dir: input
  file_pattern: ".*\\.txt$"
  encoding: utf-8

# ─── Output ───────────────────────────────────────────────────────────────────
output:
  # Option B: file (Parquet)
  type: file
  base_dir: output
  # Option A (uncomment when ready):
  # type: neo4j
  # url: ${NEO4J_URI}
  # username: ${NEO4J_USER}
  # password: ${NEO4J_PASSWORD}

# ─── Chunking ─────────────────────────────────────────────────────────────────
chunks:
  size: 1200
  overlap: 100
  group_by_columns: [id]

# ─── Entity extraction — points to Vietnamese template ────────────────────────
entity_extraction:
  prompt: prompts/entity_extraction.txt
  entity_types:
    - tổ chức        # organization
    - người          # person
    - địa điểm       # location
    - sự kiện        # event
    - khái niệm      # concept
    - quy trình      # process
    - chính sách     # policy
  max_gleanings: 1

# ─── Community reports — points to Vietnamese template ────────────────────────
community_reports:
  prompt: prompts/community_report.txt
  max_length: 2000
  max_input_length: 8000

# ─── Summarize descriptions — points to Vietnamese template ───────────────────
summarize_descriptions:
  prompt: prompts/summarize_descriptions.txt
  max_length: 500

# ─── Claim extraction (disabled — expensive; enable for compliance domains) ───
claim_extraction:
  enabled: false

# ─── Local search context ─────────────────────────────────────────────────────
local_search:
  text_unit_prop: 0.5
  community_prop: 0.1
  conversation_history_max_turns: 5
  top_k_mapped_entities: 10
  top_k_relationships: 10
  max_tokens: 12000

# ─── Global search context ────────────────────────────────────────────────────
global_search:
  max_tokens: 12000
  data_max_tokens: 12000
  map_max_tokens: 1000
  reduce_max_tokens: 2000
  concurrency: 32

# ─── Reporting ────────────────────────────────────────────────────────────────
reporting:
  type: file
  base_dir: logs
```

**Notes**:
- `entity_types` uses Vietnamese labels. GraphRAG passes these directly into the extraction prompt, so the LLM sees Vietnamese type names when processing Vietnamese documents.
- `concurrent_requests: 4` is appropriate for Gemini free tier. Increase to 16–32 on paid tiers.
- The `prompts/` path is relative to `graphrag_workspace/`. Each prompt file is a Jinja2 template — see Section 4.

---

## 4. Vietnamese Prompt Templates

These files live in `graphrag_workspace/prompts/`. They replace GraphRAG's default English templates.

### `prompts/entity_extraction.txt`

```
-Mục tiêu-
Cho một đoạn văn bản và danh sách các loại thực thể, hãy xác định tất cả các thực thể thuộc các loại đó trong văn bản và tất cả các mối quan hệ giữa các thực thể đã xác định.

-Các bước thực hiện-
1. Xác định tất cả các thực thể. Với mỗi thực thể được xác định, hãy trích xuất thông tin sau:
   - entity_name: Tên của thực thể, viết hoa chữ cái đầu
   - entity_type: Một trong các loại sau: [{entity_types}]
   - entity_description: Mô tả toàn diện về các thuộc tính và hoạt động của thực thể
   Định dạng mỗi thực thể như sau:
   ("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>)

2. Từ các thực thể đã xác định ở bước 1, xác định tất cả các cặp thực thể (source_entity, target_entity) có mối quan hệ *rõ ràng* với nhau.
   Với mỗi cặp thực thể liên quan, trích xuất thông tin sau:
   - source_entity: Tên của thực thể nguồn, như đã xác định ở bước 1
   - target_entity: Tên của thực thể đích, như đã xác định ở bước 1
   - relationship_description: Giải thích tại sao bạn cho rằng thực thể nguồn và thực thể đích có mối quan hệ với nhau
   - relationship_strength: Điểm số nguyên từ 1 đến 10 thể hiện mức độ mạnh của mối quan hệ
   Định dạng mỗi mối quan hệ như sau:
   ("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_strength>)

3. Trả về kết quả đầu ra bằng tiếng Việt dưới dạng danh sách tất cả các thực thể và mối quan hệ đã xác định. Sử dụng **{record_delimiter}** làm dấu phân cách danh sách.

4. Khi hoàn thành, hãy xuất ra {completion_delimiter}

######################
-Ví dụ-
######################

Ví dụ 1:
Loại thực thể: [tổ chức, người, địa điểm, chính sách]
Văn bản:
Công ty TNHH Kỹ thuật Số Việt ban hành Chính sách An toàn Thông tin số 2024-IT-001 vào tháng 3 năm 2024. Chính sách này được Giám đốc Điều hành Nguyễn Văn An phê duyệt và áp dụng cho tất cả nhân viên tại trụ sở Hà Nội.

Kết quả:
("entity"{tuple_delimiter}CÔNG TY TNHH KỸ THUẬT SỐ VIỆT{tuple_delimiter}tổ chức{tuple_delimiter}Công ty công nghệ thông tin ban hành các chính sách nội bộ về an toàn thông tin){record_delimiter}
("entity"{tuple_delimiter}CHÍNH SÁCH AN TOÀN THÔNG TIN 2024-IT-001{tuple_delimiter}chính sách{tuple_delimiter}Chính sách an toàn thông tin số 2024-IT-001, ban hành tháng 3 năm 2024, áp dụng cho toàn bộ nhân viên){record_delimiter}
("entity"{tuple_delimiter}NGUYỄN VĂN AN{tuple_delimiter}người{tuple_delimiter}Giám đốc Điều hành, người phê duyệt Chính sách An toàn Thông tin 2024-IT-001){record_delimiter}
("entity"{tuple_delimiter}HÀ NỘI{tuple_delimiter}địa điểm{tuple_delimiter}Trụ sở của Công ty TNHH Kỹ thuật Số Việt){record_delimiter}
("relationship"{tuple_delimiter}CÔNG TY TNHH KỸ THUẬT SỐ VIỆT{tuple_delimiter}CHÍNH SÁCH AN TOÀN THÔNG TIN 2024-IT-001{tuple_delimiter}Công ty ban hành chính sách này{tuple_delimiter}9){record_delimiter}
("relationship"{tuple_delimiter}NGUYỄN VĂN AN{tuple_delimiter}CHÍNH SÁCH AN TOÀN THÔNG TIN 2024-IT-001{tuple_delimiter}Giám đốc phê duyệt chính sách{tuple_delimiter}8){record_delimiter}
{completion_delimiter}

######################
-Dữ liệu thực tế-
######################

Loại thực thể: [{entity_types}]
Văn bản: {input_text}
Kết quả:
```

### `prompts/community_report.txt`

```
Bạn là một chuyên gia phân tích, chuyên tổng hợp thông tin từ nhiều nguồn khác nhau.

Dưới đây là một cộng đồng thực thể (một nhóm các thực thể có liên quan chặt chẽ với nhau) và các mối quan hệ của chúng. Nhiệm vụ của bạn là tạo ra một báo cáo tổng hợp toàn diện về cộng đồng này.

Nội dung báo cáo phải được viết bằng tiếng Việt và bao gồm:
1. **Tiêu đề**: Tên ngắn gọn đại diện cho cộng đồng
2. **Tóm tắt**: Tổng quan ngắn về cộng đồng (2–3 câu)
3. **Điểm đánh giá tác động**: Số nguyên từ 0–10 thể hiện mức độ quan trọng của cộng đồng này đối với việc hiểu tập tài liệu
4. **Lý do đánh giá**: Giải thích ngắn gọn lý do chọn điểm đánh giá đó
5. **Những phát hiện chính**: Danh sách 5–10 phát hiện quan trọng, mỗi phát hiện bao gồm tiêu đề ngắn và giải thích chi tiết

Định dạng đầu ra theo JSON:
{{
  "title": "<tiêu đề cộng đồng>",
  "summary": "<tóm tắt>",
  "rating": <điểm 0-10>,
  "rating_explanation": "<lý do>",
  "findings": [
    {{
      "summary": "<tiêu đề phát hiện>",
      "explanation": "<giải thích chi tiết>"
    }}
  ]
}}

######################
Dữ liệu cộng đồng:
######################

Thực thể:
{entities}

Mối quan hệ:
{relationships}

######################
Báo cáo (JSON, tiếng Việt):
```

### `prompts/summarize_descriptions.txt`

```
Bạn là một trợ lý AI chuyên tổng hợp thông tin.

Dưới đây là một thực thể cùng với danh sách các mô tả về thực thể đó, được thu thập từ nhiều tài liệu khác nhau. Hãy tổng hợp tất cả các thông tin này thành một mô tả duy nhất, toàn diện, và mạch lạc bằng tiếng Việt.

Yêu cầu:
- Mô tả phải bao gồm tất cả các thông tin quan trọng từ các mô tả gốc
- Giải quyết các thông tin mâu thuẫn bằng cách đề cập đến sự khác biệt
- Viết theo văn phong khách quan, trang trọng
- Độ dài tối đa: {max_length} từ

Thực thể: {entity_name}

Danh sách mô tả:
{description_list}

Mô tả tổng hợp (tiếng Việt):
```

---

## 6. LangChain Integration

LangChain is used **selectively** in this project — for the LLM abstraction layer and Neo4j vector store. It is NOT used for the multi-agent orchestration (plain `asyncio.gather` is cleaner) or the Microsoft GraphRAG indexing pipeline (that runs independently as a CLI).

### 6.1 Where LangChain is used

| Component | LangChain tool | Replaces |
|---|---|---|
| LLM abstraction | `langchain-google-genai`, `langchain-openai` | Custom `BaseLLMService` ABC |
| Siliconflow | `ChatOpenAI(base_url=...)` | Custom `httpx` wrapper |
| Neo4j vector store | `langchain-neo4j` `Neo4jVector` | Custom `neo4j_store.py` vector search |
| History windowing | `ConversationBufferWindowMemory` | Manual `session.messages[-10:]` slice |
| Prompt templates | `ChatPromptTemplate` | f-string prompt templates |

### 6.2 Where LangChain is NOT used

- **Multi-agent orchestration** — `OrchestratorAgent` stays in plain Python with `asyncio.gather`. LangGraph adds complexity without benefit for this routing pattern.
- **Microsoft GraphRAG indexing** — entirely independent CLI pipeline. LangChain has no role here.
- **Answer verification** — custom logic (grounding check + confidence score), kept as plain code for clarity.

### 6.3 LangChain LLM wrappers

All three providers are wrapped as LangChain `BaseChatModel` objects, giving a unified `.ainvoke()` interface:

```python
# backend/app/services/llm_service.py

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

def create_chat_model(provider: str | None = None) -> BaseChatModel:
    resolved = provider or os.environ.get("LLM_PROVIDER", "gemini")
    match resolved.lower():
        case "gemini":
            return ChatGoogleGenerativeAI(
                model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.0-flash"),
                google_api_key=os.environ["GEMINI_API_KEY"],
                temperature=0.0,
            )
        case "openai":
            return ChatOpenAI(
                model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o"),
                api_key=os.environ["OPENAI_API_KEY"],
                temperature=0.0,
            )
        case "siliconflow":
            return ChatOpenAI(
                model=os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3"),
                api_key=os.environ["SILICONFLOW_API_KEY"],
                base_url="https://api.siliconflow.cn/v1",
                temperature=0.0,
            )
        case _:
            raise ValueError(f"Unknown LLM_PROVIDER: '{resolved}'")

def create_embeddings(provider: str | None = None) -> Embeddings:
    resolved = provider or os.environ.get("LLM_PROVIDER", "gemini")
    match resolved.lower():
        case "gemini":
            return GoogleGenerativeAIEmbeddings(
                model=os.environ.get("GEMINI_EMBED_MODEL", "models/text-embedding-004"),
                google_api_key=os.environ["GEMINI_API_KEY"],
            )
        case "openai":
            return OpenAIEmbeddings(
                model=os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
                api_key=os.environ["OPENAI_API_KEY"],
            )
        case "siliconflow":
            # Siliconflow is OpenAI-compatible — use OpenAIEmbeddings with base_url
            return OpenAIEmbeddings(
                model=os.environ.get("SILICONFLOW_EMBED_MODEL", "BAAI/bge-large-zh-v1.5"),
                api_key=os.environ["SILICONFLOW_API_KEY"],
                base_url="https://api.siliconflow.cn/v1",
            )
        case _:
            raise ValueError(f"Unknown LLM_PROVIDER: '{resolved}'")
```

### 6.4 Neo4j vector store via `langchain-neo4j`

`Neo4jVector` from `langchain-neo4j` replaces the custom `neo4j_store.py` vector search methods. It handles index creation, embedding, and similarity search:

```python
from langchain_neo4j import Neo4jVector

# Build on top of the existing TextUnit nodes imported from GraphRAG Parquet
text_unit_store = Neo4jVector.from_existing_graph(
    embedding=create_embeddings(),
    url=os.environ["NEO4J_URI"],
    username=os.environ["NEO4J_USER"],
    password=os.environ["NEO4J_PASSWORD"],
    index_name="text_unit_embedding",
    node_label="TextUnit",
    text_node_properties=["text"],
    embedding_node_property="embedding",
)

# Similarity search — replaces custom vector_search_chunks()
results = text_unit_store.similarity_search_with_score(query, k=10)
```

Community summaries use a separate `Neo4jVector` on `Community` nodes:

```python
community_store = Neo4jVector.from_existing_graph(
    embedding=create_embeddings(),
    ...
    index_name="community_embedding",
    node_label="Community",
    text_node_properties=["summary"],
    embedding_node_property="embedding",
)
```

### 6.5 Conversation memory via `ConversationBufferWindowMemory`

Replaces the manual `session.messages[-10:]` slice in the orchestrator:

```python
from langchain.memory import ConversationBufferWindowMemory

# Stored per session in SessionState
memory = ConversationBufferWindowMemory(
    k=5,                    # keep last 5 turns (= 10 messages)
    return_messages=True,   # returns Message objects, not strings
    memory_key="history",
)

# Add a turn
memory.save_context({"input": user_message}, {"output": assistant_reply})

# Retrieve for LLM
history = memory.load_memory_variables({})["history"]
```

### 6.6 Prompt templates via `ChatPromptTemplate`

Vietnamese prompts are defined as `ChatPromptTemplate` objects for clean variable substitution and reuse across agents:

```python
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

DOMAIN_AGENT_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(
        "Bạn là chuyên gia về {domain}. Trả lời bằng tiếng Việt dựa trên ngữ cảnh sau:\n\n{context}"
    ),
    HumanMessagePromptTemplate.from_template("{question}"),
])

# Use in a domain agent
chain = DOMAIN_AGENT_PROMPT | llm
response = await chain.ainvoke({
    "domain": "chính sách nhân sự",
    "context": retrieved_context,
    "question": rewritten_query,
})
```

---

## 7. Multi-LLM Service Design (LangChain-backed)

The custom `BaseLLMService` ABC is replaced by LangChain's `BaseChatModel` interface. The factory functions from Section 6.3 (`create_chat_model`, `create_embeddings`) are the single entry points for all LLM and embedding calls in the agent layer.

### Two LLM Layers

The system has two distinct LLM layers that can be configured independently:

| Layer | Config source | Purpose |
|---|---|---|
| **GraphRAG indexing** | `settings.yaml` → `llm:` block | Entity extraction, community summarization during `graphrag index` |
| **Agent layer** | `LLM_PROVIDER` env var → `create_chat_model()` | Orchestrator classification, domain agent answer generation, synthesis |

You can index with Gemini (best Vietnamese extraction quality) and query with Siliconflow (lower cost). They don't need to match.

### Siliconflow Model Options

| Model | Context | Vietnamese quality | Cost tier |
|---|---|---|---|
| `deepseek-ai/DeepSeek-V3` | 64K | Excellent | Medium |
| `Qwen/Qwen2.5-72B-Instruct` | 128K | Very good | Medium |
| `deepseek-ai/DeepSeek-R1` | 64K | Excellent (reasoning) | High |
| `BAAI/bge-large-zh-v1.5` (embed) | — | Strong for CJK/Vietnamese | Low |

**Important**: `BAAI/bge-large-zh-v1.5` produces **1024-dim** vectors (not 768). Set `EMBEDDING_DIM=1024` if using Siliconflow embeddings, and adjust `import_to_neo4j.py` accordingly. Do not mix embedding providers mid-project.

---

## 8. Multi-Agent Design

### Domain Registry (`app/domains.py`)

```python
# backend/app/domains.py
"""
Single source of truth for domain configuration.
Add new domains here; the orchestrator and agent registry pick them up automatically.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Domain:
    key: str            # used in orchestrator classification output
    name_vi: str        # Vietnamese display name
    description_vi: str # used in orchestrator's classification prompt


DOMAINS: list[Domain] = [
    Domain(
        key="hr",
        name_vi="Nhân sự",
        description_vi="Chính sách tuyển dụng, hợp đồng lao động, kỷ luật, nghỉ phép, đánh giá hiệu suất",
    ),
    Domain(
        key="benefits",
        name_vi="Phúc lợi",
        description_vi="Bảo hiểm y tế, bảo hiểm xã hội, phụ cấp, chế độ nghỉ thai sản, quỹ hưu trí",
    ),
    Domain(
        key="it",
        name_vi="Bảo mật CNTT",
        description_vi="Chính sách an toàn thông tin, quy trình bảo mật, quản lý mật khẩu, quyền truy cập hệ thống",
    ),
    Domain(
        key="finance",
        name_vi="Tài chính",
        description_vi="Quy trình thanh toán, hoàn chi phí, ngân sách, báo cáo tài chính, kiểm soát nội bộ",
    ),
    Domain(
        key="compliance",
        name_vi="Tuân thủ",
        description_vi="Quy định pháp luật, tiêu chuẩn ngành, báo cáo kiểm toán, phòng chống tham nhũng",
    ),
    Domain(
        key="procedures",
        name_vi="Quy trình",
        description_vi="Quy trình vận hành chuẩn (SOP), hướng dẫn công việc, biểu mẫu, phê duyệt nội bộ",
    ),
    Domain(
        key="general",
        name_vi="Tổng hợp",
        description_vi="Câu hỏi chung không thuộc các lĩnh vực chuyên biệt trên",
    ),
]

DOMAIN_MAP: dict[str, Domain] = {d.key: d for d in DOMAINS}
```

### `BaseDomainAgent` (`app/agents/base_agent.py`)

```python
# backend/app/agents/base_agent.py

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.services.llm_service import BaseLLMService


@dataclass
class AgentResult:
    domain_key: str
    answer: str
    search_mode: str        # "local" | "global"
    sources: list[dict]


class BaseDomainAgent(ABC):
    """
    Abstract base for all domain specialist agents.

    Each concrete agent must define:
    - domain_key: str — matches a key in DOMAIN_MAP
    - _system_prompt: str — Vietnamese system prompt for this domain
    """

    domain_key: str
    _system_prompt: str

    def __init__(self, llm: BaseLLMService) -> None:
        self._llm = llm

    @abstractmethod
    def _build_user_message(
        self,
        question: str,
        context_chunks: list[str],
        graph_context: str,
    ) -> str:
        """Build the user message for the LLM from retrieved context."""
        ...

    async def answer(
        self,
        question: str,
        context_chunks: list[str],
        graph_context: str,
        search_mode: str = "local",
        sources: list[dict] | None = None,
    ) -> AgentResult:
        """
        Generate a Vietnamese answer for the question using the provided context.

        Args:
            question: The user's question (Vietnamese)
            context_chunks: Text excerpts from GraphRAG retrieval
            graph_context: Community summaries or graph traversal results
            search_mode: "local" or "global"
            sources: Source references from GraphRAG

        Returns:
            AgentResult with domain_key, answer, search_mode, sources
        """
        user_message = self._build_user_message(question, context_chunks, graph_context)
        reply = await self._llm.chat(
            messages=[{"role": "user", "content": user_message}],
            system=self._system_prompt,
            temperature=0.1,
            max_tokens=1500,
        )
        return AgentResult(
            domain_key=self.domain_key,
            answer=reply.strip(),
            search_mode=search_mode,
            sources=sources or [],
        )
```

### `OrchestratorAgent` (`app/agents/orchestrator.py`)

```python
# backend/app/agents/orchestrator.py

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from app.agents.base_agent import AgentResult, BaseDomainAgent
from app.domains import DOMAIN_MAP, DOMAINS
from app.prompts.orchestrator_prompts import CLASSIFICATION_PROMPT, SYNTHESIS_PROMPT
from app.services.graphrag_service import GraphRAGService, SearchMode
from app.services.llm_service import BaseLLMService

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    final_answer: str
    domain_keys: list[str]
    agent_results: list[AgentResult]
    search_mode: str
    sources: list[dict]


class OrchestratorAgent:
    """
    Classifies questions → routes to one or more DomainAgents → synthesizes.

    Flow:
        1. Classify question → list of domain keys (LLM call)
        2a. Single domain → direct route to DomainAgent (one GraphRAG search)
        2b. Multi-domain → asyncio.gather fan-out → _synthesize()
        3. Return OrchestratorResult
    """

    def __init__(
        self,
        llm: BaseLLMService,
        graphrag: GraphRAGService,
        agents: dict[str, BaseDomainAgent],
    ) -> None:
        self._llm = llm
        self._graphrag = graphrag
        self._agents = agents  # {domain_key: DomainAgent}

    async def run(
        self,
        question: str,
        session_history: str = "",
    ) -> OrchestratorResult:
        # Step 1: Classify
        domain_keys = await self._classify(question, session_history)
        logger.info("Classified question into domains: %s", domain_keys)

        # Step 2: Determine search mode (global for cross-domain, local otherwise)
        search_mode = SearchMode.GLOBAL if len(domain_keys) > 1 else SearchMode.LOCAL

        # Step 3: Retrieve context from GraphRAG
        graphrag_result = await self._graphrag.search(question, search_mode)

        context_chunks = [
            s.get("text", s.get("summary", ""))
            for s in graphrag_result.get("sources", [])
            if s.get("text") or s.get("summary")
        ]
        graph_context = graphrag_result.get("reply", "")
        sources = graphrag_result.get("sources", [])

        # Step 4: Route
        if len(domain_keys) == 1:
            agent = self._agents.get(domain_keys[0]) or self._agents["general"]
            result = await agent.answer(
                question=question,
                context_chunks=context_chunks,
                graph_context=graph_context,
                search_mode=search_mode.value,
                sources=sources,
            )
            return OrchestratorResult(
                final_answer=result.answer,
                domain_keys=domain_keys,
                agent_results=[result],
                search_mode=search_mode.value,
                sources=sources,
            )
        else:
            # Fan-out to all relevant domain agents in parallel
            tasks = []
            for key in domain_keys:
                agent = self._agents.get(key) or self._agents["general"]
                tasks.append(
                    agent.answer(
                        question=question,
                        context_chunks=context_chunks,
                        graph_context=graph_context,
                        search_mode=search_mode.value,
                        sources=sources,
                    )
                )
            agent_results: list[AgentResult] = await asyncio.gather(*tasks)
            final_answer = await self._synthesize(question, agent_results)
            return OrchestratorResult(
                final_answer=final_answer,
                domain_keys=domain_keys,
                agent_results=list(agent_results),
                search_mode=search_mode.value,
                sources=sources,
            )

    async def _classify(self, question: str, session_history: str) -> list[str]:
        """
        Call the LLM with the classification prompt.
        Returns a list of domain keys (subset of DOMAIN_MAP keys).
        Falls back to ["general"] on parse error.
        """
        domain_list = "\n".join(
            f"- {d.key}: {d.description_vi}" for d in DOMAINS
        )
        prompt = CLASSIFICATION_PROMPT.format(
            domain_list=domain_list,
            session_history=session_history or "(không có lịch sử)",
            question=question,
        )
        raw = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
        )
        try:
            keys = json.loads(raw.strip())
            if isinstance(keys, list):
                valid = [k for k in keys if k in DOMAIN_MAP]
                return valid if valid else ["general"]
        except (json.JSONDecodeError, ValueError):
            pass
        # Fallback: try to find domain keys mentioned in the raw output
        found = [k for k in DOMAIN_MAP if k in raw.lower()]
        return found if found else ["general"]

    async def _synthesize(
        self,
        question: str,
        agent_results: list[AgentResult],
    ) -> str:
        """Merge multiple domain agent answers into a single coherent Vietnamese response."""
        parts = []
        for r in agent_results:
            domain = DOMAIN_MAP.get(r.domain_key)
            name = domain.name_vi if domain else r.domain_key
            parts.append(f"## {name}\n{r.answer}")
        combined = "\n\n".join(parts)

        prompt = SYNTHESIS_PROMPT.format(
            question=question,
            combined_answers=combined,
        )
        return await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )
```

### Vietnamese Prompts (`app/prompts/`)

```python
# backend/app/prompts/orchestrator_prompts.py

CLASSIFICATION_PROMPT = """Bạn là một hệ thống phân loại câu hỏi thông minh.

Dưới đây là danh sách các lĩnh vực chuyên môn:
{domain_list}

Lịch sử hội thoại:
{session_history}

Câu hỏi mới: {question}

Nhiệm vụ: Xác định một hoặc nhiều lĩnh vực phù hợp nhất để trả lời câu hỏi này.
- Nếu câu hỏi chỉ liên quan đến một lĩnh vực, trả về danh sách với một phần tử.
- Nếu câu hỏi liên quan đến nhiều lĩnh vực, liệt kê tất cả.
- Nếu không chắc, sử dụng "general".

Trả về CHÍNH XÁC một mảng JSON các khóa lĩnh vực. Ví dụ: ["hr"] hoặc ["hr", "benefits"] hoặc ["general"]

Kết quả:"""


SYNTHESIS_PROMPT = """Bạn là một trợ lý tổng hợp thông minh. Nhiệm vụ của bạn là kết hợp các câu trả lời từ nhiều chuyên gia thành một câu trả lời thống nhất, mạch lạc bằng tiếng Việt.

Câu hỏi gốc: {question}

Các câu trả lời từ chuyên gia:
{combined_answers}

Yêu cầu:
- Tổng hợp thành một câu trả lời thống nhất, không lặp lại thông tin
- Sắp xếp thông tin theo thứ tự logic, dễ hiểu
- Sử dụng tiếng Việt tự nhiên, trang trọng
- Nếu các câu trả lời mâu thuẫn, đề cập rõ ràng sự khác biệt
- Không đề cập đến việc có nhiều "chuyên gia" hay "lĩnh vực" — người dùng chỉ cần thấy một câu trả lời hoàn chỉnh

Câu trả lời tổng hợp:"""
```

```python
# backend/app/prompts/system_prompts.py

HR_SYSTEM_PROMPT = """Bạn là chuyên gia nhân sự (HR) của công ty với kiến thức sâu rộng về:
- Chính sách tuyển dụng và onboarding
- Hợp đồng lao động và quyền lợi người lao động
- Quy trình kỷ luật và giải quyết khiếu nại
- Chính sách nghỉ phép (phép năm, phép ốm, phép thai sản)
- Đánh giá hiệu suất và thăng tiến

Khi trả lời:
- Sử dụng ngôn ngữ chuyên nghiệp, rõ ràng bằng tiếng Việt
- Trích dẫn số điều khoản hoặc tên chính sách khi có thể
- Nếu thông tin không có trong tài liệu, hãy nói rõ và đề xuất liên hệ phòng HR
- Không bịa đặt thông tin"""

BENEFITS_SYSTEM_PROMPT = """Bạn là chuyên gia phúc lợi nhân viên với kiến thức về:
- Bảo hiểm y tế, bảo hiểm xã hội, bảo hiểm thất nghiệp
- Phụ cấp (ăn trưa, đi lại, điện thoại, nhà ở)
- Chế độ thai sản và gia đình
- Quỹ hưu trí và tiết kiệm dài hạn
- Các phúc lợi tự nguyện và chương trình sức khỏe

Khi trả lời:
- Nêu rõ mức hưởng, điều kiện hưởng, và cách đăng ký
- Phân biệt rõ phúc lợi bắt buộc (pháp lý) và phúc lợi tự nguyện (công ty)
- Sử dụng tiếng Việt, có thể kèm số liệu cụ thể khi tài liệu cung cấp"""

IT_SYSTEM_PROMPT = """Bạn là chuyên gia bảo mật CNTT với kiến thức về:
- Chính sách an toàn thông tin và bảo mật dữ liệu
- Quản lý mật khẩu và xác thực đa yếu tố
- Quyền truy cập hệ thống và quản lý tài khoản
- Ứng phó sự cố bảo mật và báo cáo vi phạm
- Quy định sử dụng thiết bị và mạng công ty

Khi trả lời:
- Nhấn mạnh tính bảo mật và tuân thủ chính sách
- Đưa ra hướng dẫn cụ thể, từng bước khi có thể
- Cảnh báo rõ về các hành vi bị cấm và hậu quả
- Sử dụng thuật ngữ kỹ thuật kèm giải thích bằng tiếng Việt"""

FINANCE_SYSTEM_PROMPT = """Bạn là chuyên gia tài chính nội bộ với kiến thức về:
- Quy trình thanh toán và phê duyệt chi tiêu
- Chính sách hoàn chi phí công tác và tiếp khách
- Quản lý ngân sách và kiểm soát chi phí
- Báo cáo tài chính nội bộ và đối soát
- Kiểm soát nội bộ và phòng chống gian lận

Khi trả lời:
- Nêu rõ hạn mức phê duyệt và quy trình phê duyệt theo cấp
- Đề cập đến chứng từ và tài liệu cần thiết
- Giải thích timeline xử lý thanh toán
- Sử dụng tiếng Việt trang trọng, chính xác về số liệu"""

COMPLIANCE_SYSTEM_PROMPT = """Bạn là chuyên gia tuân thủ (Compliance) với kiến thức về:
- Quy định pháp luật Việt Nam liên quan đến hoạt động doanh nghiệp
- Tiêu chuẩn ngành và chứng nhận quốc tế (ISO, SOC2, v.v.)
- Chính sách phòng chống rửa tiền và tham nhũng (AML, ABAC)
- Báo cáo kiểm toán nội bộ và bên ngoài
- Bảo vệ dữ liệu cá nhân (PDPA/GDPR áp dụng)

Khi trả lời:
- Trích dẫn điều khoản pháp lý hoặc tên quy định khi có thể
- Phân biệt rõ yêu cầu bắt buộc và khuyến nghị
- Đề xuất bước tiếp theo rõ ràng nếu có vi phạm
- Sử dụng ngôn ngữ pháp lý chính xác bằng tiếng Việt"""

PROCEDURES_SYSTEM_PROMPT = """Bạn là chuyên gia quy trình vận hành với kiến thức về:
- Quy trình vận hành chuẩn (Standard Operating Procedures - SOP)
- Hướng dẫn công việc và checklist thực hiện
- Biểu mẫu nội bộ và quy trình điền/nộp
- Luồng phê duyệt và ủy quyền
- Quản lý thay đổi và cập nhật quy trình

Khi trả lời:
- Mô tả quy trình theo thứ tự từng bước
- Nêu rõ vai trò và trách nhiệm của từng bên
- Đề cập đến biểu mẫu, hệ thống, hoặc công cụ cần dùng
- Sử dụng tiếng Việt rõ ràng, dễ thực hiện"""

GENERAL_SYSTEM_PROMPT = """Bạn là trợ lý thông minh của công ty, có khả năng trả lời các câu hỏi chung về chính sách, quy trình và thông tin nội bộ.

Khi trả lời:
- Cung cấp thông tin chính xác dựa trên tài liệu nội bộ
- Nếu câu hỏi thuộc lĩnh vực chuyên biệt, gợi ý người dùng hỏi cụ thể hơn
- Nếu không có thông tin, hãy thành thật và đề xuất nguồn liên hệ
- Sử dụng tiếng Việt thân thiện, chuyên nghiệp"""

DOMAIN_SYSTEM_PROMPTS: dict[str, str] = {
    "hr": HR_SYSTEM_PROMPT,
    "benefits": BENEFITS_SYSTEM_PROMPT,
    "it": IT_SYSTEM_PROMPT,
    "finance": FINANCE_SYSTEM_PROMPT,
    "compliance": COMPLIANCE_SYSTEM_PROMPT,
    "procedures": PROCEDURES_SYSTEM_PROMPT,
    "general": GENERAL_SYSTEM_PROMPT,
}
```

### Concrete Domain Agents

Each domain agent follows the same pattern. Example for HR:

```python
# backend/app/agents/hr_agent.py

from app.agents.base_agent import BaseDomainAgent
from app.prompts.system_prompts import HR_SYSTEM_PROMPT
from app.services.llm_service import BaseLLMService


class HRAgent(BaseDomainAgent):
    domain_key = "hr"
    _system_prompt = HR_SYSTEM_PROMPT

    def __init__(self, llm: BaseLLMService) -> None:
        super().__init__(llm)

    def _build_user_message(
        self,
        question: str,
        context_chunks: list[str],
        graph_context: str,
    ) -> str:
        context = "\n\n---\n\n".join(context_chunks[:5]) if context_chunks else ""
        return f"""Thông tin từ tài liệu nội bộ:
{context}

Tóm tắt từ đồ thị tri thức:
{graph_context}

Câu hỏi của nhân viên: {question}

Hãy trả lời câu hỏi dựa trên thông tin trên. Nếu không đủ thông tin, hãy nói rõ."""
```

Repeat this pattern for `BenefitsAgent`, `ITAgent`, `FinanceAgent`, `ComplianceAgent`, `ProceduresAgent`, `GeneralAgent` — each with its respective `domain_key` and `_system_prompt` from `system_prompts.py`.

### Agent Orchestration Sequence Diagram

```
User Question
     │
     ▼
OrchestratorAgent.run(question, session_history)
     │
     ├─ [1] _classify(question)
     │         │
     │         └─ LLM call (classification prompt, ~100 tokens)
     │              └─ returns: ["hr"] or ["hr", "benefits"] etc.
     │
     ├─ [2] GraphRAGService.search(question, mode)
     │         │
     │         ├─ Single domain → SearchMode.LOCAL
     │         └─ Multi-domain  → SearchMode.GLOBAL
     │              └─ returns: {reply, sources}
     │
     ├─ [3a] Single domain:
     │         DomainAgent.answer(question, chunks, graph_context)
     │              └─ LLM call (domain system prompt)
     │                   └─ AgentResult
     │
     └─ [3b] Multi-domain (asyncio.gather):
               ├─ DomainAgent_A.answer(...)  ─┐
               ├─ DomainAgent_B.answer(...)  ─┤ concurrent
               └─ DomainAgent_C.answer(...)  ─┘
                         │
                    [4] _synthesize(question, [ResultA, ResultB, ResultC])
                              │
                              └─ LLM call (synthesis prompt)
                                   └─ final_answer (Vietnamese)
     │
     ▼
OrchestratorResult {
  final_answer,
  domain_keys,
  agent_results,     ← used for /agent_trace endpoint
  search_mode,
  sources
}
```

---

## 9. GraphRAG Query Integration

`graphrag_service.py` initializes `LocalSearch` and `GlobalSearch` using Neo4j-backed stores (Option B: reads Parquet at startup then queries Neo4j for vector search; Option A: reads directly from Neo4j).

```python
# backend/app/services/graphrag_service.py

from __future__ import annotations

import asyncio
import os
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd
from graphrag.query.context_builder.entity_extraction import EntityVectorStoreKey
from graphrag.query.indexer_adapters import (
    read_indexer_communities,
    read_indexer_entities,
    read_indexer_relationships,
    read_indexer_reports,
    read_indexer_text_units,
)
from graphrag.query.llm.oai.chat_openai import ChatOpenAI
from graphrag.query.llm.oai.embedding import OpenAIEmbedding
from graphrag.query.llm.oai.typing import OpenaiApiType
from graphrag.query.structured_search.global_search.community_context import (
    GlobalCommunityContext,
)
from graphrag.query.structured_search.global_search.search import GlobalSearch
from graphrag.query.structured_search.local_search.mixed_context import (
    LocalSearchMixedContext,
)
from graphrag.query.structured_search.local_search.search import LocalSearch

from app.services.neo4j_store import Neo4jVectorStore


class SearchMode(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"


class GraphRAGService:
    """
    Wraps Microsoft GraphRAG LocalSearch and GlobalSearch.
    Uses Neo4j for vector similarity search (entity and community embeddings).
    Reads graph structure from Parquet artifacts (Option B) or Neo4j (Option A).
    """

    def __init__(self, workspace_root: str, neo4j_store: "Neo4jVectorStore") -> None:
        self._root = Path(workspace_root)
        self._artifacts = self._root / "output" / "artifacts"
        self._neo4j = neo4j_store
        self._local_search: LocalSearch | None = None
        self._global_search: GlobalSearch | None = None
        self._lock = asyncio.Lock()

    async def search(self, question: str, mode: SearchMode) -> dict[str, Any]:
        engine = self._local_search if mode == SearchMode.LOCAL else self._global_search
        if engine is None:
            raise RuntimeError("GraphRAG not ready. Run indexing and import first.")
        result = await engine.asearch(question)
        return {
            "reply": result.response,
            "sources": self._extract_sources(result.context_data),
        }

    async def reload(self) -> None:
        async with self._lock:
            self._local_search = await asyncio.to_thread(self._build_local_search)
            self._global_search = await asyncio.to_thread(self._build_global_search)

    @property
    def is_ready(self) -> bool:
        return self._local_search is not None

    def _llm(self) -> ChatOpenAI:
        """
        GraphRAG's own LLM client for query-time summarization.
        Uses Gemini by default (via OpenAI-compatible endpoint).
        This is separate from the agent-layer LLM.
        """
        return ChatOpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            model=os.environ.get("GRAPHRAG_QUERY_MODEL", "gemini-2.0-flash"),
            api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_type=OpenaiApiType.OpenAI,
            max_retries=10,
        )

    def _embedder(self) -> OpenAIEmbedding:
        return OpenAIEmbedding(
            api_key=os.environ["GEMINI_API_KEY"],
            model=os.environ.get("EMBEDDING_MODEL", "text-embedding-004"),
            api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_type=OpenaiApiType.OpenAI,
            max_retries=10,
        )

    def _build_local_search(self) -> LocalSearch:
        a = self._artifacts
        entity_df = pd.read_parquet(a / "create_final_entities.parquet")
        rel_df = pd.read_parquet(a / "create_final_relationships.parquet")
        report_df = pd.read_parquet(a / "create_final_community_reports.parquet")
        text_unit_df = pd.read_parquet(a / "create_final_text_units.parquet")
        node_df = pd.read_parquet(a / "create_final_nodes.parquet")

        entities = read_indexer_entities(entity_df, node_df, community_level=2)
        relationships = read_indexer_relationships(rel_df)
        reports = read_indexer_reports(report_df, node_df, community_level=2)
        text_units = read_indexer_text_units(text_unit_df)

        # Use Neo4jVectorStore adapter instead of LanceDB
        entity_store = self._neo4j.as_entity_vector_store()

        context_builder = LocalSearchMixedContext(
            community_reports=reports,
            text_units=text_units,
            entities=entities,
            relationships=relationships,
            entity_text_embeddings=entity_store,
            embedding_vectorstore_key=EntityVectorStoreKey.ID,
            text_embedder=self._embedder(),
        )

        return LocalSearch(
            llm=self._llm(),
            context_builder=context_builder,
            token_encoder=None,
            llm_params={"max_tokens": 2000, "temperature": 0},
            context_builder_params={
                "text_unit_prop": 0.5,
                "community_prop": 0.1,
                "conversation_history_max_turns": 5,
                "top_k_mapped_entities": 10,
                "top_k_relationships": 10,
                "max_tokens": 12000,
            },
        )

    def _build_global_search(self) -> GlobalSearch:
        a = self._artifacts
        report_df = pd.read_parquet(a / "create_final_community_reports.parquet")
        node_df = pd.read_parquet(a / "create_final_nodes.parquet")
        entity_df = pd.read_parquet(a / "create_final_entities.parquet")

        reports = read_indexer_reports(report_df, node_df, community_level=2)
        entities = read_indexer_entities(entity_df, node_df, community_level=2)

        context_builder = GlobalCommunityContext(
            community_reports=reports,
            entities=entities,
            token_encoder=None,
        )

        return GlobalSearch(
            llm=self._llm(),
            context_builder=context_builder,
            token_encoder=None,
            max_data_tokens=12000,
            map_llm_params={"max_tokens": 1000, "temperature": 0},
            reduce_llm_params={"max_tokens": 2000, "temperature": 0},
            concurrent_coroutines=32,
            response_type="multiple paragraphs",
        )

    def _extract_sources(self, context_data: dict) -> list[dict]:
        sources = []
        for unit in context_data.get("text_units", []):
            sources.append({
                "type": "text_unit",
                "id": unit.get("id"),
                "text": unit.get("text", "")[:400],
                "document": unit.get("document_id"),
            })
        for report in context_data.get("reports", []):
            sources.append({
                "type": "community_report",
                "id": report.get("id"),
                "title": report.get("title"),
                "summary": report.get("summary", "")[:400],
            })
        return sources
```

### `Neo4jVectorStore` Adapter (`app/services/neo4j_store.py`)

This adapter wraps the Neo4j driver and implements the vector store interface expected by GraphRAG's `LocalSearchMixedContext`. It also provides direct Cypher query methods used by agents for graph traversal.

```python
# backend/app/services/neo4j_store.py

from __future__ import annotations

import os
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver


class Neo4jStore:
    """
    Async Neo4j driver wrapper.
    Provides vector search (entity, community) and graph traversal helpers.
    """

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()

    async def entity_vector_search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Return top-k entities by cosine similarity to query_embedding."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                CALL db.index.vector.queryNodes(
                    'entity_embedding', $k, $embedding
                ) YIELD node, score
                RETURN node.id AS id,
                       node.name AS name,
                       node.type AS type,
                       node.description AS description,
                       score
                ORDER BY score DESC
                """,
                k=top_k,
                embedding=query_embedding,
            )
            return [dict(r) async for r in result]

    async def community_vector_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return top-k community summaries by cosine similarity."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                CALL db.index.vector.queryNodes(
                    'community_embedding', $k, $embedding
                ) YIELD node, score
                RETURN node.id AS id,
                       node.title AS title,
                       node.summary AS summary,
                       node.level AS level,
                       score
                ORDER BY score DESC
                """,
                k=top_k,
                embedding=query_embedding,
            )
            return [dict(r) async for r in result]

    async def get_entity_neighbors(
        self,
        entity_id: str,
        max_depth: int = 2,
    ) -> list[dict[str, Any]]:
        """Traverse the graph from an entity and return neighboring entities."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (e:Entity {id: $id})-[r:RELATED_TO*1..$depth]-(neighbor:Entity)
                RETURN DISTINCT neighbor.id AS id,
                               neighbor.name AS name,
                               neighbor.type AS type,
                               neighbor.description AS description
                LIMIT 50
                """,
                id=entity_id,
                depth=max_depth,
            )
            return [dict(r) async for r in result]

    async def get_entity_text_units(self, entity_id: str) -> list[dict[str, Any]]:
        """Return text units that mention an entity."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (t:TextUnit)-[:MENTIONS]->(e:Entity {id: $id})
                RETURN t.id AS id, t.text AS text, t.document_id AS document_id
                LIMIT 20
                """,
                id=entity_id,
            )
            return [dict(r) async for r in result]

    def as_entity_vector_store(self):
        """
        Returns a thin adapter that implements the VectorStore interface
        expected by GraphRAG's LocalSearchMixedContext.
        This wraps Neo4j vector search in the interface GraphRAG expects.
        """
        return _Neo4jEntityVectorStoreAdapter(self)


class _Neo4jEntityVectorStoreAdapter:
    """
    Minimal adapter implementing the subset of GraphRAG's VectorStore API
    needed by LocalSearchMixedContext.entity_text_embeddings.

    GraphRAG expects:
        store.search(query_embedding, k) -> list of (id, score) tuples
    """

    def __init__(self, neo4j: Neo4jStore) -> None:
        self._neo4j = neo4j

    def search(
        self,
        query_embedding: list[float],
        k: int = 10,
    ) -> list[tuple[str, float]]:
        """
        Synchronous wrapper (GraphRAG's LocalSearch calls this synchronously
        in some code paths). Use asyncio.get_event_loop().run_until_complete()
        or restructure to async depending on GraphRAG version.
        """
        import asyncio
        results = asyncio.get_event_loop().run_until_complete(
            self._neo4j.entity_vector_search(query_embedding, top_k=k)
        )
        return [(r["id"], r["score"]) for r in results]
```

**Note on the adapter**: GraphRAG's internal API for `entity_text_embeddings` may differ across 2.x minor versions. If the synchronous `search()` method causes event loop conflicts, wrap `Neo4jStore.entity_vector_search` using `asyncio.to_thread` at the call site, or patch the adapter to use `nest_asyncio`. Pin `graphrag>=2.0.0,<3.0.0` and test the adapter against your pinned version.

---

## 10. Retrieval Quality Pipeline

The retrieval pipeline runs in eight sequential layers, each inherited or adapted from the proven `graphrag-assistant` implementation. Together they transform a raw user question into a high-precision, grounded Vietnamese answer.

```
User question
    │
    ▼ Layer 1: Query rewriting
    │
    ▼ Layer 2: Overfetch (k=25)  ←── Neo4j vector search
    │
    ▼ Layer 3: Entity augmentation (type-aware seeding)
    │
    ▼ Layer 4: Cohere cross-encoder rerank (25 → 8)
    │
    ▼ Layer 5: Seed entity re-anchoring (post-rerank)
    │
    ▼ Layer 6: 2-hop graph neighborhood traversal
    │
    ▼ Layer 7: Seed-entity triple filtering
    │
    ▼ LLM answer generation (per domain agent)
    │
    ▼ Layer 8: Two-level answer verification
    │
    ▼ Final answer (Vietnamese)
```

---

### Layer 1 — Multi-turn query rewriting

**Source**: `graphrag-assistant/llm_service.py:181-198` — carried over unchanged.

Before embedding, the orchestrator rewrites vague or context-dependent questions using the last 6 messages of conversation history. This ensures follow-up questions become standalone retrieval queries.

**Vietnamese rewrite prompt** (in `app/prompts/orchestrator_prompts.py`):

```python
QUERY_REWRITE_PROMPT = """\
Dựa vào lịch sử hội thoại bên dưới và câu hỏi mới nhất của người dùng, hãy viết lại câu hỏi \
thành một câu hỏi độc lập, đầy đủ ngữ cảnh để tìm kiếm trong cơ sở tri thức.
Chỉ trả về câu hỏi đã viết lại, không thêm bất kỳ giải thích nào.

Lịch sử hội thoại:
{history_text}

Câu hỏi hiện tại: {question}
Câu hỏi độc lập:"""
```

**Behaviour**:
- Turn 1 (empty history) → skip rewrite, use original question as-is (avoids unnecessary latency on first turn)
- Turn 2+ → rewrite with last 6 messages (`history[-6:]`)
- On any LLM error → fall back to original question (never blocks retrieval)
- Temperature: `0.0` — deterministic rewrites

**Multi-agent adaptation**: rewriting happens **once at the orchestrator** before routing. All domain agents receive the same rewritten query, preventing inconsistent disambiguation per agent.

---

### Layer 2 — Overfetch for reranking headroom

**Source**: `graphrag-assistant/graph_rag_service.py:84-90` — carried over.

Vector search returns `rerank_candidate_pool=25` chunks instead of the final `max_local_chunks=8`. This gives the cross-encoder reranker in Layer 4 a larger pool to select from. Cosine similarity ranks topical proximity; the cross-encoder ranks answer relevance. They disagree frequently enough that fetching 3× the final count measurably improves precision.

```python
# graphrag_service.py
pool_size = settings.rerank_candidate_pool if settings.enable_rerank else settings.max_local_chunks
# Use langchain-neo4j Neo4jVector:
candidates = text_unit_store.similarity_search_with_score(rewritten_query, k=pool_size)
```

**Config** (`config.py`):
```python
RERANK_CANDIDATE_POOL: int = 25   # overfetch size
MAX_LOCAL_CHUNKS: int = 8         # final context size after rerank
ENABLE_RERANK: bool = True
```

---

### Layer 3 — Type-aware entity seeding

**Source**: `graphrag-assistant/neo4j_store.py:213-271` and `graph_rag_service.py:93-116` — carried over with adapted entity types.

After vector search, seed entities are extracted from the candidate chunks and used to fetch additional entity-linked `TextUnit` nodes from Neo4j. Not all entities are treated equally:

**Specific entity types** → `min_entity_hits = 1`
These are scoped to one policy area. A single occurrence of `CHINH_SACH` or `QUY_TRINH` in a chunk is a strong signal of relevance.

**Generic entity types** → `min_entity_hits = 2`
Entities like `VAI_TRO` ("employee", "manager") or `PHONG_BAN` ("HR department") appear in almost every chunk. Requiring co-occurrence of 2+ of these prevents flooding the context with off-topic results.

```python
# app/services/neo4j_store.py

SPECIFIC_ENTITY_TYPES = frozenset({
    # Vietnamese GraphRAG entity types — mapped from existing project
    "chính sách",   # policy
    "quy trình",    # process
    "quy tắc",      # rule
    "quyền lợi",    # benefit/entitlement
    "ngoại lệ",     # exception
})

GENERIC_ENTITY_TYPES = frozenset({
    "người",        # person / role
    "tổ chức",      # organization / department
    "địa điểm",     # location
})

async def get_chunks_by_entity_names(
    self,
    entity_names: list[str],
    k: int = 5,
    min_entity_hits: int = 2,
) -> list[dict]:
    """
    Return TextUnit nodes that co-mention at least min_entity_hits of the given entities.
    Requiring co-occurrence ensures topical focus — a chunk mentioning 3 seed entities
    is almost certainly on-topic; one mentioning only 'Nhân viên' may not be.
    """
    async with self._driver.session() as session:
        result = await session.run(
            """
            MATCH (t:TextUnit)-[:MENTIONS]->(e:Entity)
            WHERE e.name IN $names
            WITH t, COUNT(DISTINCT e) AS hits
            WHERE hits >= $min_hits
            RETURN t.id AS id, t.text AS text, t.document_id AS document_id,
                   hits AS entity_hit_count,
                   0.5 AS score
            ORDER BY hits DESC
            LIMIT $k
            """,
            names=entity_names,
            min_hits=min_entity_hits,
            k=k,
        )
        return [dict(r) async for r in result]

async def get_specific_entity_names(self, entity_names: list[str]) -> list[str]:
    """Filter to only specific (non-generic) entity names for relaxed retrieval."""
    async with self._driver.session() as session:
        result = await session.run(
            """
            MATCH (e:Entity)
            WHERE e.name IN $names AND e.type IN $types
            RETURN e.name AS name
            """,
            names=entity_names,
            types=list(SPECIFIC_ENTITY_TYPES),
        )
        return [r["name"] async for r in result]
```

**Orchestration in `graphrag_service.py`**:

```python
# Step 1: collect seed entities from overfetch pool
seed_pool = []
for chunk in candidates:
    seed_pool.extend(chunk.metadata.get("entity_names") or [])
seed_pool = list(dict.fromkeys(seed_pool))[:20]   # dedup, keep order, cap at 20

# Step 2: split into specific vs generic
specific_seeds = await neo4j_store.get_specific_entity_names(seed_pool)
if specific_seeds:
    # specific entities → loose threshold (min_hits=1): narrow scope, safe
    entity_chunks = await neo4j_store.get_chunks_by_entity_names(
        specific_seeds, k=5, min_entity_hits=1
    )
else:
    # only generic entities → strict threshold (min_hits=2): prevent noise flood
    entity_chunks = await neo4j_store.get_chunks_by_entity_names(
        seed_pool, k=5, min_entity_hits=2
    )

# Step 3: merge without duplicates
seen_ids = {c["id"] for c in candidates}
for ec in entity_chunks:
    if ec["id"] not in seen_ids:
        candidates.append(ec)
        seen_ids.add(ec["id"])
```

---

### Layer 4 — Cohere multilingual cross-encoder reranking

**Source**: `graphrag-assistant/rerank_service.py` — carried over unchanged.

`cohere rerank-multilingual-v3.0` is a cross-encoder trained on multilingual text including Vietnamese. Unlike cosine similarity (which compares query and chunk vectors independently), a cross-encoder processes the query and chunk together and directly scores relevance. This catches semantically related chunks that cosine similarity misranks.

```python
# app/services/rerank_service.py (carried over from existing project)
from cohere import AsyncClientV2

class RerankService:
    def __init__(self) -> None:
        self._client = AsyncClientV2(api_key=os.environ["COHERE_API_KEY"])
        self._model = os.environ.get("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0")
        self._top_n = int(os.environ.get("MAX_LOCAL_CHUNKS", "8"))

    async def rerank(self, query: str, documents: list[dict], text_key: str = "text") -> list[dict]:
        if not documents:
            return documents
        texts = [d.get(text_key, "") for d in documents]
        result = await self._client.rerank(
            model=self._model,
            query=query,
            documents=texts,
            top_n=min(self._top_n, len(documents)),
        )
        reordered = []
        for r in result.results:
            doc = dict(documents[r.index])
            doc["rerank_score"] = float(r.relevance_score)
            reordered.append(doc)
        return reordered
```

**When reranking is skipped**: if `ENABLE_RERANK=false` or `COHERE_API_KEY` is not set, the pipeline falls back to the top `MAX_LOCAL_CHUNKS` by cosine score. Quality drops but the system remains functional.

**Add to `requirements.txt`**: `cohere>=5.0.0`

---

### Layer 5 — Seed entity re-anchoring post-rerank

**Source**: `graphrag-assistant/graph_rag_service.py:124-128` — carried over.

After reranking, seed entities are **recomputed from the winning chunks**, not from the original overfetch pool. This matters because chunks that were dropped by the reranker may have contributed seed entities that are irrelevant to the final context. Re-anchoring ensures graph traversal in Layer 6 is centered on the most relevant entities.

```python
# After reranking — recompute seed entities from winning chunks only
winning_chunks = await rerank_service.rerank(rewritten_query, candidates)

seed_names = []
for chunk in winning_chunks:
    seed_names.extend(chunk.metadata.get("entity_names") or [])
seed_names = list(dict.fromkeys(seed_names))[:20]   # dedup, cap at 20
```

---

### Layer 6 — 2-hop graph neighborhood traversal

**Source**: `graphrag-assistant/neo4j_store.py:275-320` — carried over with adapted node labels.

From the winning seed entities, a configurable-depth Cypher traversal fetches all neighboring entities and the relationships between them:

```python
# app/services/neo4j_store.py

async def get_entity_neighborhood(
    self, entity_names: list[str], depth: int = 2
) -> dict:
    """
    Step 1: collect all entities reachable within `depth` hops from seeds.
    Step 2: fetch all RELATED_TO relationships among discovered entities.
    """
    async with self._driver.session() as session:
        # Depth is interpolated (Neo4j does not support parameterized hop bounds)
        entities_result = await session.run(
            f"""
            UNWIND $names AS name
            MATCH (e:Entity {{name: name}})
            WITH COLLECT(DISTINCT e) AS seeds
            UNWIND seeds AS seed
            OPTIONAL MATCH (seed)-[*1..{depth}]-(neighbor:Entity)
            WITH seeds + COLLECT(DISTINCT neighbor) AS all_nodes
            UNWIND all_nodes AS node
            RETURN DISTINCT node.name AS name, node.type AS type, node.description AS description
            """,
            names=entity_names,
        )
        entities = [dict(r) async for r in entities_result]
        if not entities:
            return {"entities": [], "triples": []}

        all_names = [e["name"] for e in entities if e.get("name")]

        triples_result = await session.run(
            """
            MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity)
            WHERE a.name IN $names AND b.name IN $names
            RETURN DISTINCT a.name AS source, type(r) AS relation, b.name AS target
            """,
            names=all_names,
        )
        triples = [dict(r) async for r in triples_result]

    return {"entities": entities, "triples": triples}
```

**Config**: `GRAPH_HOP_DEPTH=2` (configurable). Depth 1 misses related policies; depth 3+ pulls in too many unrelated nodes.

---

### Layer 7 — Seed-entity triple filtering

**Source**: `graphrag-assistant/graph_rag_service.py:158-169` — carried over verbatim. This is the most critical quality guard.

After graph traversal, only triples where **both** source AND target are seed entities (from the winning chunks after re-anchoring) are included in the LLM context. 2-hop traversal reaches tangentially related entities — the triples involving those entities are noise that causes the LLM to hallucinate rules not in the retrieved text.

```python
# In graphrag_service.py — build_local_context()

if seed_names:
    triples = [
        t for t in triples
        if t.get("source") in seed_names and t.get("target") in seed_names
    ]
# Only triples where BOTH endpoints are directly from winning chunks are kept.
# 2-hop neighbor triples are discarded.
```

**Why this is critical**: without this filter, a query about "chính sách nghỉ phép" (leave policy) can cause the LLM to traverse to "Nhân viên → IN_COMMUNITY → IT Team" and hallucinate IT-related policy rules as if they apply to leave.

---

### Layer 8 — Two-level answer verification

**Source**: `graphrag-assistant/llm_service.py:200-222` — extended to two levels for multi-agent.

The existing project runs one verification pass on the final reply. The new project runs **two**:

**Level 1 — Domain agent verification** (before returning to orchestrator)
Each domain agent verifies its own answer against its own retrieved context. This catches domain-specific hallucinations before they reach synthesis.

**Level 2 — Orchestrator verification** (after synthesis)
The orchestrator verifies the final synthesized answer against the combined context. This catches synthesis-introduced errors (e.g., incorrectly merging two domain answers).

```python
# app/services/verification_service.py

VERIFICATION_PROMPT = """\
Câu hỏi: {question}

Ngữ cảnh được sử dụng để tạo câu trả lời:
{context}

Câu trả lời được tạo ra:
{answer}

Hãy đánh giá câu trả lời theo hai tiêu chí:
1. is_grounded: Mọi thông tin trong câu trả lời có được hỗ trợ trực tiếp bởi ngữ cảnh không? (true/false)
2. confidence: Mức độ tin cậy từ 1 đến 5, trong đó:
   1 = Câu trả lời phần lớn không có căn cứ
   3 = Câu trả lời một phần có căn cứ nhưng có các điểm không chắc chắn
   5 = Câu trả lời hoàn toàn có căn cứ và rõ ràng

Trả về JSON: {{"is_grounded": bool, "confidence": int, "issues": ["..."]}}"""

FALLBACK_ANSWER = (
    "Xin lỗi, tôi không tìm thấy đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này một cách chính xác. "
    "Vui lòng liên hệ trực tiếp với bộ phận liên quan hoặc kiểm tra tài liệu chính sách mới nhất."
)

class VerificationService:
    def __init__(self, llm) -> None:
        self._llm = llm   # LangChain BaseChatModel

    async def verify(self, question: str, context: str, answer: str) -> dict:
        prompt = VERIFICATION_PROMPT.format(
            question=question,
            context=context[:4000],   # truncate to control cost
            answer=answer,
        )
        try:
            response = await self._llm.ainvoke([HumanMessage(content=prompt)])
            data = json.loads(response.content)
            return {
                "is_grounded": bool(data.get("is_grounded", True)),
                "confidence": max(1, min(5, int(data.get("confidence", 3)))),
                "issues": data.get("issues", []),
            }
        except Exception:
            return {"is_grounded": True, "confidence": 5, "issues": []}

    def should_fallback(self, verification: dict) -> bool:
        return not verification["is_grounded"] or verification["confidence"] < 3
```

**In `orchestrator.py`**:
```python
# Level 1: domain agent verifies before returning
agent_result = await agent.answer(question, chunks, graph_context)
verification = await verification_service.verify(question, context_str, agent_result.answer)
if verification_service.should_fallback(verification):
    agent_result.answer = FALLBACK_ANSWER

# Level 2: orchestrator verifies synthesized answer
final = await self._synthesize(question, agent_results)
final_verification = await verification_service.verify(question, combined_context, final)
if verification_service.should_fallback(final_verification):
    final = FALLBACK_ANSWER
```

**Controlled by**: `ENABLE_ANSWER_VERIFICATION=true` (default). Set to `false` to skip both levels (lower latency, lower quality guarantee).

---

### Embedding dimension upgrade

The existing project uses `gemini-embedding-exp-03-07` at **3072 dimensions** (`config.py:17`). The original plan used `text-embedding-004` at 768 dimensions.

**Recommendation**: upgrade to 3072-dim embeddings for production. Higher dimensions significantly improve cosine similarity precision for short, semantically similar Vietnamese policy phrases. Update `settings.yaml` and `.env`:

```yaml
# settings.yaml
embeddings:
  llm:
    model: gemini-embedding-exp-03-07   # 3072-dim
```

```bash
# .env
EMBEDDING_DIM=3072
GEMINI_EMBED_MODEL=models/gemini-embedding-exp-03-07
```

Adjust `import_to_neo4j.py` to call `create_vector_indexes(driver, dim=3072)`.

---

### Configuration summary

```python
# app/config.py — retrieval quality knobs

# Overfetch + rerank
RERANK_CANDIDATE_POOL: int = 25     # vector search overfetch size
MAX_LOCAL_CHUNKS: int = 8           # final context size after rerank
ENABLE_RERANK: bool = True          # set False to skip Cohere (degrades quality)
COHERE_API_KEY: str = ""
COHERE_RERANK_MODEL: str = "rerank-multilingual-v3.0"

# Graph traversal
GRAPH_HOP_DEPTH: int = 2            # 1=direct neighbors only, 3=too noisy

# Answer verification
ENABLE_ANSWER_VERIFICATION: bool = True
# confidence threshold below which fallback is triggered
VERIFICATION_CONFIDENCE_THRESHOLD: int = 3

# Embedding
EMBEDDING_DIM: int = 3072           # upgrade from 768 for production
```

---

## 11. LangSmith Observability

The project uses LangChain throughout the agent layer, so LangSmith integration is almost zero-effort — LangChain auto-instruments all `BaseChatModel` and `Neo4jVector` calls. Non-LangChain steps (Cohere reranking, Neo4j graph traversal, entity seeding) are wrapped with `@traceable` to ensure full pipeline visibility.

---

### 11.1 Environment variables

Add to `.env` and `docker-compose.yml`:

```bash
# ─── LangSmith ────────────────────────────────────────────────────────────────
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=new-rag-2026
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com   # default; change for self-hosted
```

When `LANGCHAIN_TRACING_V2=true`, every `chain.ainvoke()`, `llm.ainvoke()`, and `Neo4jVector.similarity_search_with_score()` call is automatically traced. No other code changes needed for LangChain components.

To **disable** tracing in production without removing the env var:
```bash
LANGCHAIN_TRACING_V2=false
```

---

### 11.2 Auto-traced components (no code changes)

| Component | Trace name (auto) | What you see |
|---|---|---|
| `create_chat_model()` | `ChatGoogleGenerativeAI` / `ChatOpenAI` | prompt, output, token counts, latency |
| `DOMAIN_AGENT_PROMPT \| llm` | `RunnableSequence` | full prompt with injected context |
| `Neo4jVector.similarity_search_with_score()` | `Neo4jVector` | query, k, results count |
| `ConversationBufferWindowMemory` | `ConversationBufferWindowMemory` | loaded history |
| `ChatPromptTemplate.ainvoke()` | `ChatPromptTemplate` | formatted message |

A single chat turn produces a trace tree like:
```
OrchestratorAgent.run                        total ~340ms
  ├── rewrite_query          (LLM)            80ms  input/output shown
  ├── classify_domains       (LLM)            60ms  ["hr", "benefits"]
  ├── Neo4jVector.search                      45ms  k=25
  ├── cohere_rerank          (@traceable)     90ms  25→8 results
  ├── neo4j_entity_seeding   (@traceable)     35ms  entity names, hit counts
  ├── neo4j_graph_traversal  (@traceable)     40ms  entities, triples count
  ├── HRAgent.answer         (LLM chain)     120ms  parallel
  ├── BenefitsAgent.answer   (LLM chain)     115ms  parallel
  ├── verify_domain_hr       (@traceable)     70ms  is_grounded, confidence
  ├── verify_domain_benefits (@traceable)     68ms  is_grounded, confidence
  ├── synthesize             (LLM)            95ms  combined answer
  └── verify_final           (@traceable)     70ms  final grounding check
```

---

### 11.3 `@traceable` on non-LangChain steps

Steps that are NOT LangChain objects must be explicitly wrapped. Add `@traceable` to four locations:

#### `app/services/rerank_service.py`

```python
from langsmith import traceable

class RerankService:
    @traceable(
        name="cohere_rerank",
        run_type="retriever",
        metadata={"model": "rerank-multilingual-v3.0"},
    )
    async def rerank(
        self,
        query: str,
        documents: list[dict],
        text_key: str = "text",
    ) -> list[dict]:
        """Cross-encoder rerank. @traceable logs input count, output count, top score."""
        if not documents:
            return documents
        texts = [d.get(text_key, "") for d in documents]
        top_n = min(self._top_n, len(documents))
        try:
            result = await self._client.rerank(
                model=self._model,
                query=query,
                documents=texts,
                top_n=top_n,
            )
        except Exception as exc:
            # LangSmith captures the exception automatically when @traceable is used
            raise
        reordered = []
        for r in result.results:
            doc = dict(documents[r.index])
            doc["rerank_score"] = float(r.relevance_score)
            reordered.append(doc)
        return reordered
```

#### `app/services/neo4j_store.py` — entity seeding

```python
from langsmith import traceable

class Neo4jStore:
    @traceable(
        name="neo4j_entity_seeding",
        run_type="retriever",
        metadata={"store": "neo4j"},
    )
    async def get_chunks_by_entity_names(
        self,
        entity_names: list[str],
        k: int = 5,
        min_entity_hits: int = 2,
    ) -> list[dict]:
        """Entity-augmented retrieval. @traceable logs entity_names, min_hits, result count."""
        ...  # implementation from Section 10, Layer 3

    @traceable(
        name="neo4j_graph_traversal",
        run_type="retriever",
        metadata={"store": "neo4j"},
    )
    async def get_entity_neighborhood(
        self,
        entity_names: list[str],
        depth: int = 2,
    ) -> dict:
        """Graph traversal. @traceable logs entity_names, depth, entities+triples counts."""
        ...  # implementation from Section 10, Layer 6

    @traceable(
        name="neo4j_specific_entity_filter",
        run_type="retriever",
    )
    async def get_specific_entity_names(self, entity_names: list[str]) -> list[str]:
        """Type filter. @traceable logs input vs output count (how many are specific types)."""
        ...  # implementation from Section 10, Layer 3
```

#### `app/services/verification_service.py`

```python
from langsmith import traceable

class VerificationService:
    @traceable(
        name="answer_verification",
        run_type="llm",
        metadata={"type": "grounding_check"},
    )
    async def verify(
        self,
        question: str,
        context: str,
        answer: str,
        domain: str | None = None,   # "hr", "benefits", "final_synthesis", etc.
    ) -> dict:
        """
        Grounding check. @traceable logs:
        - inputs: question, context (truncated), answer, domain
        - output: is_grounded, confidence, issues
        LangSmith shows verification results per domain and for final synthesis.
        """
        ...  # implementation from Section 10, Layer 8
```

#### `app/agents/orchestrator.py`

Wrap `_classify` and `_synthesize` explicitly so they appear as named nodes in the trace tree:

```python
from langsmith import traceable

class OrchestratorAgent:
    @traceable(name="orchestrator_classify", run_type="chain")
    async def _classify(self, question: str, session_history: str) -> list[str]:
        ...

    @traceable(name="orchestrator_synthesize", run_type="chain")
    async def _synthesize(self, question: str, agent_results: list) -> str:
        ...

    @traceable(name="orchestrator_run", run_type="chain")
    async def run(self, question: str, session_history: str = "") -> OrchestratorResult:
        ...
```

---

### 11.4 `run_name` and `tags` for filtering

Pass `run_name` and `tags` via LangChain's `RunnableConfig` on each chat request so you can filter traces by session, domain, or LLM provider in the LangSmith UI:

```python
# app/routers/chat.py

from langchain_core.runnables.config import RunnableConfig

@router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    config = RunnableConfig(
        run_name=f"chat/{body.session_id[:8]}",
        tags=[
            f"provider:{settings.LLM_PROVIDER}",
            f"session:{body.session_id[:8]}",
        ],
        metadata={
            "session_id": body.session_id,
            "llm_provider": settings.LLM_PROVIDER,
            "project": "new-rag-2026",
        },
    )
    result = await orchestrator.run(
        question=body.message,
        session_history=session_history_str,
        config=config,   # propagated to all LangChain calls in the chain
    )
    ...
```

Pass `config` through `OrchestratorAgent.run()` and each `agent.answer()` call so it propagates to all nested LangChain invocations.

---

### 11.5 LangSmith evaluation with existing eval sets

The project has eval question sets at `graphrag-assistant/eval-sets/eval_questions.json`. Use them directly with LangSmith's evaluator:

```python
# scripts/run_eval.py

import json
from langsmith import Client
from langsmith.evaluation import evaluate, LangChainStringEvaluator

client = Client()

# Load golden Q&A pairs from existing eval sets
with open("eval_questions.json") as f:
    questions = json.load(f)

# Create dataset (run once)
dataset = client.create_dataset("new-rag-2026-golden-qa")
for q in questions:
    client.create_example(
        inputs={"question": q["question"]},
        outputs={"answer": q["expected_answer"]},
        dataset_id=dataset.id,
    )

# Define the system under test
async def answer_question(inputs: dict) -> dict:
    result = await orchestrator.run(inputs["question"])
    return {"answer": result.final_answer}

# Run evaluation — LangSmith calls answer_question for each example
results = evaluate(
    answer_question,
    data="new-rag-2026-golden-qa",
    evaluators=[
        LangChainStringEvaluator("qa"),            # LLM-as-judge: correctness
        LangChainStringEvaluator("criteria",       # custom rubric
            config={"criteria": "relevance"}),
    ],
    experiment_prefix="v2-gemini-3072dim",         # label for this run
)
print(results.to_pandas()[["input", "output", "feedback.qa"]].head(20))
```

Run after each significant change (chunk size, hop depth, LLM provider) to catch retrieval regressions before deployment.

---

### 11.6 `requirements.txt` addition

```
langsmith>=0.1.0
```

---

### 11.7 Summary — what gets traced

| Step | How traced | LangSmith run_type |
|---|---|---|
| Orchestrator entry | `@traceable` | `chain` |
| Query rewriting | auto (LangChain LLM) | `llm` |
| Domain classification | auto (LangChain LLM) | `llm` |
| Vector search | auto (`Neo4jVector`) | `retriever` |
| Cohere reranking | `@traceable` | `retriever` |
| Entity seeding (type-aware) | `@traceable` | `retriever` |
| Graph traversal | `@traceable` | `retriever` |
| Domain agent answer | auto (LangChain chain) | `chain` + `llm` |
| Answer verification | `@traceable` | `llm` |
| Synthesis | auto (LangChain LLM) | `llm` |
| Final verification | `@traceable` | `llm` |

Every step is visible, latency and token counts are tracked, and evaluation against golden Q&A sets is one script away.

---

## 12. Neo4j Schema

### Node Types

| Label | Key Properties | Description |
|---|---|---|
| `Entity` | `id`, `name`, `type`, `description`, `embedding` | Knowledge graph entity (person, org, policy, etc.) |
| `Community` | `id`, `level`, `title`, `summary`, `embedding` | Leiden community cluster with summary |
| `TextUnit` | `id`, `text`, `document_id` | Chunked document passage |
| `Document` | `id`, `filename`, `ingested_at` | Source document metadata |
| `Covariate` | `id`, `subject_id`, `type`, `value` | Optional: claim/fact extractions |

### Relationship Types

| Type | Pattern | Description |
|---|---|---|
| `RELATED_TO` | `(Entity)-[:RELATED_TO {description, weight}]->(Entity)` | Knowledge graph edge |
| `IN_COMMUNITY` | `(Entity)-[:IN_COMMUNITY]->(Community)` | Entity's Leiden cluster membership |
| `MENTIONS` | `(TextUnit)-[:MENTIONS]->(Entity)` | Text chunk mentions entity |
| `PART_OF` | `(TextUnit)-[:PART_OF]->(Document)` | Text chunk belongs to document |

### Cypher: Create Schema Constraints and Indexes

```cypher
-- Uniqueness constraints
CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT community_id IF NOT EXISTS FOR (c:Community) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT text_unit_id IF NOT EXISTS FOR (t:TextUnit) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE;

-- Property indexes for lookup
CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name);
CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type);
CREATE INDEX community_level IF NOT EXISTS FOR (c:Community) ON (c.level);
CREATE INDEX text_unit_document IF NOT EXISTS FOR (t:TextUnit) ON (t.document_id);

-- Vector indexes (created by import_to_neo4j.py, shown here for reference)
CREATE VECTOR INDEX entity_embedding IF NOT EXISTS
FOR (e:Entity) ON (e.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX community_embedding IF NOT EXISTS
FOR (c:Community) ON (c.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
}};
```

### Useful Query Patterns

```cypher
-- Find top similar entities to a query vector
CALL db.index.vector.queryNodes('entity_embedding', 10, $queryVector)
YIELD node, score
RETURN node.name, node.type, node.description, score;

-- Find all entities in a community and their relationships
MATCH (e:Entity)-[:IN_COMMUNITY]->(c:Community {id: $communityId})
OPTIONAL MATCH (e)-[r:RELATED_TO]-(e2:Entity)
RETURN e, r, e2;

-- Find text units that discuss a specific entity
MATCH (t:TextUnit)-[:MENTIONS]->(e:Entity {name: $entityName})
RETURN t.text, t.document_id
LIMIT 10;

-- Cross-domain: Find all policies related to a person
MATCH (p:Entity {type: 'người'})-[:RELATED_TO]-(pol:Entity {type: 'chính sách'})
RETURN p.name, pol.name, pol.description;
```

---

## 13. API Endpoints

All routes prefixed `/api/v1`. Inherits all 6 endpoints from PLAN.md plus one new endpoint.

### Inherited Endpoints (unchanged from PLAN.md)

- `POST /api/v1/session` — create session
- `DELETE /api/v1/session/{session_id}` — delete session
- `POST /api/v1/admin/ingest` — upload document
- `POST /api/v1/admin/index` — trigger indexing + post-import to Neo4j
- `GET /api/v1/admin/status` — poll indexing status
- `GET /health` — liveness check (now also reports `neo4j_connected`)

### Modified: `POST /api/v1/chat`

**Request** (adds `domain_hint` optional field):
```json
{
  "session_id": "uuid4",
  "message": "Chính sách nghỉ phép và bảo hiểm y tế của công ty như thế nào?",
  "mode": "auto"
}
```

`mode` options: `"auto"` (orchestrator decides local/global), `"local"`, `"global"`.

**Response** (adds agent metadata):
```json
{
  "reply": "Câu trả lời tổng hợp...",
  "sources": [...],
  "query_type": "global",
  "session_id": "uuid4",
  "domain_keys": ["hr", "benefits"],
  "agent_count": 2
}
```

### New: `GET /api/v1/chat/{session_id}/agent_trace`

Returns the agent invocation trace for the most recent turn in a session. Used by the admin debug panel.

**Response**:
```json
{
  "session_id": "uuid4",
  "last_question": "Chính sách nghỉ phép và bảo hiểm y tế?",
  "domain_keys": ["hr", "benefits"],
  "search_mode": "global",
  "agent_results": [
    {
      "domain_key": "hr",
      "domain_name_vi": "Nhân sự",
      "answer": "Về chính sách nghỉ phép: nhân viên được hưởng 12 ngày phép năm...",
      "sources_count": 3
    },
    {
      "domain_key": "benefits",
      "domain_name_vi": "Phúc lợi",
      "answer": "Về bảo hiểm y tế: công ty đóng 3% lương cơ bản cho bảo hiểm y tế...",
      "sources_count": 2
    }
  ]
}
```

The session service stores the `OrchestratorResult` from the last turn per session. The `/agent_trace` endpoint reads from this stored result.

---

## 14. Environment Variables

```bash
# .env.example

# ─── LLM Provider (agent layer) ───────────────────────────────────────────────
LLM_PROVIDER=gemini              # gemini | openai | siliconflow

# ─── Gemini ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY=
GEMINI_CHAT_MODEL=gemini-2.0-flash
GEMINI_EMBED_MODEL=text-embedding-004

# ─── OpenAI ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY=
OPENAI_CHAT_MODEL=gpt-4o
OPENAI_EMBED_MODEL=text-embedding-3-small

# ─── Siliconflow ──────────────────────────────────────────────────────────────
SILICONFLOW_API_KEY=
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3
SILICONFLOW_EMBED_MODEL=BAAI/bge-large-zh-v1.5

# ─── GraphRAG (indexing LLM — always Gemini or OpenAI via settings.yaml) ──────
GRAPHRAG_ROOT=./graphrag_workspace
GRAPHRAG_QUERY_MODEL=gemini-2.0-flash  # model used by graphrag_service.py query layer

# ─── Neo4j ────────────────────────────────────────────────────────────────────
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=

# ─── Embedding dimensions ─────────────────────────────────────────────────────
# 768 for Gemini text-embedding-004
# 1536 for OpenAI text-embedding-3-small
# 1024 for BAAI/bge-large-zh-v1.5 (Siliconflow)
EMBEDDING_DIM=768

# ─── LangSmith observability ─────────────────────────────────────────────────
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=new-rag-2026
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

# ─── Retrieval quality ────────────────────────────────────────────────────────
ENABLE_RERANK=true
COHERE_API_KEY=
COHERE_RERANK_MODEL=rerank-multilingual-v3.0
RERANK_CANDIDATE_POOL=25
MAX_LOCAL_CHUNKS=8
GRAPH_HOP_DEPTH=2
ENABLE_ANSWER_VERIFICATION=true
VERIFICATION_CONFIDENCE_THRESHOLD=3

# ─── Session ──────────────────────────────────────────────────────────────────
SESSION_TTL_MINUTES=60

# ─── CORS ─────────────────────────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:5173

# ─── App ──────────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
```

### `config.py` (Pydantic Settings)

```python
# backend/app/config.py

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Agent-layer LLM
    LLM_PROVIDER: str = "gemini"

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_CHAT_MODEL: str = "gemini-2.0-flash"
    GEMINI_EMBED_MODEL: str = "text-embedding-004"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = "gpt-4o"
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"

    # Siliconflow
    SILICONFLOW_API_KEY: str = ""
    SILICONFLOW_MODEL: str = "deepseek-ai/DeepSeek-V3"
    SILICONFLOW_EMBED_MODEL: str = "BAAI/bge-large-zh-v1.5"

    # GraphRAG
    GRAPHRAG_ROOT: str = "./graphrag_workspace"
    GRAPHRAG_QUERY_MODEL: str = "gemini-2.0-flash"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""

    # Embedding
    EMBEDDING_DIM: int = 768

    # Session
    SESSION_TTL_MINUTES: int = 60

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

---

## 15. `requirements.txt`

```
# ─── Web framework ────────────────────────────────────────────────────────────
fastapi>=0.111.0
uvicorn[standard]>=0.29.0

# ─── Microsoft GraphRAG ───────────────────────────────────────────────────────
graphrag>=2.0.0,<3.0.0

# ─── Neo4j ────────────────────────────────────────────────────────────────────
neo4j>=5.0.0

# ─── LangChain ────────────────────────────────────────────────────────────────
langchain>=0.3.0
langchain-core>=0.3.0
langchain-google-genai>=2.0.0    # Gemini chat + embeddings
langchain-openai>=0.2.0          # OpenAI + Siliconflow (OpenAI-compatible)
langchain-neo4j>=0.3.0           # Neo4j vector store
langchain-community>=0.3.0       # ConversationBufferWindowMemory + utilities

# ─── LLM SDKs (required by LangChain providers) ───────────────────────────────
google-generativeai>=0.8.0       # required by langchain-google-genai
openai>=1.50.0                   # required by langchain-openai
httpx>=0.27.0                    # Siliconflow fallback + general HTTP

# ─── Retrieval quality ────────────────────────────────────────────────────────
cohere>=5.0.0                    # cross-encoder reranking (rerank-multilingual-v3.0)

# ─── LangSmith observability ─────────────────────────────────────────────────
langsmith>=0.1.0                 # @traceable + evaluation runner

# ─── Data / Parquet (for import_to_neo4j.py) ─────────────────────────────────
pandas>=2.0.0
pyarrow>=14.0.0

# ─── Pydantic / config ────────────────────────────────────────────────────────
pydantic-settings>=2.0.0
pydantic>=2.0.0

# ─── File handling ────────────────────────────────────────────────────────────
python-multipart>=0.0.9
aiofiles>=24.0.0

# ─── Document conversion ──────────────────────────────────────────────────────
pymupdf>=1.24.0           # PDF → text
python-docx>=1.1.0        # DOCX → text

# ─── Misc ─────────────────────────────────────────────────────────────────────
python-dotenv>=1.0.0
structlog>=24.0.0

# ─── LanceDB (kept for Option B intermediate step; remove for full Option A) ──
lancedb>=0.8.0
```

**Frontend** (`frontend/package.json` — same as PLAN.md; add one dependency):
```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "zustand": "^4.5.0",
    "react-markdown": "^9.0.0",
    "react-dropzone": "^14.2.0",
    "axios": "^1.7.0"
  }
}
```

---

## 16. `docker-compose.yml`

Three services: `neo4j` (with APOC), `backend`, `frontend`.

```yaml
# docker-compose.yml
version: "3.9"

services:

  neo4j:
    image: neo4j:5.20-community
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-changeme}
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_dbms_security_procedures_unrestricted: "apoc.*,gds.*"
      NEO4J_server_memory_heap_initial__size: "512m"
      NEO4J_server_memory_heap_max__size: "2g"
    ports:
      - "7474:7474"   # Neo4j Browser
      - "7687:7687"   # Bolt
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "neo4j", "status"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      - LLM_PROVIDER=${LLM_PROVIDER:-gemini}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - SILICONFLOW_API_KEY=${SILICONFLOW_API_KEY:-}
      - SILICONFLOW_MODEL=${SILICONFLOW_MODEL:-deepseek-ai/DeepSeek-V3}
      - GRAPHRAG_ROOT=/app/graphrag_workspace
      - GRAPHRAG_QUERY_MODEL=${GRAPHRAG_QUERY_MODEL:-gemini-2.0-flash}
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=${NEO4J_PASSWORD:-changeme}
      - EMBEDDING_DIM=${EMBEDDING_DIM:-768}
      - SESSION_TTL_MINUTES=${SESSION_TTL_MINUTES:-60}
      - CORS_ORIGINS=http://localhost:80
      - LANGCHAIN_TRACING_V2=${LANGCHAIN_TRACING_V2:-false}
      - LANGCHAIN_API_KEY=${LANGCHAIN_API_KEY:-}
      - LANGCHAIN_PROJECT=${LANGCHAIN_PROJECT:-new-rag-2026}
      - LANGCHAIN_ENDPOINT=${LANGCHAIN_ENDPOINT:-https://api.smith.langchain.com}
    volumes:
      - graphrag_data:/app/graphrag_workspace
      - documents_data:/app/data/documents
    ports:
      - "8000:8000"
    depends_on:
      neo4j:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  neo4j_data:
  neo4j_logs:
  graphrag_data:
  documents_data:
```

### `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p graphrag_workspace/input graphrag_workspace/output data/documents

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `frontend/Dockerfile` and `nginx.conf`

Same as PLAN.md (unchanged).

---

## 17. Comparison Table

| Dimension | Custom `graphrag-assistant` | PLAN.md (MSFT GraphRAG, Parquet) | **PLAN V2 (Multi-agent + Neo4j)** |
|---|---|---|---|
| **Agent architecture** | Single agent | Single agent | OrchestratorAgent + 7 domain agents |
| **Answer quality (domain-specific)** | Moderate (generalist) | Moderate (generalist) | **High** (specialist per domain) |
| **Cross-domain questions** | Weak | Weak | **Strong** (parallel fan-out + synthesis) |
| **Graph storage** | Neo4j (custom schema) | Parquet + LanceDB (ephemeral) | **Neo4j** (persistent, Cypher-queryable) |
| **Vector search** | Neo4j vector index | LanceDB | **Neo4j vector index** |
| **Graph visualization** | Neo4j Browser | None | **Neo4j Browser** |
| **Language** | Mixed (EN/VI prompts) | English prompts | **Vietnamese throughout** |
| **LLM flexibility** | Gemini only | Gemini only | **Gemini / OpenAI / Siliconflow** |
| **Extraction quality** | Custom (team-maintained) | MSFT GraphRAG | **MSFT GraphRAG + Vietnamese templates** |
| **Infrastructure** | Neo4j + backend + frontend | Backend + frontend only | Neo4j + backend + frontend |
| **Maintenance burden** | High | Low | Low (MSFT core) + Medium (agents) |
| **Incremental indexing** | Manual delta | Built-in (2.x) | Built-in + re-import script |
| **Deployment complexity** | Medium | Low | **Medium** (3 Docker services) |

---

## 18. Implementation Order

Work through these steps sequentially. Each step produces a testable artifact before moving to the next.

**1. Project scaffold**
Create directory structure as shown in Section 1. Create `requirements.txt`, `.env.example`. Initialize Python venv and install packages. Verify `import graphrag` and `import neo4j` work.

**2. Neo4j setup**
Start Neo4j via `docker compose up neo4j`. Open Neo4j Browser at `http://localhost:7474`. Run the schema creation Cypher from Section 8 (constraints + indexes). Verify connectivity with a simple `MATCH (n) RETURN count(n)`.

**3. GraphRAG workspace init**
```bash
graphrag init --root ./graphrag_workspace
```
Copy the three Vietnamese prompt files from Section 4 into `graphrag_workspace/prompts/`. Write `settings.yaml` from Section 3. Place 3–5 test `.txt` files in `graphrag_workspace/input/`. Run `graphrag index --root ./graphrag_workspace`. Verify Parquet artifacts in `output/artifacts/`.

**4. `import_to_neo4j.py`**
Implement the import script from Section 2. Run it against the test artifacts:
```bash
python scripts/import_to_neo4j.py \
  --artifacts ./graphrag_workspace/output/artifacts \
  --uri bolt://localhost:7687 \
  --password changeme
```
Verify in Neo4j Browser: `MATCH (n) RETURN labels(n), count(n)`.

**5. `config.py`**
Implement pydantic settings from Section 10. Load from `.env`. Smoke test: `python -c "from app.config import settings; print(settings.LLM_PROVIDER)"`.

**6. `llm_service.py`**
Implement `BaseLLMService`, `GeminiLLMService`, `OpenAILLMService`, `SiliconflowLLMService`, and `create_llm_service()` factory from Section 5. Test each provider:
```bash
LLM_PROVIDER=gemini python -c "
import asyncio; from app.services.llm_service import create_llm_service
llm = create_llm_service()
print(asyncio.run(llm.chat([{'role':'user','content':'Xin chào'}])))
"
```

**7. `neo4j_store.py`**
Implement `Neo4jStore` and `_Neo4jEntityVectorStoreAdapter` from Section 7. Test vector search:
```python
import asyncio
from app.services.neo4j_store import Neo4jStore
store = Neo4jStore()
asyncio.run(store.connect())
# embed a test string then search
```

**8. `graphrag_service.py`**
Implement `GraphRAGService` from Section 7 using the Neo4j adapter. Test:
```python
import asyncio
from app.services.graphrag_service import GraphRAGService, SearchMode
# ...
result = asyncio.run(svc.search("Chính sách bảo mật là gì?", SearchMode.LOCAL))
print(result["reply"])
```

**9. `domains.py` + `system_prompts.py` + `orchestrator_prompts.py`**
Implement domain registry and all Vietnamese prompt strings from Sections 6.

**10. `base_agent.py` + domain agents**
Implement `BaseDomainAgent` ABC. Implement all 7 domain agents (`HRAgent`, `BenefitsAgent`, `ITAgent`, `FinanceAgent`, `ComplianceAgent`, `ProceduresAgent`, `GeneralAgent`). Unit test one agent in isolation.

**11. `orchestrator.py`**
Implement `OrchestratorAgent`. Test classification:
```python
# Test single-domain routing
result = asyncio.run(orch.run("Chính sách nghỉ phép năm là gì?"))
assert result.domain_keys == ["hr"]

# Test multi-domain routing
result = asyncio.run(orch.run("Nghỉ phép thai sản và bảo hiểm y tế quy định thế nào?"))
assert len(result.domain_keys) > 1
```

**12. `session_service.py`**
Port from PLAN.md with one addition: store `last_orchestrator_result: OrchestratorResult | None` on each `Session` for the `/agent_trace` endpoint.

**13. `schemas.py`**
Pydantic request/response models for all endpoints including the new `AgentTraceResponse`.

**14. Routers**
Implement in order: `health.py` → `session.py` → `admin.py` (ingest + index → triggers `import_to_neo4j.py` on completion → calls `graphrag_service.reload()`) → `chat.py` (calls `OrchestratorAgent.run()`).

**15. `main.py`**
FastAPI app with lifespan (connects Neo4j, loads GraphRAG if artifacts exist), CORS, router registration, TTL cleanup loop.

**16. Integration smoke test**
With all services running:
1. Upload 5 real company policy documents via `POST /admin/ingest`
2. Trigger `POST /admin/index` — wait for completion (poll `/admin/status`)
3. Run `python scripts/import_to_neo4j.py` if not auto-triggered
4. Ask 5 single-domain questions — verify `domain_keys` has 1 entry, answers are in Vietnamese
5. Ask 2 cross-domain questions — verify `domain_keys` has multiple entries, `/agent_trace` returns per-domain answers
6. Switch `LLM_PROVIDER=siliconflow` and repeat questions — verify same behavior, different provider

**17. Frontend**
Port frontend from PLAN.md. Add `/agent_trace` debug panel (toggle-able, shows per-domain answers). Add domain badge display on assistant messages.

**18. Docker**
Write `docker-compose.yml` from Section 12. Test `docker compose up` end-to-end including Neo4j health check gating backend startup.

**19. Final verification**
- Neo4j Browser: confirm entity graph is populated and vector indexes are online
- Test `LLM_PROVIDER` switching without restart (restart required — provider is set at startup via `create_llm_service()`)
- Load test: 10 concurrent chat requests; verify `asyncio.gather` fan-out does not block
- Check Vietnamese extraction quality: read a community report from Neo4j and verify it is in Vietnamese
