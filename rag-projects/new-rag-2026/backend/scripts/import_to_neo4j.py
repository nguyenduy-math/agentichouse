"""
Bulk-import GraphRAG Parquet artifacts into Neo4j.
Run after `graphrag index` completes.

Usage:
    python scripts/import_to_neo4j.py \\
        --artifacts ./graphrag_workspace/output \\
        --uri bolt://localhost:7687 \\
        --user neo4j \\
        --password <password>

Document-level refresh strategy
---------------------------------
graphrag rebuilds *all* Parquet files on every index run with new UUIDs for
Community and TextUnit nodes, but entity names stay stable.  To avoid stale
data accumulating across re-indexes we use two-phase cleanup:

  Phase 1 — transient nodes (Community, TextUnit): always wiped and recreated.
  Phase 2 — entity diff: Entity nodes whose stable-ID is not in the new Parquet
             are deleted (they belong to a removed/replaced document section).
             Entity nodes still present are updated in place via MERGE.

Entity stable-IDs are SHA-256 hashes of the normalised entity title so the
same real-world entity survives a re-index of any document that mentions it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import GraphRAG Parquet artifacts into Neo4j")
    p.add_argument("--artifacts", required=True, help="Path to GraphRAG output directory")
    p.add_argument("--uri", default="bolt://localhost:7687", help="Neo4j Bolt URI")
    p.add_argument("--user", default="neo4j", help="Neo4j username")
    p.add_argument("--password", required=True, help="Neo4j password")
    p.add_argument(
        "--embedding-dim",
        type=int,
        default=3072,
        help="Embedding dimensions for vector indexes (3072 for gemini-embedding-001, "
             "768 for text-embedding-004, 1024 for Siliconflow, 1536 for OpenAI)",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BATCH_SIZE = 500


def stable_entity_id(name: str) -> str:
    """Return a deterministic 32-char hex ID for an entity name.

    graphrag uppercases entity titles (e.g. "THE COMPANY"), so we normalise
    to uppercase before hashing to ensure the same real-world entity always
    maps to the same Neo4j node across index runs.
    """
    return hashlib.sha256(name.upper().strip().encode()).hexdigest()[:32]


def _embedding_list(val) -> list[float] | None:
    """Parse embedding from Parquet (may be list, np.ndarray, or JSON string)."""
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return None
    try:
        lst = list(val)
        return lst if lst else None
    except TypeError:
        return None


def _array_to_list(val) -> list:
    """Safely convert a column value that may be a numpy array, list, str, or None."""
    if val is None:
        return []
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    try:
        return list(val)
    except TypeError:
        return []


# ---------------------------------------------------------------------------
# Cleanup helpers
# ---------------------------------------------------------------------------

def delete_transient_nodes(driver) -> None:
    """Wipe Community and TextUnit nodes — they get new UUIDs on every graphrag run."""
    with driver.session() as session:
        for label in ("Community", "TextUnit"):
            deleted = 1
            while deleted > 0:
                result = session.run(
                    f"MATCH (n:{label}) WITH n LIMIT 1000 DETACH DELETE n RETURN count(n) AS d"
                )
                deleted = result.single()["d"]
    print("Cleared transient nodes (Community, TextUnit).")


def delete_stale_entities(driver, entity_df: pd.DataFrame) -> None:
    """Remove Entity nodes whose stable-ID is no longer present in the new Parquet.

    These are entities that existed in a previous document version but are
    absent from the freshly rebuilt graph — i.e. the document-level cleanup.
    Entity nodes shared across multiple documents are preserved because their
    stable-ID appears in the new Parquet (contributed by the other documents).
    """
    current_ids = [stable_entity_id(str(row["title"])) for _, row in entity_df.iterrows()]
    with driver.session() as session:
        result = session.run(
            "MATCH (e:Entity) WHERE NOT e.id IN $ids DETACH DELETE e RETURN count(e) AS d",
            ids=current_ids,
        )
        deleted = result.single()["d"]
    if deleted:
        print(f"Removed {deleted} stale entity node(s).")


# ---------------------------------------------------------------------------
# Import functions
# ---------------------------------------------------------------------------

def import_entities(tx, df: pd.DataFrame) -> None:
    """MERGE Entity nodes using stable name-derived IDs."""
    records = []
    for _, row in df.iterrows():
        name = str(row.get("title", "") or "")
        records.append({
            "id": stable_entity_id(name),
            "name": name,
            "type": str(row.get("type", "") or ""),
            "description": str(row.get("description", "") or ""),
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
    """MERGE RELATED_TO relationships using stable entity IDs.

    relationships.parquet stores entity names (not UUIDs) in source/target,
    so we can compute stable IDs directly without a lookup table.
    """
    records = []
    for _, row in df.iterrows():
        records.append({
            "source_id": stable_entity_id(str(row["source"])),
            "target_id": stable_entity_id(str(row["target"])),
            "description": str(row.get("description", "") or ""),
            "weight": float(row.get("weight", 1.0) or 1.0),
        })
    tx.run(
        """
        UNWIND $records AS r
        MATCH (src:Entity {id: r.source_id})
        MATCH (tgt:Entity {id: r.target_id})
        MERGE (src)-[rel:RELATED_TO]->(tgt)
        SET rel.description = r.description,
            rel.weight = r.weight
        """,
        records=records,
    )


def import_communities(tx, df: pd.DataFrame, report_df: pd.DataFrame) -> None:
    """MERGE Community nodes joined with community report summaries.

    Join on the 'community' integer (shared key) — NOT on 'id' because both
    DataFrames have an 'id' column with different UUID values.
    """
    report_cols = [c for c in ["community", "title", "summary", "full_content"] if c in report_df.columns]
    merged = df.merge(report_df[report_cols], on="community", how="left")

    records = []
    for _, row in merged.iterrows():
        records.append({
            "id": str(row["id"]),
            "level": int(row.get("level", 0) or 0),
            "title": str(row.get("title", "") or ""),
            "summary": str(row.get("summary", "") or ""),
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


def import_community_membership(
    tx, community_df: pd.DataFrame, uuid_to_stable: dict[str, str]
) -> None:
    """Create IN_COMMUNITY edges from Entity → Community.

    community_df.entity_ids contains graphrag UUIDs; we translate them to
    stable entity IDs via the pre-built uuid_to_stable mapping.
    """
    records = []
    for _, row in community_df.iterrows():
        community_id = str(row["id"])
        for eid_uuid in _array_to_list(row.get("entity_ids")):
            stable_id = uuid_to_stable.get(str(eid_uuid))
            if stable_id:
                records.append({"entity_id": stable_id, "community_id": community_id})
    if not records:
        return
    for i in range(0, len(records), BATCH_SIZE):
        tx.run(
            """
            UNWIND $records AS r
            MATCH (e:Entity {id: r.entity_id})
            MATCH (c:Community {id: r.community_id})
            MERGE (e)-[:IN_COMMUNITY]->(c)
            """,
            records=records[i : i + BATCH_SIZE],
        )


def import_text_units(tx, df: pd.DataFrame) -> None:
    """CREATE TextUnit nodes (always fresh — UUIDs change every graphrag run)."""
    records = []
    for _, row in df.iterrows():
        doc_ids = _array_to_list(row.get("document_ids"))
        records.append({
            "id": str(row["id"]),
            "text": str(row.get("text", "") or ""),
            "document_id": str(doc_ids[0]) if doc_ids else "",
        })
    tx.run(
        """
        UNWIND $records AS r
        CREATE (t:TextUnit {id: r.id})
        SET t.text = r.text,
            t.document_id = r.document_id
        """,
        records=records,
    )


def import_text_unit_entity_links(
    tx, entity_df: pd.DataFrame
) -> None:
    """Create MENTIONS edges from TextUnit → Entity using stable entity IDs."""
    records = []
    for _, row in entity_df.iterrows():
        stable_id = stable_entity_id(str(row.get("title", "") or ""))
        for tu_id in _array_to_list(row.get("text_unit_ids")):
            records.append({"tu_id": str(tu_id), "entity_id": stable_id})
    if not records:
        return
    for i in range(0, len(records), BATCH_SIZE):
        tx.run(
            """
            UNWIND $records AS r
            MATCH (t:TextUnit {id: r.tu_id})
            MATCH (e:Entity {id: r.entity_id})
            MERGE (t)-[:MENTIONS]->(e)
            """,
            records=records[i : i + BATCH_SIZE],
        )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def create_schema_constraints(driver) -> None:
    with driver.session() as session:
        stmts = [
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT community_id IF NOT EXISTS FOR (c:Community) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT text_unit_id IF NOT EXISTS FOR (t:TextUnit) REQUIRE t.id IS UNIQUE",
            "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
            "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)",
            "CREATE INDEX community_level IF NOT EXISTS FOR (c:Community) ON (c.level)",
            "CREATE INDEX text_unit_document IF NOT EXISTS FOR (t:TextUnit) ON (t.document_id)",
        ]
        for stmt in stmts:
            try:
                session.run(stmt)
            except Exception as exc:
                print(f"Warning: {exc}")
    print("Schema constraints and indexes ensured.")


def create_vector_indexes(driver, dim: int = 3072) -> None:
    with driver.session() as session:
        for label, prop in (("Entity", "e.embedding"), ("Community", "c.embedding")):
            var = label[0].lower()
            try:
                session.run(
                    f"""
                    CREATE VECTOR INDEX {label.lower()}_embedding IF NOT EXISTS
                    FOR ({var}:{label}) ON ({prop})
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {dim},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                    """
                )
            except Exception as exc:
                print(f"Warning ({label} vector index): {exc}")
    print(f"Vector indexes ensured (dim={dim}).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    artifacts = Path(args.artifacts)

    if not artifacts.is_dir():
        raise SystemExit(f"Artifacts directory not found: {artifacts}")

    print(f"Connecting to Neo4j at {args.uri}...")
    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))

    create_schema_constraints(driver)

    print("Reading Parquet artifacts...")
    entity_df = pd.read_parquet(artifacts / "entities.parquet")
    rel_df = pd.read_parquet(artifacts / "relationships.parquet")
    text_unit_df = pd.read_parquet(artifacts / "text_units.parquet")

    community_file = artifacts / "communities.parquet"
    report_file = artifacts / "community_reports.parquet"
    has_communities = community_file.exists() and report_file.exists()
    if has_communities:
        community_df = pd.read_parquet(community_file)
        report_df = pd.read_parquet(report_file)
    else:
        print("Warning: Community Parquet files not found — skipping community import.")

    print(f"  Entities:      {len(entity_df)}")
    print(f"  Relationships: {len(rel_df)}")
    print(f"  Text units:    {len(text_unit_df)}")
    if has_communities:
        print(f"  Communities:   {len(community_df)}")

    # Phase 1: wipe transient nodes (new UUIDs every run) — fast
    delete_transient_nodes(driver)

    # Phase 2: remove entity nodes no longer present in the rebuilt graph —
    # these belong to document sections that were deleted or replaced
    delete_stale_entities(driver, entity_df)

    # Build graphrag UUID → stable entity ID mapping (needed for community links)
    uuid_to_stable = {
        str(row["id"]): stable_entity_id(str(row.get("title", "") or ""))
        for _, row in entity_df.iterrows()
    }

    with driver.session() as session:
        # Entities — MERGE preserves cross-document nodes, updates properties
        for i in range(0, len(entity_df), BATCH_SIZE):
            session.execute_write(import_entities, entity_df.iloc[i : i + BATCH_SIZE])
        print("Entities synced.")

        # Relationships
        for i in range(0, len(rel_df), BATCH_SIZE):
            session.execute_write(import_relationships, rel_df.iloc[i : i + BATCH_SIZE])
        print("Relationships synced.")

        # Communities + membership (always fresh)
        if has_communities:
            session.execute_write(import_communities, community_df, report_df)
            print("Communities imported.")
            session.execute_write(import_community_membership, community_df, uuid_to_stable)
            print("Community membership links created.")

        # TextUnit nodes (always fresh — CREATE not MERGE)
        for i in range(0, len(text_unit_df), BATCH_SIZE):
            session.execute_write(import_text_units, text_unit_df.iloc[i : i + BATCH_SIZE])
        print("Text units imported.")

        # TextUnit → Entity MENTIONS
        session.execute_write(import_text_unit_entity_links, entity_df)
        print("MENTIONS links created.")

    create_vector_indexes(driver, dim=args.embedding_dim)
    driver.close()
    print("Import complete.")


if __name__ == "__main__":
    main()
