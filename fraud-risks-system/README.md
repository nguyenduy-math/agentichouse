# Hệ Thống Phát Hiện Gian Lận Hồ Sơ BHYT (Healthcare Claim Fraud Detection)

Hệ thống phát hiện gian lận bảo hiểm y tế (BHYT) cho thị trường Việt Nam, kết hợp phân tích mô tả lâm sàng bằng LLM, tín hiệu dựa trên quy tắc, đồ thị mạng lưới bệnh nhân Neo4j và vòng lặp xem xét của con người (human-in-the-loop). Hệ thống hoạt động ngay từ ngày đầu mà không cần dữ liệu gian lận đã được gán nhãn, tích lũy quyết định của điều tra viên làm tập dữ liệu huấn luyện cho giai đoạn ML sau này.

> **Ngôn ngữ phân tích:** Tiếng Việt — LLM trả về giải thích và cờ cảnh báo bằng tiếng Việt.
> **Đơn vị tiền tệ:** VND (Đồng Việt Nam).
> **Khung pháp lý tham chiếu:** Luật BHYT, Thông tư 39/2018/TT-BYT.

---

## Architecture

```
CSV Upload → Claims DB (PostgreSQL)
                ↓
        [Nightly Batch @ 2am]
                ↓
    ┌─────────────────────────┐     ┌──────────────────────────┐
    │  Qwen2.5 LLM Analyzer   │  +  │  Rule-Based Signals      │
    │  (narrative analysis)   │     │  (codes, amounts, dates) │
    └─────────────────────────┘     └──────────────────────────┘
                ↓
        Per-Claim Risk Score
                ↓
    ┌─────────────────────────────────────────┐
    │  Patient Profile Graph  (Neo4j)         │  ← Post-batch enrichment pass
    │  Provider concentration · Fraud rings   │
    │  Patient velocity · Procedure dominance │
    └─────────────────────────────────────────┘
                ↓
        Combined Risk Score (0–100) + Network Risk flag
                ↓
    ┌─────────────────────────────┐
    │  Investigator Dashboard     │  http://localhost:5173
    │  Review Queue + Decisions   │  Purple "Network Risk" badge
    └─────────────────────────────┘
                ↓
        Labeled Dataset → Phase 2 ML Training (~500 reviews)
```

---

## Các Hình Thức Gian Lận Được Phát Hiện

### Cấp Độ Hồ Sơ — LLM + Quy Tắc (Per-Claim)

| Hình thức | Mô tả (Vietnam BHYT context) |
|---|---|
| **Kê sai mã / Nâng hạng dịch vụ** | Mô tả lâm sàng thấp hơn mã dịch vụ kỹ thuật được kê (upcoding) |
| **Kê khống dịch vụ** | Dịch vụ được kê không khớp với mô tả lâm sàng trong hồ sơ (phantom billing) |
| **Tách dịch vụ** | Kê nhiều mã dịch vụ lẽ ra phải tính chung một lần (unbundling) |
| **Không có chỉ định y tế** | Mã bệnh không hỗ trợ điều trị hoặc xét nghiệm được kê |
| **Mô tả mơ hồ** | Mô tả hồ sơ quá ngắn hoặc thiếu thông tin lâm sàng cần thiết |
| **Ngôn ngữ soạn sẵn** | Mô tả rập khuôn, không thực tế hoặc có yếu tố gây áp lực |
| **Bất thường thời gian** | Ngày nộp hồ sơ trước ngày khám, hoặc chênh lệch >1 năm |
| **Số tiền bất thường** | Số tiền đề nghị thanh toán vượt ngưỡng: >200 triệu VND (cao), >50 triệu VND (trung bình) |
| **Kê thuốc biệt dược không cần** | Kê thuốc nhập khẩu đắt tiền khi có thuốc generic tương đương |
| **Nằm viện không cần thiết** | Nhập viện điều trị nội trú khi hoàn toàn có thể điều trị ngoại trú |
| **Tách đợt điều trị** | Chia một đợt điều trị thành nhiều hồ sơ BHYT riêng biệt |

### Cấp Độ Mạng Lưới — Đồ Thị Neo4j (Network-Level)

| Hình thức | Mô tả |
|---|---|
| **Tập trung rủi ro cơ sở y tế** | Cơ sở y tế có >40% hồ sơ nguy cơ cao, tối thiểu 2 hồ sơ |
| **Vòng gian lận** | ≥2 bệnh nhân cùng cơ sở y tế và cùng mã dịch vụ |
| **Bệnh nhân đi nhiều cơ sở** | Bệnh nhân có ≥5 hồ sơ tại ≥3 cơ sở khác nhau |
| **Dịch vụ thống trị** | Cơ sở y tế kê cùng 1 mã dịch vụ >70% hồ sơ, tối thiểu 2 hồ sơ |

Hồ sơ bị gắn cờ mạng lưới hiển thị huy hiệu tím **Network Risk** trong hàng đợi xem xét và mục **Network Signals** riêng biệt trong ngăn chi tiết hồ sơ.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn (Python) |
| Relational DB | PostgreSQL 16 (Docker) |
| Graph DB | Neo4j 5 + APOC plugin (Docker) |
| LLM | Qwen2.5 via [SiliconFlow](https://siliconflow.cn) (OpenAI-compatible API) |
| Scheduler | APScheduler (nightly batch) |
| Frontend | React + Vite |

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- Docker + Docker Compose
- SiliconFlow API key — [get one here](https://siliconflow.cn)

---

## Quick Start

### 1. Start the databases

`docker-compose.yml` defines two sets of services. Start only the active **v2** containers:

```bash
docker compose up -d postgres-v2 neo4j-v2
```

Wait for both to be healthy:

```bash
docker ps --filter name=fraud-postgres-v2
docker ps --filter name=fraud-neo4j-v2
```

| Service | Container | Port |
|---|---|---|
| PostgreSQL v2 | `fraud-postgres-v2` | `5433` |
| Neo4j v2 (browser UI) | `fraud-neo4j-v2` | `7475` |
| Neo4j v2 (Bolt) | `fraud-neo4j-v2` | `7688` |

Neo4j Browser is available at `http://localhost:7475` (login: `neo4j` / `fraud-neo4j-secret`).

> **Old containers** (`fraud-postgres` on `5432`, `fraud-neo4j` on `7474`/`7687`) are kept in `docker-compose.yml` for data preservation and are not started by the command above.

### 2. Set up the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy and edit the environment file:

```bash
cp .env.example .env
```

Set at minimum:

```env
LLM_API_KEY=your-siliconflow-key-here
```

The Neo4j and PostgreSQL defaults in `.env.example` already point to the v2 ports (`5433` / `7688`) and need no changes unless you modified the passwords.

Start the API server:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

The server initializes the database tables on first startup. Open `http://127.0.0.1:8001/docs` to explore the API.

### 3. Set up the frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Using the System

### Step 1 — Upload Claims

Go to the **Upload Claims** tab and drop a CSV file. The only required column is `claim_id`.

**Các cột hỗ trợ:**

| Cột | Mô tả |
|---|---|
| `claim_id` | Mã hồ sơ (bắt buộc) |
| `patient_id` | Mã bệnh nhân (đã ẩn danh) |
| `provider_id` | Mã cơ sở khám chữa bệnh |
| `provider_name` | Tên cơ sở khám chữa bệnh |
| `claim_amount` | Số tiền đề nghị thanh toán **(đơn vị: VND)** |
| `service_date` | Ngày khám/điều trị (`YYYY-MM-DD` hoặc `MM/DD/YYYY`) |
| `submission_date` | Ngày nộp hồ sơ |
| `claim_type` | `inpatient` (nội trú), `outpatient` (ngoại trú), `pharmacy` (dược), `lab` (xét nghiệm) |
| `diagnosis_codes` | Mã bệnh ICD-10, phân cách bằng `\|` (ví dụ: `J06.9\|J02.9`) |
| `procedure_codes` | Mã dịch vụ kỹ thuật, phân cách bằng `\|` (ví dụ: `KT-001\|XN-002`) |
| `claim_narrative` | **Mô tả hồ sơ bằng tiếng Việt** — trường chính được LLM phân tích |

Bộ dữ liệu mẫu với 25 hồ sơ BHYT Việt Nam tổng hợp tại `backend/data/sample_claims.csv`.

### Step 2 — Run Batch Analysis

Click **Run Batch Now** in the Review Queue tab, or wait for the nightly run at 2:00 AM. The batch runs in two passes:

**Pass 1 — Phân tích từng hồ sơ** (runs in parallel per claim)
- Qwen2.5 LLM (SiliconFlow) phân tích mô tả hồ sơ → điểm rủi ro + cờ cảnh báo + giải thích **bằng tiếng Việt**
- Rule engine kiểm tra số tiền VND, số lượng dịch vụ, và thời gian nộp hồ sơ
- Combined score ghi vào `fraud_analyses`

**Pass 2 — Graph enrichment** (runs once after all claims are scored)
- All claims synced to the Neo4j patient profile graph as nodes and edges
- 4 Cypher queries detect network-level fraud patterns across providers and patients
- Graph flags appended to `rule_flags`; combined score boosted by up to +20 per high-severity graph flag

```
Điểm kết hợp = 0.7 × Điểm LLM + 0.3 × max(Điểm quy tắc, Điểm đồ thị)
                                 + phần thưởng mức độ nghiêm trọng đồ thị (tối đa 100)
```

Ngưỡng phân loại rủi ro:

| Điểm | Mức | Ngưỡng quy tắc VND |
|---|---|---|
| 0–25 | Thấp (Low) | — |
| 26–50 | Trung bình (Medium) | > 50,000,000 VND |
| 51–75 | Cao (High) | — |
| 76–100 | Nghiêm trọng (Critical) | > 200,000,000 VND |

### Step 3 — Review Claims

The **Review Queue** shows analyzed claims sorted by risk score. Claims with network-level fraud signals display a purple **Network Risk** badge.

Click any row to open the claim detail drawer:

- Thông tin hồ sơ và mã dịch vụ kỹ thuật
- Mô tả hồ sơ gốc (tiếng Việt)
- **Giải thích AI bằng tiếng Việt** — tóm tắt lý do nghi ngờ gian lận
- Mục **Network Signals** (màu tím) — cờ phát hiện từ đồ thị mạng lưới
- Danh sách cờ cảnh báo từng hồ sơ kèm mức độ nghiêm trọng

Quyết định của điều tra viên:

- **Legitimate** — hồ sơ hợp lệ
- **Suspicious** — cần điều tra thêm
- **Confirmed Fraud** — xác nhận gian lận, chuyển xử lý

Each decision is stored and contributes to your labeled dataset.

### Step 4 — Explore the Graph

Open **http://localhost:7475** to query the patient profile graph directly:

```cypher
// View the full graph (small datasets)
MATCH (n) RETURN n LIMIT 100

// Find providers with the most high-risk claims
MATCH (pr:Provider)<-[:TREATED_BY]-(c:Claim)
WHERE c.combined_score >= 51
RETURN pr.provider_name, count(c) AS high_risk_claims
ORDER BY high_risk_claims DESC

// Find shared-provider patient clusters
MATCH (pt:Patient)-[:SUBMITTED]->(c:Claim)-[:TREATED_BY]->(pr:Provider)
WITH pr, collect(DISTINCT pt.patient_id) AS patients
WHERE size(patients) >= 2
RETURN pr.provider_name, patients
```

### Step 5 — Track Progress

The **Stats** tab shows your label accumulation. Phase 2 ML training (XGBoost/LightGBM classifier) becomes viable at approximately 500 labeled reviews.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | System health (DB + LLM) |
| `POST` | `/claims/upload` | Upload CSV file |
| `GET` | `/claims` | List claims with filters |
| `GET` | `/claims/{id}` | Claim detail + latest analysis |
| `GET` | `/review/queue` | Paginated queue sorted by risk (`network_risk` field included) |
| `POST` | `/review/{id}/decision` | Submit investigator decision |
| `GET` | `/review/stats` | Dashboard statistics |
| `POST` | `/batch/run` | Trigger batch analysis + graph enrichment manually |
| `GET` | `/batch/status` | Last batch run status |

All endpoints are also available under the `/api/` prefix (used by the frontend).

Interactive API docs: `http://127.0.0.1:8001/docs`

---

## Configuration

All settings are in `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `LLM_API_KEY` | — | Required. Your SiliconFlow API key |
| `LLM_API_BASE` | `https://api.siliconflow.cn/v1` | OpenAI-compatible API base URL |
| `LLM_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | Model name (e.g. `Qwen/Qwen2.5-14B-Instruct` for higher accuracy) |
| `DATABASE_URL` | `postgresql+asyncpg://fraud:fraud-secret@localhost:5433/fraud_detection` | PostgreSQL connection string (v2 container) |
| `NEO4J_URI` | `bolt://localhost:7688` | Neo4j Bolt URI (v2 container) |
| `NEO4J_USERNAME` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `fraud-neo4j-secret` | Must match `docker-compose.yml` `NEO4J_AUTH` |
| `BATCH_CRON_HOUR` | `2` | Hour for nightly batch (0–23) |
| `BATCH_CRON_MINUTE` | `0` | Minute for nightly batch |
| `BATCH_MAX_CLAIMS` | `500` | Max claims per batch run |
| `LLM_SCORE_WEIGHT` | `0.7` | Weight for LLM score in combined score |
| `RULE_SCORE_WEIGHT` | `0.3` | Weight for rule-based + graph score |
| `PORT` | `8001` | Backend server port |

---

## Dữ Liệu Mẫu (Sample Claims)

File `backend/data/sample_claims.csv` chứa 25 hồ sơ BHYT Việt Nam tổng hợp với các bệnh viện thực tế:

| Hồ sơ | Cơ sở y tế | Hình thức gian lận |
|---|---|---|
| VN-001 – VN-009 | BV Bạch Mai, BV Chợ Rẫy, BV Việt Đức... | Hồ sơ hợp lệ (baseline) |
| VN-010 | Phòng Khám Thái Bình | Kê khống 15 xét nghiệm cho cảm cúm thông thường |
| VN-011 | BV Tư Nhân Phú Nhuận | Nâng hạng phẫu thuật — u nang nhỏ khai là phẫu thuật nội soi phức tạp |
| VN-012 | BV Khu Vực Miền Núi | Nằm viện 10 ngày không cần thiết cho viêm họng |
| VN-013 | Phòng Khám Minh Đức | Kê 8 loại thuốc biệt dược đắt tiền cho cảm lạnh |
| VN-014 | BV Phục Hồi Chức Năng | Khai khống 30 ngày điều trị (thực tế 3 ngày) |
| VN-015 | BV Đa Khoa Tỉnh Thanh Hóa | Phantom claim — mô tả hồ sơ trống hoàn toàn |
| VN-016/B/C | Phòng Khám Tim Mạch | Tách 1 đợt điều trị thành 3 hồ sơ riêng biệt |
| VN-017 | Trung Tâm Chẩn Đoán HN | CT scan 3 lần không cần thiết cho đau đầu |
| VN-018 | BV Tư Nhân Phú Nhuận | Khai phòng dịch vụ VIP cho bệnh nhân phòng thường |
| VN-019 | BV Hữu Nghị Việt Đức | Trùng lặp hồ sơ — cùng bệnh nhân + chẩn đoán |
| VN-020 | Phòng Khám Nam Định | 20 dịch vụ kỹ thuật cho khám sức khỏe bình thường |
| VN-021 | Phòng Khám Thái Bình | Nhập viện viêm phổi cho ca cảm cúm nhẹ |
| VN-022 – VN-025 | Các BV tuyến TW | Hồ sơ bình thường — sinh thường, tái khám, xét nghiệm, chấn thương |

---

## Project Structure

```
fraud-risks-system/
├── docker-compose.yml              # PostgreSQL + Neo4j services (v1 legacy + v2 active)
├── backend/
│   ├── .env.example                # Configuration template
│   ├── requirements.txt
│   ├── data/
│   │   └── sample_claims.csv       # 25 hồ sơ BHYT Việt Nam tổng hợp
│   └── app/
│       ├── main.py                 # FastAPI entry point + lifespan
│       ├── config.py               # Pydantic settings
│       ├── database.py             # SQLAlchemy async engine
│       ├── models.py               # ORM: Claim, FraudAnalysis, Review, BatchRun
│       ├── schemas.py              # Pydantic request/response models
│       ├── fraud_analyzer.py       # Qwen2.5 LLM (SiliconFlow) — prompt + phân tích bằng tiếng Việt, ngưỡng VND
│       ├── batch_pipeline.py       # APScheduler nightly job + graph enrichment trigger
│       ├── graph_engine.py         # Neo4j patient profile graph sync + 4 Cypher fraud queries
│       ├── feature_extractor.py    # ML feature extraction (Phase 2 prep)
│       └── routers/
│           ├── claims.py           # Claim upload and listing
│           ├── review.py           # Review queue (network_risk field) and decisions
│           ├── batch.py            # Batch trigger and status
│           └── health.py           # Health check
└── frontend/
    ├── vite.config.js
    └── src/
        ├── App.jsx                 # Root component + tab nav
        ├── api.js                  # Fetch wrapper
        └── components/
            ├── ReviewQueue.jsx     # Claims table + Network Risk badge column
            ├── ClaimDetail.jsx     # Claim drawer: AI analysis + Network Signals section
            ├── RiskBadge.jsx       # Color-coded risk indicator
            ├── DecisionPanel.jsx   # Legitimate / Suspicious / Fraud buttons
            └── UploadClaims.jsx    # CSV drag-and-drop upload
```

---

## Graph Schema

```
(:Patient {patient_id, claim_count, total_billed})
(:Provider {provider_id, provider_name, claim_count, total_billed, high_risk_count})
(:Claim {claim_id, db_id, amount, service_date, combined_score, risk_level})
(:Diagnosis {code})
(:Procedure {code})

(Patient)-[:SUBMITTED]→(Claim)
(Claim)-[:TREATED_BY]→(Provider)
(Claim)-[:CODED_WITH]→(Diagnosis)
(Claim)-[:BILLED_FOR]→(Procedure)
```

Nodes are upserted (MERGE) after each batch run. Graph flags are prefixed `graph_` in `fraud_analyses.rule_flags` so the frontend can distinguish them from per-claim rule flags.

---

## Evolution Roadmap

### Phase 1 — Current
LLM narrative scoring + rule-based signals + Neo4j network fraud detection + HITL review + label accumulation.

### Phase 2 — After ~500 labeled reviews
Train an XGBoost/LightGBM classifier on structured features extracted by `feature_extractor.py` (claim amount ratios, code counts, submission timing, provider frequency). Blend ML score with LLM + graph scores for higher precision.

### Phase 3 — Scale
- **Active learning** — prioritize borderline cases for investigator review
- **Embedding fine-tuning** on the healthcare claim domain
- **Real-time scoring** for high-priority claims before batch
- **Adjuster graph** — extend the graph to link adjusters for collusion detection

---

## Bảo Mật & Tuân Thủ Pháp Luật Việt Nam

Hệ thống sử dụng SiliconFlow API (cloud, máy chủ đặt tại Trung Quốc). Hồ sơ BHYT chứa thông tin sức khỏe cá nhân thuộc phạm vi bảo vệ theo pháp luật Việt Nam.

**Trước khi xử lý dữ liệu bệnh nhân thực:**

- Tuân thủ **Nghị định 13/2023/NĐ-CP** về bảo vệ dữ liệu cá nhân và **Luật An toàn thông tin mạng 2015**
- Ký **thỏa thuận bảo mật dữ liệu** với nhà cung cấp API (SiliconFlow Data Processing Agreement)
- Hoặc chuyển sang **LLM cục bộ** (Qwen2.5 via Ollama) bằng cách đổi `LLM_API_BASE=http://localhost:11434/v1` và `LLM_API_KEY=ollama` trong `.env` — không cần thay đổi code
- **Ẩn danh hóa** thông tin định danh bệnh nhân (họ tên, số CMND, địa chỉ) trong narrative trước khi gửi lên API
- Neo4j chạy hoàn toàn on-premises — không có dữ liệu bệnh nhân rời khỏi hạ tầng nội bộ qua tầng đồ thị
