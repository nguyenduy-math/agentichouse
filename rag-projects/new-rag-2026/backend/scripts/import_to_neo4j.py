"""
Bulk-import GraphRAG Parquet artifacts into Neo4j.
Run after `graphrag index` completes.

Usage:
    python scripts/import_to_neo4j.py \\
        --artifacts ./graphrag_workspace/output/artifacts \\
        --uri bolt://localhost:7687 \\
        --user neo4j \\
        --password <password>

    # With non-default embedding dimensions (Siliconflow BAAI/bge-large-zh-v1.5 = 1024):
    python scripts/import_to_neo4j.py \\
        --artifacts ./graphrag_workspace/output/artifacts \\
        --uri bolt://localhost:7687 \\
        --user neo4j \\
        --password <password> \\
        --embedding-dim 1024
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import GraphRAG Parquet artifacts into Neo4j")
    p.add_argument("--artifacts", required=True, help="Path to GraphRAG output/artifacts directory")
    p.add_argument("--uri", default="bolt://localhost:7687", help="Neo4j Bolt URI")
    p.add_argument("--user", default="neo4j", help="Neo4j username")
    p.add_argument("--password", required=True, help="Neo4j password")
    p.add_argument(
        "--embedding-dim",
        type=int,
        default=768,
        help="Embedding dimensions for vector indexes (768 for Gemini, 1024 for Siliconflow, 1536 for OpenAI)",
    )
    return p.parse_args()


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


BATCH_SIZE = 500


def import_entities(tx, df: pd.DataFrame) -> None:
    """Import Entity nodes with embeddings."""
    records = []
    for _, row in df.iterrows():
        records.append({
            "id": str(row["id"]),
            "name": str(row.get("name", "") or ""),
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
    """Import RELATED_TO relationships between Entity nodes."""
    records = []
    for _, row in df.iterrows():
        records.append({
            "source": str(row["source"]),
            "target": str(row["target"]),
            "description": str(row.get("description", "") or ""),
            "weight": float(row.get("weight", 1.0) or 1.0),
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


def import_communities(
    tx, df: pd.DataFrame, report_df: pd.DataFrame
) -> None:
    """Import Community nodes with summary text and embeddings from community reports."""
    # Normalize report_df ID column
    report_col_map = {}
    if "community" in report_df.columns:
        report_col_map["community"] = "id"
    report_df = report_df.rename(columns=report_col_map)

    # Merge community data with report data
    report_cols = [c for c in ["id", "title", "summary", "full_content", "embedding"] if c in report_df.columns]
    merged = df.merge(report_df[report_cols], on="id", how="left")

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


def import_community_membership(tx, entity_df: pd.DataFrame) -> None:
    """Link Entity nodes to their Community via IN_COMMUNITY."""
    records = []
    for _, row in entity_df.iterrows():
        community = row.get("community")
        if community is not None and str(community) not in ("nan", "None", ""):
            records.append({
                "entity_id": str(row["id"]),
                "community_id": str(int(float(community))),
            })
    if not records:
        return
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
    """Import TextUnit nodes."""
    records = []
    for _, row in df.iterrows():
        # document_ids may be a list or a string
        doc_ids = row.get("document_ids", [])
        if isinstance(doc_ids, str):
            try:
                doc_ids = json.loads(doc_ids)
            except Exception:
                doc_ids = []
        doc_id = str(doc_ids[0]) if doc_ids else ""

        records.append({
            "id": str(row["id"]),
            "text": str(row.get("text", "") or ""),
            "document_id": doc_id,
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
    """Link TextUnit nodes to Entity nodes via MENTIONS."""
    records = []
    for _, row in entity_df.iterrows():
        text_unit_ids = row.get("text_unit_ids") or []
        if isinstance(text_unit_ids, str):
            try:
                text_unit_ids = json.loads(text_unit_ids)
            except Exception:
                text_unit_ids = []
        for tu_id in text_unit_ids:
            records.append({
                "tu_id": str(tu_id),
                "entity_id": str(row["id"]),
            })
    if not records:
        return
    # Process in batches to avoid huge UNWIND
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


def create_schema_constraints(driver) -> None:
    """Create uniqueness constraints and property indexes."""
    with driver.session() as session:
        constraints = [
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT community_id IF NOT EXISTS FOR (c:Community) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT text_unit_id IF NOT EXISTS FOR (t:TextUnit) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
            "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)",
            "CREATE INDEX community_level IF NOT EXISTS FOR (c:Community) ON (c.level)",
            "CREATE INDEX text_unit_document IF NOT EXISTS FOR (t:TextUnit) ON (t.document_id)",
        ]
        for stmt in constraints + indexes:
            try:
                session.run(stmt)
            except Exception as exc:
                print(f"Warning: {exc}")
    print("Schema constraints and indexes created.")


def create_vector_indexes(driver, dim: int = 768) -> None:
    """Create Neo4j vector indexes for entity and community embeddings."""
    with driver.session() as session:
        try:
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
        except Exception as exc:
            print(f"Warning (entity vector index): {exc}")

        try:
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
        except Exception as exc:
            print(f"Warning (community vector index): {exc}")

    print(f"Vector indexes created (dim={dim}).")


def main() -> None:
    args = parse_args()
    artifacts = Path(args.artifacts)

    if not artifacts.is_dir():
        raise SystemExit(f"Artifacts directory not found: {artifacts}")

    print(f"Connecting to Neo4j at {args.uri}...")
    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))

    # Create schema first
    create_schema_constraints(driver)

    print("Reading Parquet artifacts...")
    entity_df = pd.read_parquet(artifacts / "create_final_entities.parquet")
    rel_df = pd.read_parquet(artifacts / "create_final_relationships.parquet")
    text_unit_df = pd.read_parquet(artifacts / "create_final_text_units.parquet")

    # Community files
    community_file = artifacts / "create_final_communities.parquet"
    report_file = artifacts / "create_final_community_reports.parquet"
    has_communities = community_file.exists() and report_file.exists()
    if has_communities:
        community_df = pd.read_parquet(community_file)
        report_df = pd.read_parquet(report_file)
    else:
        print("Warning: Community Parquet files not found — skipping community import.")

    print(f"  Entities:     {len(entity_df)}")
    print(f"  Relationships:{len(rel_df)}")
    print(f"  Text units:   {len(text_unit_df)}")
    if has_communities:
        print(f"  Communities:  {len(community_df)}")

    with driver.session() as session:
        # Entities (batched)
        for i in range(0, len(entity_df), BATCH_SIZE):
            session.execute_write(import_entities, entity_df.iloc[i : i + BATCH_SIZE])
        print("Entities imported.")

        # Relationships (batched)
        for i in range(0, len(rel_df), BATCH_SIZE):
            session.execute_write(import_relationships, rel_df.iloc[i : i + BATCH_SIZE])
        print("Relationships imported.")

        # Communities + reports
        if has_communities:
            session.execute_write(import_communities, community_df, report_df)
            print("Communities imported.")
            session.execute_write(import_community_membership, entity_df)
            print("Community membership links created.")

        # Text units (batched)
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
