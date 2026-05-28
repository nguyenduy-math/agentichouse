# Trợ lý chính sách — PageIndex Cloud + Gemini

Ứng dụng FastAPI hỏi đáp tài liệu chính sách **tiếng Việt**, dùng:

- **PageIndex Cloud** (qua API key) để dựng *cây tri thức* (knowledge tree) cho mỗi
  tài liệu PDF, rồi **tải cây về máy dưới dạng JSON**.
- **Gemini** (`gemini-2.5-flash`) để điều hướng cây JSON, lấy nội dung node liên quan,
  **ghép cùng văn bản nguyên văn của trang PDF tương ứng** và sinh câu trả lời tiếng
  Việt **có trích dẫn trang/điều khoản**.

Khác với cách chạy PageIndex cục bộ: việc dựng cây được giao cho nền tảng PageIndex
online; máy của bạn giữ các tệp JSON đã tải về (xem mẫu
`../document-structure-pi-*.json`) **và PDF gốc** để tham chiếu chéo khi trả lời.

## Kiến trúc

```text
PDF ─▶ PageIndex Cloud (dựng cây) ─▶ tree_storage/{doc_id}.json
                                              │
câu hỏi ─▶ Gemini điều hướng cây ─▶ chọn node ─▶ ghép node text + trích trang PDF
                                                                    │
                                                                    ▼
                                              Gemini sinh câu trả lời (tiếng Việt + trích dẫn)
```

Một câu hỏi fan-out qua các cây liên quan rồi tổng hợp thành một câu trả lời duy nhất
(kho đơn — single corpus, không phân loại lĩnh vực).

## Cài đặt

```powershell
cd backend
pip install -r requirements.txt
```

Tạo tệp `backend/.env` (tham khảo `.env.example`):

```text
PAGEINDEX_API_KEY=...    # https://dash.pageindex.ai/api-keys
GEMINI_API_KEY=...       # https://aistudio.google.com/app/apikey
```

## Chạy

```powershell
cd backend
uvicorn app.main:app --reload
```

Mở tài liệu API tương tác tại <http://127.0.0.1:8000/docs>.

## Các endpoint

| Method | Đường dẫn            | Mô tả                                                                      |
| ------ | -------------------- | -------------------------------------------------------------------------- |
| GET    | `/health`            | Trạng thái + số tài liệu đã nạp + hiện diện key                            |
| POST   | `/ingest/upload`     | Tải PDF lên cloud, dựng cây, tải JSON về (đồng thời ghi PDF gốc vào sổ)    |
| GET    | `/ingest/list`       | Danh sách tài liệu đã nạp                                                  |
| DELETE | `/ingest/{doc_id}`   | Xoá tài liệu (cục bộ + cloud)                                              |
| POST   | `/chat`              | Hỏi đáp dựa trên các cây + PDF đã nạp                                      |

### Shape của `/chat`

Request:

```json
{ "message": "Thưởng Tết Nguyên Đán tính thế nào?", "history": [] }
```

Response:

```json
{
  "answer": "Thưởng Tết Nguyên Đán được tính theo thâm niên ...",
  "citations": [
    { "document": "chinh_sach_phuc_loi.pdf", "page": 2, "section": "2.2 Thưởng Tết Nguyên Đán" }
  ],
  "documents_consulted": ["chinh_sach_phuc_loi.pdf"],
  "retrieved_contexts": [
    "[Mục: 2.2 Thưởng Tết Nguyên Đán · Trang 2]\n... (node text)\n\n[Trích nguyên văn từ PDF, Trang 2]\n..."
  ]
}
```

`retrieved_contexts` là các đoạn văn bản đã đưa vào prompt sinh câu trả lời — phục vụ
chấm điểm RAGAS (xem mục **Đánh giá** bên dưới).

## Ví dụ

Nạp tài liệu mẫu (PDF nằm ở thư mục cha của dự án):

```powershell
curl.exe -F "file=@../../chinh_sach_phuc_loi.pdf" http://127.0.0.1:8000/ingest/upload
```

Đặt câu hỏi:

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat `
  -H "Content-Type: application/json" `
  -d '{\"message\": \"Thưởng Tết Nguyên Đán được tính như thế nào?\"}'
```

## Giao diện web (frontend)

Frontend là ứng dụng Vite + React (không phụ thuộc nặng), gọi backend qua proxy `/api`.

```powershell
cd frontend
npm install
npm run dev
```

Mở <http://localhost:5173>. Giao diện cho phép tải lên PDF, xem danh sách tài liệu đã
nạp (kèm số node và nút xoá), và hỏi đáp với câu trả lời tiếng Việt kèm trích dẫn
`tên tài liệu · tr.X`. Vite proxy chuyển `/api/*` sang `http://127.0.0.1:8000` (đã
strip tiền tố `/api`), nên hãy chạy backend trước.

## Đánh giá (RAGAS)

Bộ đánh giá hiệu năng RAG sống trong thư mục [`eval/`](./eval), dùng
[RAGAS](https://docs.ragas.io/) với **OpenAI làm judge** (gpt-4o-mini +
text-embedding-3-small) và 5 chỉ số: `faithfulness`, `answer_relevancy`,
`context_precision`, `context_recall`, `answer_correctness`. Hỗ trợ cả single-turn
(`policy_eval.py`) lẫn multi-turn (`policy_eval_multiturn.py`). Bộ câu hỏi tiếng Việt
được viết riêng cho `chinh_sach_phuc_loi.pdf` (10 câu single-turn + 3 hội thoại × 3
lượt). Xem [eval/README.md](./eval/README.md) để biết cách cài đặt và chạy.

## Cấu trúc dự án

```text
backend/
  app/
    config.py            # cấu hình (.env): API key, model, ngân sách token
    schemas.py           # model Gemini (TreeNavigation, GroundedAnswer) + API
    context_budget.py    # cắt ngữ cảnh theo token
    prompts.py           # toàn bộ prompt tiếng Việt
    services/
      pageindex_cloud.py  # nộp PDF, chờ xử lý, tải cây JSON, sổ đăng ký (lưu cả pdf_path)
      search_service.py   # điều hướng cây + ghép node text với trang PDF + sinh câu trả lời
    routers/             # health, ingest, chat
    main.py              # khởi tạo app + wiring service
  tree_storage/          # cây JSON đã tải về + registry.json
  data/documents/        # nơi lưu PDF đã upload (dùng cả khi trả lời)
frontend/                # Vite + React 18 (upload, danh sách tài liệu, hỏi đáp)
eval/                    # RAGAS eval (single-turn + multi-turn, judge OpenAI)
```

## Ghi chú

- Câu trả lời lấy từ **cả hai nguồn**: trường `text` của node trong cây JSON (tóm tắt
  có cấu trúc của PageIndex) **và** văn bản nguyên văn các trang PDF tương ứng. Nếu
  thiếu PDF (entry cũ không có `pdf_path`) → tự động fallback sang chỉ dùng node text.
- Code chịu được khác biệt định dạng số trang giữa các phiên bản cây cloud
  (`start_index/end_index` hoặc `page_index`).
- Token budget trong `config.py` (`answer_content_budget_tokens = 4500`) đã tính tới
  việc mỗi section bây giờ bao gồm cả node text lẫn trích PDF.
