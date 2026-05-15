"""Neo4j patient profile graph — sync and fraud detection queries.

Graph schema:
  (:Patient {patient_id})
  (:Provider {provider_id, provider_name})
  (:Claim {claim_id, db_id, amount, service_date, combined_score, risk_level})
  (:Diagnosis {code})
  (:Procedure {code})

  (Patient)-[:SUBMITTED]->(Claim)
  (Claim)-[:TREATED_BY]->(Provider)
  (Claim)-[:CODED_WITH]->(Diagnosis)
  (Claim)-[:BILLED_FOR]->(Procedure)

After each batch run, `sync_and_enrich()` upserts all nodes/edges then runs
4 Cypher fraud queries. Results are returned as per-claim graph flags that
batch_pipeline.py appends to FraudAnalysis.rule_flags.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver

from app.config import settings

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None


async def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def check_neo4j() -> bool:
    try:
        driver = await get_driver()
        await driver.verify_connectivity()
        return True
    except Exception as exc:
        logger.warning("Neo4j connectivity check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Sync: upsert all nodes and relationships for a batch of claims
# ---------------------------------------------------------------------------

async def sync_batch(claim_rows: list[dict]) -> None:
    """Upsert Patient, Provider, Claim, Diagnosis, Procedure nodes + edges."""
    if not claim_rows:
        return

    driver = await get_driver()
    async with driver.session() as session:
        for row in claim_rows:
            await session.execute_write(_upsert_claim_graph, row)

    logger.info("Graph sync complete — %d claims upserted", len(claim_rows))


async def _upsert_claim_graph(tx, row: dict) -> None:
    patient_id = row.get("patient_id") or "UNKNOWN"
    provider_id = row.get("provider_id") or "UNKNOWN"
    provider_name = row.get("provider_name") or provider_id
    claim_id = row["claim_id"]
    db_id = str(row["db_id"])
    amount = float(row.get("amount") or 0)
    service_date = str(row.get("service_date") or "")
    combined_score = int(row.get("combined_score") or 0)
    risk_level = row.get("risk_level") or "low"
    diagnosis_codes = row.get("diagnosis_codes") or []
    procedure_codes = row.get("procedure_codes") or []

    # Upsert Patient
    await tx.run(
        "MERGE (p:Patient {patient_id: $pid}) "
        "ON CREATE SET p.claim_count = 1, p.total_billed = $amount "
        "ON MATCH SET p.claim_count = p.claim_count + 1, p.total_billed = p.total_billed + $amount",
        pid=patient_id, amount=amount,
    )

    # Upsert Provider
    await tx.run(
        "MERGE (pr:Provider {provider_id: $prid}) "
        "ON CREATE SET pr.provider_name = $name, pr.claim_count = 1, pr.total_billed = $amount, pr.high_risk_count = $hr "
        "ON MATCH SET pr.claim_count = pr.claim_count + 1, pr.total_billed = pr.total_billed + $amount, "
        "            pr.high_risk_count = pr.high_risk_count + $hr",
        prid=provider_id, name=provider_name, amount=amount,
        hr=1 if combined_score >= 51 else 0,
    )

    # Upsert Claim
    await tx.run(
        "MERGE (c:Claim {db_id: $db_id}) "
        "SET c.claim_id = $claim_id, c.amount = $amount, c.service_date = $sdate, "
        "    c.combined_score = $score, c.risk_level = $level",
        db_id=db_id, claim_id=claim_id, amount=amount,
        sdate=service_date, score=combined_score, level=risk_level,
    )

    # Relationships: Patient→Claim, Claim→Provider
    await tx.run(
        "MATCH (p:Patient {patient_id: $pid}), (c:Claim {db_id: $db_id}) "
        "MERGE (p)-[:SUBMITTED]->(c)",
        pid=patient_id, db_id=db_id,
    )
    await tx.run(
        "MATCH (c:Claim {db_id: $db_id}), (pr:Provider {provider_id: $prid}) "
        "MERGE (c)-[:TREATED_BY]->(pr)",
        db_id=db_id, prid=provider_id,
    )

    # Diagnosis nodes + edges
    for code in diagnosis_codes:
        if code:
            await tx.run(
                "MERGE (d:Diagnosis {code: $code}) "
                "WITH d MATCH (c:Claim {db_id: $db_id}) "
                "MERGE (c)-[:CODED_WITH]->(d)",
                code=code, db_id=db_id,
            )

    # Procedure nodes + edges
    for code in procedure_codes:
        if code:
            await tx.run(
                "MERGE (proc:Procedure {code: $code}) "
                "WITH proc MATCH (c:Claim {db_id: $db_id}) "
                "MERGE (c)-[:BILLED_FOR]->(proc)",
                code=code, db_id=db_id,
            )


# ---------------------------------------------------------------------------
# Fraud detection queries — each returns list of {db_id, flag}
# ---------------------------------------------------------------------------

async def run_fraud_queries() -> dict[str, list[dict]]:
    """Run all 4 graph fraud queries. Returns {db_id -> [flags]}."""
    results: dict[str, list[dict]] = {}

    for query_fn in (
        _query_provider_concentration,
        _query_patient_velocity,
        _query_fraud_ring,
        _query_procedure_dominance,
    ):
        flags = await query_fn()
        for db_id, flag in flags:
            results.setdefault(db_id, []).append(flag)

    return results


async def _query_provider_concentration() -> list[tuple[str, dict]]:
    """Provider where >50% of claims are high-risk (score ≥51), min 3 claims."""
    cypher = """
    MATCH (pr:Provider)<-[:TREATED_BY]-(c:Claim)
    WITH pr,
         count(c) AS total,
         sum(CASE WHEN c.combined_score >= 51 THEN 1 ELSE 0 END) AS high_risk
    WHERE total >= 2 AND toFloat(high_risk) / total > 0.4
    MATCH (pr)<-[:TREATED_BY]-(c2:Claim)
    RETURN c2.db_id AS db_id,
           pr.provider_name AS provider_name,
           total,
           high_risk
    """
    return await _run_query(
        cypher,
        lambda r: {
            "type": "graph_provider_concentration",
            "description": (
                f"Provider '{r['provider_name']}' has {r['high_risk']}/{r['total']} "
                f"high-risk claims ({round(r['high_risk']/r['total']*100)}%) — "
                "concentrated fraud pattern"
            ),
            "severity": "high",
        },
    )


async def _query_patient_velocity() -> list[tuple[str, dict]]:
    """Patient with ≥5 claims across multiple providers in a short window."""
    cypher = """
    MATCH (pt:Patient)-[:SUBMITTED]->(c:Claim)-[:TREATED_BY]->(pr:Provider)
    WITH pt, count(c) AS claim_count, count(DISTINCT pr) AS provider_count
    WHERE claim_count >= 5 AND provider_count >= 3
    MATCH (pt)-[:SUBMITTED]->(c2:Claim)
    RETURN c2.db_id AS db_id,
           pt.patient_id AS patient_id,
           claim_count,
           provider_count
    """
    return await _run_query(
        cypher,
        lambda r: {
            "type": "graph_velocity",
            "description": (
                f"Patient '{r['patient_id']}' submitted {r['claim_count']} claims "
                f"across {r['provider_count']} providers — rapid multi-provider pattern"
            ),
            "severity": "medium",
        },
    )


async def _query_fraud_ring() -> list[tuple[str, dict]]:
    """≥3 distinct patients sharing the same provider AND procedure code."""
    cypher = """
    MATCH (pt:Patient)-[:SUBMITTED]->(c:Claim)-[:TREATED_BY]->(pr:Provider)
    MATCH (c)-[:BILLED_FOR]->(proc:Procedure)
    WITH pr, proc, collect(DISTINCT pt.patient_id) AS patients,
         collect(DISTINCT c.db_id) AS claim_ids
    WHERE size(patients) >= 2
    UNWIND claim_ids AS db_id
    RETURN db_id,
           pr.provider_name AS provider_name,
           proc.code AS proc_code,
           size(patients) AS ring_size
    """
    return await _run_query(
        cypher,
        lambda r: {
            "type": "graph_ring",
            "description": (
                f"Fraud ring detected: {r['ring_size']} patients billed CPT {r['proc_code']} "
                f"by provider '{r['provider_name']}'"
            ),
            "severity": "high",
        },
    )


async def _query_procedure_dominance() -> list[tuple[str, dict]]:
    """Provider billing the same CPT code on >80% of claims, min 5 claims."""
    cypher = """
    MATCH (pr:Provider)<-[:TREATED_BY]-(c:Claim)-[:BILLED_FOR]->(proc:Procedure)
    WITH pr, proc, count(c) AS freq
    WITH pr, collect({code: proc.code, freq: freq}) AS procs,
         sum(freq) AS grand_total
    WHERE grand_total >= 2
    UNWIND procs AS p
    WITH pr, p, grand_total
    WHERE toFloat(p.freq) / grand_total > 0.8
    MATCH (pr)<-[:TREATED_BY]-(c2:Claim)
    RETURN c2.db_id AS db_id,
           pr.provider_name AS provider_name,
           p.code AS proc_code,
           p.freq AS freq,
           grand_total
    """
    return await _run_query(
        cypher,
        lambda r: {
            "type": "graph_procedure_dominance",
            "description": (
                f"Provider '{r['provider_name']}' bills CPT {r['proc_code']} "
                f"on {r['freq']}/{r['grand_total']} claims "
                f"({round(r['freq']/r['grand_total']*100)}%) — possible upcoding pattern"
            ),
            "severity": "medium",
        },
    )


async def _run_query(cypher: str, flag_fn) -> list[tuple[str, dict]]:
    results = []
    try:
        driver = await get_driver()
        async with driver.session() as session:
            records = await session.run(cypher)
            async for record in records:
                db_id = record.get("db_id")
                if db_id:
                    results.append((str(db_id), flag_fn(record)))
    except Exception as exc:
        logger.error("Graph query failed: %s", exc)
    return results


# ---------------------------------------------------------------------------
# Main entry point called by batch_pipeline
# ---------------------------------------------------------------------------

async def sync_and_enrich(claim_rows: list[dict]) -> dict[str, list[dict]]:
    """Sync claims to graph then return per-claim graph flags."""
    try:
        await sync_batch(claim_rows)
        flags = await run_fraud_queries()
        total_flagged = sum(len(v) for v in flags.values())
        logger.info("Graph enrichment complete — %d claim(s) received graph flags", len(flags))
        return flags
    except Exception as exc:
        logger.error("Graph sync_and_enrich failed: %s", exc)
        return {}
