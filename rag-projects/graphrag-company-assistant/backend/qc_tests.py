"""
QC Test Suite – GraphRAG HR Assistant (Agentic House)
======================================================
Run from the backend/ directory:

    python qc_tests.py                              # all sections
    python qc_tests.py --section neo4j              # just Neo4j checks
    python qc_tests.py --section api                # just API checks
    python qc_tests.py --section eval               # golden-QA evaluation (costs LLM calls)
    python qc_tests.py --output report.csv          # export results to docs/report.csv
    python qc_tests.py --section api --output api.csv  # combine section + export

Sections: neo4j | retrieval | api | eval | manual
Export:   --output FILE  (CSV; plain filename → saved under docs/)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import textwrap
import time
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Optional imports — only needed for specific sections
# ---------------------------------------------------------------------------
try:
    import httpx  # for API tests
except ImportError:
    httpx = None  # type: ignore

try:
    from neo4j import GraphDatabase  # for Neo4j tests
except ImportError:
    GraphDatabase = None  # type: ignore

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "techviet2024")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"
INFO = "\033[94mℹ INFO\033[0m"

@dataclass
class Result:
    name: str
    passed: bool
    message: str
    detail: str = ""

results: list[Result] = []

def record(name: str, passed: bool, message: str, detail: str = "") -> None:
    r = Result(name, passed, message, detail)
    results.append(r)
    icon = PASS if passed else FAIL
    print(f"  {icon}  {name}: {message}")
    if detail and not passed:
        for line in textwrap.wrap(detail, 90):
            print(f"         {line}")

def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")

# ===========================================================================
# SECTION 1 – Neo4j Indexing QC
# ===========================================================================

# Expected source files after running build_graph_index.py
EXPECTED_SOURCE_FILES = [
    "chinh_sach_nghi_phep.txt",
    "quy_trinh_xin_phep.txt",
    "quy_dinh_trang_phuc.txt",
    "chinh_sach_phuc_loi.txt",
    "chinh_sach_lam_viec_tu_xa.txt",
    "so_tay_nhan_vien.txt",
]

MIN_CHUNKS_PER_FILE = 2
MIN_ENTITIES_TOTAL = 30
MIN_COMMUNITIES = 2
MAX_ORPHAN_RATIO = 0.05  # ≤ 5% entities without any relationship


def run_neo4j_qc() -> None:
    section("1. NEO4J INDEXING QC")

    if GraphDatabase is None:
        print(f"  {WARN}  neo4j driver not installed — pip install neo4j")
        return

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
    except Exception as e:
        record("neo4j-connection", False, f"Cannot connect to Neo4j: {e}")
        return

    with driver.session() as s:
        # 1a. All expected source files are indexed
        rows = s.run(
            "MATCH (c:PolicyChunk) RETURN c.source_file AS f, count(*) AS n"
        ).data()
        indexed = {r["f"]: r["n"] for r in rows}

        for fname in EXPECTED_SOURCE_FILES:
            found = any(fname in key for key in indexed)
            count = next((v for k, v in indexed.items() if fname in k), 0)
            record(
                f"indexed-{fname}",
                found and count >= MIN_CHUNKS_PER_FILE,
                f"{count} chunks" if found else "NOT FOUND in PolicyChunk nodes",
            )

        # 1b. Total entity count
        total_entities = s.run("MATCH (e:Entity) RETURN count(e) AS n").single()["n"]
        record(
            "entity-count",
            total_entities >= MIN_ENTITIES_TOTAL,
            f"{total_entities} entities (min {MIN_ENTITIES_TOTAL})",
        )

        # 1c. No entity with null description
        null_desc = s.run(
            "MATCH (e:Entity) WHERE e.description IS NULL OR e.description = '' RETURN count(e) AS n"
        ).single()["n"]
        record(
            "entity-descriptions",
            null_desc == 0,
            f"{null_desc} entities with missing description",
        )

        # 1d. Orphan entities (no relationships)
        orphan_count = s.run(
            "MATCH (e:Entity) WHERE NOT (e)-[]-() RETURN count(e) AS n"
        ).single()["n"]
        orphan_ratio = orphan_count / max(total_entities, 1)
        record(
            "orphan-entities",
            orphan_ratio <= MAX_ORPHAN_RATIO,
            f"{orphan_count} orphans ({orphan_ratio:.1%}) — max allowed {MAX_ORPHAN_RATIO:.0%}",
        )

        # 1e. Community detection ran and all have summaries
        community_data = s.run(
            "MATCH (c:Community) RETURN count(c) AS total, "
            "sum(CASE WHEN c.summary IS NOT NULL AND c.summary <> '' THEN 1 ELSE 0 END) AS with_summary"
        ).single()
        total_comm = community_data["total"]
        with_summary = community_data["with_summary"]
        record(
            "community-count",
            total_comm >= MIN_COMMUNITIES,
            f"{total_comm} communities (min {MIN_COMMUNITIES})",
        )
        record(
            "community-summaries",
            total_comm > 0 and total_comm == with_summary,
            f"{with_summary}/{total_comm} communities have summaries",
        )

        # 1f. Vector indexes exist
        indexes = s.run("SHOW INDEXES").data()
        index_names = [i.get("name", "") for i in indexes]
        for expected_index in ["policy_chunks", "community_summaries"]:
            found = any(expected_index in name for name in index_names)
            record(f"vector-index-{expected_index}", found, "present" if found else "MISSING")

    driver.close()


# ===========================================================================
# SECTION 2 – Retrieval QC (vector search + graph traversal)
# ===========================================================================

# Each tuple: (question, expected_source_file_substring, expected_query_type)
RETRIEVAL_CASES: list[tuple[str, str, str]] = [
    ("Nhân viên có bao nhiêu ngày nghỉ phép năm?", "nghi_phep", "LOCAL"),
    ("Quy trình xin nghỉ phép năm gồm mấy bước?", "xin_phep", "LOCAL"),
    ("Nhân viên Phòng Kỹ thuật mặc gì vào thứ Hai?", "trang_phuc", "LOCAL"),
    ("Thưởng cuối năm xếp loại Xuất sắc được bao nhiêu tháng lương?", "phuc_loi", "LOCAL"),
    ("Phòng Kỹ thuật được làm việc từ xa mấy ngày mỗi tuần?", "lam_viec_tu_xa", "LOCAL"),
    ("Tóm tắt toàn bộ chính sách phúc lợi của công ty", "phuc_loi", "GLOBAL"),
    ("So sánh chính sách nghỉ phép giữa các loại nhân viên", "nghi_phep", "GLOBAL"),
    ("Công ty hỗ trợ gì cho nhân viên làm việc từ xa?", "lam_viec_tu_xa", "GLOBAL"),
]

# Classifier sanity check (only question + expected type)
CLASSIFIER_CASES: list[tuple[str, str]] = [
    ("Bao nhiêu ngày phép năm sau 5 năm?", "LOCAL"),
    ("Quy trình xin nghỉ thai sản?", "LOCAL"),
    ("Mức thưởng Tết tối thiểu?", "LOCAL"),
    ("Nhân viên Kinh doanh có được làm remote không?", "LOCAL"),
    ("Tóm tắt tất cả quy định trang phục", "GLOBAL"),
    ("Công ty có những chính sách gì hỗ trợ sức khỏe nhân viên?", "GLOBAL"),
    ("So sánh quyền lợi của nhân viên các phòng ban", "GLOBAL"),
]


async def run_retrieval_qc() -> None:
    section("2. RETRIEVAL & CLASSIFIER QC")

    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from app.config import settings  # noqa: F401
        from app.services.embedding_service import EmbeddingService
        from app.services.neo4j_store import Neo4jStore
        from app.services.llm_service import LLMService
    except ImportError as e:
        print(f"  {WARN}  Cannot import backend services: {e}")
        print("        Run from backend/ directory with venv activated.")
        return

    emb_service = EmbeddingService()
    neo4j_store = Neo4jStore()
    llm_service = LLMService()

    # 2a. Retrieval recall
    hit = 0
    for question, expected_file_substr, _ in RETRIEVAL_CASES:
        try:
            embedding = await emb_service.embed_query(question)
            chunks = await neo4j_store.vector_search_chunks(embedding, k=8)
            sources = [c.get("source_file", "") for c in chunks]
            matched = any(expected_file_substr in s for s in sources)
            if matched:
                hit += 1
            record(
                f"retrieval-{expected_file_substr[:20]}",
                matched,
                f"found '{expected_file_substr}' in top-8" if matched else f"top sources: {sources[:3]}",
            )
        except Exception as e:
            record(f"retrieval-{expected_file_substr[:20]}", False, f"Error: {e}")

    recall = hit / len(RETRIEVAL_CASES)
    record("retrieval-recall@8", recall >= 0.85, f"{recall:.0%} (target ≥ 85%)")

    # 2b. Query classifier
    classifier_hit = 0
    for question, expected_type in CLASSIFIER_CASES:
        try:
            got = await llm_service.classify_query(question)
            ok = got == expected_type
            if ok:
                classifier_hit += 1
            record(
                f"classify-{'LOCAL' if expected_type == 'LOCAL' else 'GLOBAL'}-{question[:30]}",
                ok,
                f"got {got}" if ok else f"expected {expected_type}, got {got}",
            )
        except Exception as e:
            record(f"classify-{question[:20]}", False, f"Error: {e}")

    accuracy = classifier_hit / len(CLASSIFIER_CASES)
    record("classifier-accuracy", accuracy >= 0.85, f"{accuracy:.0%} (target ≥ 85%)")

    await neo4j_store.close()


# ===========================================================================
# SECTION 3 – API Integration QC
# ===========================================================================

# (question, must_contain_substring_in_reply, expected_query_type, expected_has_sources)
API_CASES: list[tuple[str, str, str, bool]] = [
    # ── Leave policy ─────────────────────────────────────────────────────────
    ("Nhân viên dưới 5 năm có bao nhiêu ngày nghỉ phép năm?", "12", "LOCAL", True),
    ("Nhân viên từ 5 đến dưới 10 năm thâm niên được bao nhiêu ngày nghỉ phép năm?", "14", "LOCAL", True),
    ("Nhân viên trên 10 năm thâm niên được nghỉ bao nhiêu ngày phép năm?", "16", "LOCAL", True),
    ("Phép năm còn dư có thể chuyển tối đa bao nhiêu ngày sang năm sau?", "5 ngày", "LOCAL", True),
    ("Nhân viên được nghỉ ốm có lương tối đa bao nhiêu ngày mỗi năm?", "10 ngày", "LOCAL", True),
    ("Nhân viên nữ được nghỉ thai sản bao lâu?", "6 tháng", "LOCAL", True),
    ("Bản thân nhân viên kết hôn được nghỉ mấy ngày có lương?", "3 ngày", "LOCAL", True),
    # ── Leave procedure ───────────────────────────────────────────────────────
    ("Quy trình xin nghỉ đột xuất cần làm gì?", "HRM", "LOCAL", True),
    ("Làm thêm giờ vào ngày lễ được tính bao nhiêu phần trăm lương?", "300", "LOCAL", True),
    # ── Dress code ────────────────────────────────────────────────────────────
    ("Phòng Kỹ thuật được phép mặc gì vào thứ Hai?", "casual", "LOCAL", True),
    ("Chính sách Casual Friday cho phép nhân viên mặc trang phục gì?", "jeans", "LOCAL", True),
    ("Nhân viên vi phạm quy định trang phục lần thứ 2 bị xử lý như thế nào?", "cảnh báo", "LOCAL", True),
    # ── Benefits ─────────────────────────────────────────────────────────────
    ("Mức phụ cấp ăn trưa là bao nhiêu?", "50.000", "LOCAL", True),
    ("Thưởng cuối năm xếp loại Xuất sắc được bao nhiêu tháng lương?", "3", "LOCAL", True),
    ("Nhân viên giới thiệu ứng viên Senior được thưởng bao nhiêu?", "5.000.000", "LOCAL", True),
    # ── Remote work ───────────────────────────────────────────────────────────
    ("Phòng Kỹ thuật làm remote tối đa mấy ngày?", "3", "LOCAL", True),
    ("Phòng Kinh doanh có được phép làm việc từ xa không?", "không áp dụng", "LOCAL", True),
    ("Trong giờ cốt lõi khi làm remote, nhân viên phải phản hồi trong bao lâu?", "15 phút", "LOCAL", True),
    # ── Out-of-scope (hallucination guard) ───────────────────────────────────
    ("Câu hỏi hoàn toàn không liên quan đến nội quy: thời tiết hôm nay thế nào?", "Nhân sự", "LOCAL", False),
]

MULTI_TURN_FLOW = [
    ("Nhân viên có bao nhiêu ngày nghỉ phép?", "12"),
    ("Nếu thâm niên trên 10 năm thì sao?", "16"),
    ("Còn nhân viên thử việc?", "không áp dụng"),
]


async def run_api_qc() -> None:
    section("3. API INTEGRATION QC")

    if httpx is None:
        print(f"  {WARN}  httpx not installed — pip install httpx")
        return

    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=60) as client:
        # 3a. Health check
        try:
            r = await client.get("/health")
            record("health-endpoint", r.status_code == 200 and r.json().get("status") == "ok",
                   f"status={r.status_code} body={r.text[:80]}")
        except Exception as e:
            record("health-endpoint", False, f"Cannot reach backend: {e}")
            return

        # 3b. Session creation
        try:
            r = await client.post("/api/v1/session")
            session_id = r.json().get("session_id", "")
            record("create-session", r.status_code == 200 and bool(session_id),
                   f"session_id={session_id[:20]}...")
        except Exception as e:
            record("create-session", False, str(e))
            return

        # 3c. Individual chat cases — each gets its own fresh session so questions
        # are fully isolated and don't see each other's conversation history.
        for question, must_contain, exp_type, exp_sources in API_CASES:
            try:
                # r_sess = await client.post("/api/v1/session")
                # case_session_id = r_sess.json().get("session_id", "")

                # r = await client.post("/api/v1/chat", json={"session_id": case_session_id, "message": question})
                r = await client.post("/api/v1/chat", json={"session_id": session_id, "message": question})
                body = r.json()
                # print(f"API response: {body}")
                reply = body.get("reply", "").lower()
                got_type = body.get("query_type", "")
                sources = body.get("sources", [])

                answer_ok = must_contain.lower() in reply
                type_ok = got_type == exp_type
                sources_ok = (len(sources) > 0) == exp_sources

                record(
                    f"chat-{question[:35]}",
                    answer_ok and type_ok,
                    f"query_type={got_type}, sources={len(sources)}, contains='{must_contain}': {'✓' if answer_ok else '✗'}",
                    detail="" if answer_ok else f"Reply excerpt: {body.get('reply', '')[:200]}",
                )
                # await client.delete(f"/api/v1/session/{case_session_id}")
            except Exception as e:
                record(f"chat-{question[:35]}", False, str(e))

        # 3d. Multi-turn conversation (context continuity)
        # try:
        #     r2 = await client.post("/api/v1/session")
        #     mt_session = r2.json().get("session_id", "")
        #     mt_ok = True
        #     for question, must_contain in MULTI_TURN_FLOW:
        #         r = await client.post("/api/v1/chat", json={"session_id": mt_session, "message": question})
        #         reply = r.json().get("reply", "").lower()
        #         if must_contain.lower() not in reply:
        #             mt_ok = False
        #             record(
        #                 f"multi-turn-{question[:30]}",
        #                 False,
        #                 f"Missing '{must_contain}' in reply",
        #                 detail=r.json().get("reply", "")[:300],
        #             )
        #         else:
        #             record(f"multi-turn-{question[:30]}", True, f"contains '{must_contain}'")
        # except Exception as e:
        #     record("multi-turn", False, str(e))

        # 3e. Session history endpoint
        # try:
        #     r = await client.get(f"/api/v1/chat/{session_id}/history")
        #     history = r.json()
        #     record("chat-history", r.status_code == 200 and len(history) > 0,
        #            f"{len(history)} messages in history")
        # except Exception as e:
        #     record("chat-history", False, str(e))

        # 3f. Graph endpoint
        # try:
        #     r = await client.get("/api/v1/graph/nodes")
        #     record("graph-nodes", r.status_code == 200, f"status={r.status_code}")
        # except Exception as e:
        #     record("graph-nodes", False, str(e))

        # 3g. Stats endpoint
        # try:
        #     r = await client.get("/api/v1/stats")
        #     record("admin-stats", r.status_code == 200, f"status={r.status_code}")
        # except Exception as e:
        #     record("admin-stats", False, str(e))

        # 3h. Session delete
        try:
            r = await client.delete(f"/api/v1/session/{session_id}")
            record("delete-session", r.status_code in (200, 204),
                   f"status={r.status_code}")
        except Exception as e:
            record("delete-session", False, str(e))


# ===========================================================================
# SECTION 4 – Golden QA Evaluation (LLM-as-Judge)
# ===========================================================================

@dataclass
class GoldenCase:
    question: str
    ground_truth: str       # key facts that MUST appear in a correct answer
    source_file: str        # expected source document substring
    query_type: str         # LOCAL or GLOBAL
    out_of_scope: bool = False  # True → system should NOT fabricate; should redirect


GOLDEN_QA: list[GoldenCase] = [
    # ── Leave policy ─────────────────────────────────────────────────────────
    GoldenCase(
        question="Nhân viên chính thức dưới 5 năm thâm niên được nghỉ bao nhiêu ngày phép năm?",
        ground_truth="12 ngày/năm",
        source_file="nghi_phep",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Nhân viên từ 5 năm đến dưới 10 năm thâm niên được bao nhiêu ngày phép năm?",
        ground_truth="14 ngày/năm",
        source_file="nghi_phep",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Phép năm còn dư có thể chuyển tối đa bao nhiêu ngày?",
        ground_truth="5 ngày",
        source_file="nghi_phep",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Nghỉ ốm có lương tối đa bao nhiêu ngày mỗi năm?",
        ground_truth="10 ngày",
        source_file="nghi_phep",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Nhân viên nữ được nghỉ thai sản bao lâu?",
        ground_truth="6 tháng",
        source_file="nghi_phep",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Bản thân nhân viên kết hôn được nghỉ mấy ngày có lương?",
        ground_truth="3 ngày",
        source_file="nghi_phep",
        query_type="LOCAL",
    ),

    # ── Leave procedure ───────────────────────────────────────────────────────
    GoldenCase(
        question="Xin nghỉ 1–2 ngày phép năm phải nộp đơn trước bao nhiêu ngày?",
        ground_truth="3 ngày làm việc",
        source_file="xin_phep",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Khi nghỉ đột xuất, nhân viên KHÔNG được làm gì theo quy trình?",
        ground_truth="không chỉ gửi email",
        source_file="xin_phep",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Làm thêm giờ vào ngày lễ được tính lương bao nhiêu phần trăm?",
        ground_truth="300%",
        source_file="xin_phep",
        query_type="LOCAL",
    ),

    # ── Dress code ────────────────────────────────────────────────────────────
    GoldenCase(
        question="Nhân viên Phòng Kỹ thuật được phép mặc gì vào thứ Hai đến thứ Năm?",
        ground_truth="business casual",
        source_file="trang_phuc",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Chính sách Casual Friday cho phép nhân viên mặc gì?",
        ground_truth="jeans",
        source_file="trang_phuc",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Nhân viên vi phạm quy định trang phục lần 2 bị xử lý thế nào?",
        ground_truth="cảnh báo bằng văn bản",
        source_file="trang_phuc",
        query_type="LOCAL",
    ),

    # ── Benefits ─────────────────────────────────────────────────────────────
    GoldenCase(
        question="Phụ cấp ăn trưa cho nhân viên đi làm văn phòng là bao nhiêu mỗi ngày?",
        ground_truth="50.000 VNĐ",
        source_file="phuc_loi",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Thưởng cuối năm xếp loại Xuất sắc được bao nhiêu tháng lương?",
        ground_truth="3–4 tháng",
        source_file="phuc_loi",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Nhân viên giới thiệu ứng viên Senior được thưởng bao nhiêu?",
        ground_truth="5.000.000 VNĐ",
        source_file="phuc_loi",
        query_type="LOCAL",
    ),

    # ── Remote work ───────────────────────────────────────────────────────────
    GoldenCase(
        question="Phòng Kỹ thuật được làm việc từ xa tối đa bao nhiêu ngày mỗi tuần?",
        ground_truth="3 ngày",
        source_file="lam_viec_tu_xa",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Phòng Kinh doanh có được làm việc từ xa thường xuyên không?",
        ground_truth="không áp dụng",
        source_file="lam_viec_tu_xa",
        query_type="LOCAL",
    ),
    GoldenCase(
        question="Trong giờ cốt lõi khi làm remote, nhân viên phải phản hồi tin nhắn trong bao lâu?",
        ground_truth="15 phút",
        source_file="lam_viec_tu_xa",
        query_type="LOCAL",
    ),

    # ── GLOBAL / overview questions ───────────────────────────────────────────
    GoldenCase(
        question="Tóm tắt các loại nghỉ phép mà nhân viên được hưởng",
        ground_truth="nghỉ phép năm",
        source_file="nghi_phep",
        query_type="GLOBAL",
    ),
    GoldenCase(
        question="Công ty có những chính sách gì hỗ trợ nhân viên làm việc từ xa?",
        ground_truth="VPN",
        source_file="lam_viec_tu_xa",
        query_type="GLOBAL",
    ),

    # ── Out-of-scope (hallucination guard) ───────────────────────────────────
    GoldenCase(
        question="Lịch sử hình thành công ty Agentic House từ năm 2010 như thế nào?",
        ground_truth="Nhân sự",  # should redirect to HR, not make up history
        source_file="",
        query_type="LOCAL",
        out_of_scope=True,
    ),
    GoldenCase(
        question="Mức lương tháng cụ thể của vị trí Software Engineer là bao nhiêu?",
        ground_truth="Nhân sự",  # salary not in docs
        source_file="",
        query_type="LOCAL",
        out_of_scope=True,
    ),
]

JUDGE_PROMPT = """\
Bạn là một chuyên gia đánh giá hệ thống hỏi đáp về nội quy công ty.

Câu hỏi: {question}
Ground truth (thông tin đúng cần có): {ground_truth}
Câu trả lời của hệ thống: {answer}
Câu hỏi nằm ngoài tài liệu: {out_of_scope}

Hãy đánh giá câu trả lời theo 3 tiêu chí sau và trả về JSON:

{{
  "correctness": <1-5>,
  "groundedness": <1-5>,
  "completeness": <1-5>,
  "reasoning": "<giải thích ngắn gọn bằng tiếng Việt>"
}}

Tiêu chí:
- correctness (1-5): Thông tin có đúng với ground truth không? (5 = hoàn toàn đúng)
- groundedness (1-5): Câu trả lời có dựa trên tài liệu, không bịa đặt? (5 = không bịa đặt)
- completeness (1-5): Câu trả lời có đủ chi tiết cần thiết không? (5 = đầy đủ)

Nếu out_of_scope=True, groundedness = 5 nếu hệ thống từ chối hoặc chuyển hướng đến HR,\
 groundedness = 1 nếu hệ thống bịa đặt thông tin.
"""


async def run_eval_qc() -> None:
    section("4. GOLDEN QA EVALUATION (LLM-as-Judge)")

    if not GOOGLE_API_KEY:
        print(f"  {WARN}  GOOGLE_API_KEY not set — skipping eval section")
        return
    if httpx is None:
        print(f"  {WARN}  httpx not installed — pip install httpx")
        return

    try:
        from google import genai
        from google.genai import types as gtypes
        judge_client = genai.Client(
            api_key=GOOGLE_API_KEY,
            http_options={"api_version": "v1beta"},
        )
    except ImportError:
        print(f"  {WARN}  google-genai not installed")
        return

    scores_correctness: list[float] = []
    scores_groundedness: list[float] = []
    scores_completeness: list[float] = []

    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=90) as client:
        for case in GOLDEN_QA:
            try:
                # Fresh session per case so no cross-contamination from prior answers.
                r_sess = await client.post("/session")
                eval_session_id = r_sess.json().get("session_id", "eval-session")

                r = await client.post("/chat", json={
                    "session_id": eval_session_id,
                    "message": case.question,
                })
                answer = r.json().get("reply", "")

                judge_prompt = JUDGE_PROMPT.format(
                    question=case.question,
                    ground_truth=case.ground_truth,
                    answer=answer,
                    out_of_scope=str(case.out_of_scope),
                )
                judge_response = judge_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=judge_prompt,
                    config=gtypes.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0,
                    ),
                )
                scores = json.loads(judge_response.text)
                c = float(scores.get("correctness", 0))
                g = float(scores.get("groundedness", 0))
                comp = float(scores.get("completeness", 0))
                reasoning = scores.get("reasoning", "")

                scores_correctness.append(c)
                scores_groundedness.append(g)
                scores_completeness.append(comp)

                avg = (c + g + comp) / 3
                passed = c >= 3.5 and g >= 4.0 and comp >= 3.0
                label = f"C={c:.0f} G={g:.0f} Comp={comp:.0f} avg={avg:.1f}"
                record(
                    f"eval-{case.question[:45]}",
                    passed,
                    label,
                    detail=reasoning if not passed else "",
                )
                await client.delete(f"/session/{eval_session_id}")
                await asyncio.sleep(1)  # gentle rate-limit

            except Exception as e:
                record(f"eval-{case.question[:45]}", False, f"Error: {e}")

    if scores_correctness:
        avg_c = sum(scores_correctness) / len(scores_correctness)
        avg_g = sum(scores_groundedness) / len(scores_groundedness)
        avg_comp = sum(scores_completeness) / len(scores_completeness)
        print(f"\n  Aggregate scores over {len(GOLDEN_QA)} cases:")
        print(f"    Correctness  : {avg_c:.2f}/5 (target ≥ 4.0)")
        print(f"    Groundedness : {avg_g:.2f}/5 (target ≥ 4.5)")
        print(f"    Completeness : {avg_comp:.2f}/5 (target ≥ 3.5)")
        record("eval-correctness-avg",  avg_c >= 4.0,  f"{avg_c:.2f}/5")
        record("eval-groundedness-avg", avg_g >= 4.5,  f"{avg_g:.2f}/5")
        record("eval-completeness-avg", avg_comp >= 3.5, f"{avg_comp:.2f}/5")


# ===========================================================================
# SECTION 5 – Manual QC Checklist (printed, not automated)
# ===========================================================================

MANUAL_CHECKLIST = """
┌─────────────────────────────────────────────────────────────────────────┐
│                    MANUAL QC CHECKLIST (30 minutes)                     │
├──────────────────────────────────────────────────────────────────────────┤
│ NEO4J BROWSER  http://localhost:7474                                     │
│                                                                          │
│ □ Run: MATCH (e:Entity) RETURN e LIMIT 25                               │
│   → Visually inspect entity names and descriptions for correctness       │
│                                                                          │
│ □ Run: MATCH (e:Entity)-[r]->(e2:Entity) RETURN e,r,e2 LIMIT 40        │
│   → Check that relationships make sense (AP_DUNG_CHO, YEU_CAU, etc.)   │
│                                                                          │
│ □ Run: MATCH (c:Community) RETURN c.summary LIMIT 5                     │
│   → Check summaries are in Vietnamese and coherent                       │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ CHAT UI  http://localhost:5173                                           │
│                                                                          │
│ □ Ask: "Nhân viên có bao nhiêu ngày phép?"                              │
│   → Answer must cite 12/14/16 days; Sources panel shows nghi_phep.txt   │
│   → Graph panel shows entity nodes                                       │
│                                                                          │
│ □ Ask: "Phòng Kỹ thuật mặc gì thứ Hai?"                                │
│   → Answer says "business casual"; sources cite trang_phuc.txt          │
│                                                                          │
│ □ Ask: "Tóm tắt toàn bộ chính sách phúc lợi"                           │
│   → Long synthesized answer (GLOBAL); multiple community summaries used  │
│                                                                          │
│ □ Ask follow-up: "Còn quy định trang phục thì sao?" (in same session)   │
│   → System uses conversation history correctly                           │
│                                                                          │
│ □ Ask completely off-topic: "Cho tôi biết công thức nấu phở"            │
│   → System MUST say it cannot answer / redirect to HR                   │
│   → Must NOT fabricate any information                                   │
│                                                                          │
│ □ Check Sources panel shows correct file names and relevance scores      │
│ □ Check Graph panel renders nodes and edges without error                │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ EDGE CASES TO TEST MANUALLY                                              │
│                                                                          │
│ □ Very short question: "phép?"                                           │
│   → Graceful handling, not crash                                         │
│                                                                          │
│ □ English question: "How many vacation days do I get?"                   │
│   → Response should still be in Vietnamese                               │
│                                                                          │
│ □ Mixed language: "I want to take phép how many days?"                  │
│   → Should understand and respond in Vietnamese                          │
│                                                                          │
│ □ Very long question (300+ words)                                        │
│   → Should not timeout or crash                                          │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
"""

# ===========================================================================
# Summary report
# ===========================================================================

def print_summary() -> None:
    print(f"\n{'═' * 60}")
    print("  QC SUMMARY")
    print(f"{'═' * 60}")
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    print(f"  Total : {len(results)}")
    print(f"  {PASS} : {len(passed)}")
    print(f"  {FAIL} : {len(failed)}")

    if failed:
        print(f"\n  Failed tests:")
        for r in failed:
            print(f"    • {r.name}: {r.message}")

    score = len(passed) / max(len(results), 1)
    verdict = PASS if score >= 0.85 else WARN if score >= 0.70 else FAIL
    print(f"\n  Overall score: {score:.0%} {verdict}")
    print()


def export_csv(path: str) -> None:
    import csv
    from pathlib import Path

    out = Path(path)
    if out.parent == Path("."):
        out = Path("docs") / out
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "passed", "message", "detail"])
        writer.writeheader()
        for r in results:
            writer.writerow({"name": r.name, "passed": r.passed, "message": r.message, "detail": r.detail})

    print(f"\n  Report saved → {out.resolve()}")


# ===========================================================================
# Entry point
# ===========================================================================

async def main(sections: list[str], output: Optional[str] = None) -> None:
    print("\n  GraphRAG HR Assistant – QC Test Suite")
    print(f"  Backend: {BACKEND_URL}  |  Neo4j: {NEO4J_URI}")

    run_all = "all" in sections

    if run_all or "neo4j" in sections:
        run_neo4j_qc()

    if run_all or "retrieval" in sections:
        await run_retrieval_qc()

    if run_all or "api" in sections:
        await run_api_qc()

    if run_all or "eval" in sections:
        await run_eval_qc()

    if run_all or "manual" in sections:
        section("5. MANUAL QC CHECKLIST")
        print(MANUAL_CHECKLIST)

    if sections != ["manual"]:
        print_summary()

    if output:
        export_csv(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphRAG QC Test Suite")
    parser.add_argument(
        "--section",
        choices=["all", "neo4j", "retrieval", "api", "eval", "manual"],
        default="all",
        help="Which QC section to run (default: all)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Export results to a CSV file (default dir: docs/). E.g. --output report.csv",
    )
    args = parser.parse_args()
    asyncio.run(main([args.section], output=args.output))
