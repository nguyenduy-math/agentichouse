# Eval RAGAS cho policy-assistant-cloud

Bộ đánh giá hiệu năng RAG cho dự án [`policy-assistant-cloud`](..), dùng
[RAGAS](https://docs.ragas.io/) với **OpenAI làm judge LLM và embeddings**. Phỏng theo
`agentichouse/eval-v2/` nhưng điều chỉnh cho backend mới (stateless `/chat`, lấy
`retrieved_contexts` trực tiếp từ response).

## Yêu cầu

| Mục | Ghi chú |
|---|---|
| Python 3.11–3.13 | **Không dùng 3.14** — `pydantic-core` và một số dep Rust chưa có wheel |
| OpenAI API key | Judge LLM + embeddings |
| Backend policy-assistant-cloud | Chạy ở `http://127.0.0.1:8000` (mặc định) với ít nhất 1 tài liệu đã nạp |

## Cài đặt (Windows PowerShell, Python 3.13)

```powershell
cd labs/pageindex/policy-assistant-cloud/eval

# Tạo venv mới với Python 3.13
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version   # phải in 3.13.x

python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

Copy-Item .env.example .env
# mở .env, điền OPENAI_API_KEY
```

## Sử dụng

```powershell
# Single-turn — chạy đầy đủ
python policy_eval.py

# Chỉ thu thập câu trả lời, không gọi OpenAI (không tốn chi phí)
python policy_eval.py --dry-run

# Đổi model judge
python policy_eval.py --model gpt-4o

# Multi-turn — chạy toàn bộ set
python policy_eval_multiturn.py

# Multi-turn — chỉ 1 set
python policy_eval_multiturn.py --set CS-001
```

Kết quả CSV được lưu trong `results/` với tên `policy_eval_<timestamp>.csv` (hoặc
`policy_eval_multiturn_<timestamp>.csv`).

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `OPENAI_API_KEY` | *(bắt buộc)* | Khoá OpenAI |
| `OPENAI_JUDGE_MODEL` | `gpt-4o-mini` | Model làm judge |
| `POLICY_API_URL` | `http://127.0.0.1:8000` | URL backend |

CLI ghi đè `.env`: `--model`, `--dry-run`, `--set <ID>`.

## 5 chỉ số RAGAS

| Metric | Ý nghĩa | Cần |
|---|---|---|
| `faithfulness` | Mọi tuyên bố trong câu trả lời có được nguồn dẫn chứng không? | LLM |
| `answer_relevancy` | Câu trả lời có đúng trọng tâm câu hỏi không? | LLM + embedding |
| `context_precision` | Các đoạn liên quan có được xếp đầu retrieval không? | LLM + reference |
| `context_recall` | Các đoạn truy xuất có đủ thông tin để trả lời đúng không? | LLM + reference |
| `answer_correctness` | Câu trả lời có khớp ground truth không? | LLM + embedding |

Tất cả thang điểm **[0, 1]** — càng cao càng tốt.

## Bộ câu hỏi

- `eval_questions.json` — 10 câu single-turn bám sát `chinh_sach_phuc_loi.pdf`
  (thưởng, phụ cấp, đào tạo, quà tặng, team building, fallback ngoài phạm vi).
- `eval_conversation_sets.json` — 3 hội thoại nhiều lượt:
  - **CS-001 Thưởng cuối năm** (3 lượt)
  - **CS-002 Đào tạo & phát triển** (3 lượt)
  - **CS-003 Phúc lợi đời thường** (3 lượt)

Mỗi câu có `expected_answer_summary` làm ground truth cho `context_recall` và
`answer_correctness`.

## Luồng hoạt động

```
eval_questions.json  /  eval_conversation_sets.json
      │
      ▼
[1] Gọi backend (POST /chat) → answer + retrieved_contexts
      │
      ▼
[2] Dựng RAGAS EvaluationDataset (SingleTurnSample / lượt)
      │
      ▼
[3] evaluate() với judge OpenAI
      │  LLM:        ChatOpenAI (gpt-4o-mini)
      │  Embeddings: OpenAIEmbeddings (text-embedding-3-small)
      ▼
[4] Lưu CSV + in bảng tổng kết (per-metric, per-set với multi-turn)
```

## Khác biệt so với eval-v2

| | eval-v2 (graphrag-assistant) | eval/ (policy-assistant-cloud) |
|---|---|---|
| Backend session | `/api/v1/session` + `/api/v1/chat` | stateless `/chat` |
| Multi-turn | session_id giữ history server-side | client truyền `history` mỗi lượt |
| Retrieved contexts | `sources[].excerpt` | `retrieved_contexts` (node text + trích PDF) |
| Question set | Eval set chung của graphrag | Bộ riêng cho `chinh_sach_phuc_loi.pdf` |
