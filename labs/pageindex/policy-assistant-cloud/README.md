# Trợ lý chính sách — PageIndex Cloud + Gemini

Ứng dụng FastAPI hỏi đáp tài liệu chính sách **tiếng Việt**, dùng:

- **PageIndex Cloud** (qua API key) để dựng *cây tri thức* (knowledge tree) cho mỗi
  tài liệu PDF, rồi **tải cây về máy dưới dạng JSON**.
- **Gemini** (`gemini-2.5-flash`) để điều hướng cây JSON, lấy nội dung node liên quan
  và sinh câu trả lời tiếng Việt **có trích dẫn trang/điều khoản**.

Khác với cách chạy PageIndex cục bộ: việc dựng cây được giao cho nền tảng PageIndex
online; máy của bạn chỉ giữ các tệp JSON đã tải về (xem mẫu
`../document-structure-pi-*.json`) và tìm kiếm trên đó.

## Kiến trúc

```
PDF ─▶ PageIndex Cloud (dựng cây) ─▶ tải về tree_storage/{doc_id}.json
                                                  │
câu hỏi ─▶ Gemini điều hướng cây ─▶ lấy text node ─▶ Gemini trả lời (tiếng Việt + trích dẫn)
```

Một câu hỏi sẽ fan-out qua các cây liên quan rồi tổng hợp thành một câu trả lời
duy nhất (kho đơn — single corpus, không phân loại lĩnh vực).

## Cài đặt

```powershell
cd backend
pip install -r requirements.txt
```

Tạo tệp `backend/.env` (tham khảo `.env.example`):

```
PAGEINDEX_API_KEY=...    # https://dash.pageindex.ai/api-keys
GEMINI_API_KEY=...       # https://aistudio.google.com/app/apikey
```

## Chạy

```powershell
cd backend
uvicorn app.main:app --reload
```

Mở tài liệu API tương tác tại http://127.0.0.1:8000/docs

## Các endpoint

| Method | Đường dẫn            | Mô tả                                             |
| ------ | -------------------- | ------------------------------------------------- |
| GET    | `/health`            | Trạng thái + số tài liệu đã nạp + hiện diện key   |
| POST   | `/ingest/upload`     | Tải PDF lên cloud, dựng cây, tải JSON về          |
| GET    | `/ingest/list`       | Danh sách tài liệu đã nạp                         |
| DELETE | `/ingest/{doc_id}`   | Xoá tài liệu (cục bộ + cloud)                     |
| POST   | `/chat`              | Hỏi đáp dựa trên các cây đã nạp                   |

## Ví dụ

Nạp tài liệu mẫu (PDF chính sách phúc lợi nằm ở thư mục cha của dự án):

```powershell
curl.exe -F "file=@../../chinh_sach_phuc_loi.pdf" http://127.0.0.1:8000/ingest/upload
```

Đặt câu hỏi:

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat `
  -H "Content-Type: application/json" `
  -d '{\"message\": \"Thưởng Tết Nguyên Đán được tính như thế nào?\"}'
```

Trả về (rút gọn):

```json
{
  "answer": "Thưởng Tết Nguyên Đán được tính theo thâm niên ...",
  "citations": [{"document": "chinh_sach_phuc_loi.pdf", "page": 2, "section": "2.2 Thưởng Tết Nguyên Đán"}],
  "documents_consulted": ["chinh_sach_phuc_loi.pdf"]
}
```

## Giao diện web (frontend)

Frontend là ứng dụng Vite + React (không phụ thuộc nặng), gọi backend qua proxy `/api`.

```powershell
cd frontend
npm install
npm run dev
```

Mở http://localhost:5173. Giao diện cho phép: tải lên PDF (xây cây trên cloud), xem
danh sách tài liệu đã nạp (kèm số node, có nút xoá), và hỏi đáp với câu trả lời tiếng
Việt kèm trích dẫn `tên tài liệu · tr.X`. Vite proxy chuyển `/api/*` sang
`http://127.0.0.1:8000` (đã strip tiền tố `/api`), nên hãy chạy backend trước.

## Cấu trúc dự án

```
backend/
  app/
    config.py            # cấu hình (.env): API key, model, ngân sách token
    schemas.py           # model Gemini (TreeNavigation, GroundedAnswer) + API
    context_budget.py    # cắt ngữ cảnh theo token
    prompts.py           # toàn bộ prompt tiếng Việt
    services/
      pageindex_cloud.py  # nộp PDF, chờ xử lý, tải cây JSON, sổ đăng ký
      search_service.py   # điều hướng cây + sinh câu trả lời tiếng Việt
    routers/             # health, ingest, chat
    main.py              # khởi tạo app + wiring service
  tree_storage/          # cây JSON đã tải về + registry.json
  data/documents/        # nơi lưu tạm PDF đã upload
```

## Ghi chú

- Nội dung trả lời lấy trực tiếp từ trường `text` của node trong cây JSON, nên
  **không cần giữ lại PDF** sau khi đã tải cây về.
- Code chịu được khác biệt định dạng số trang giữa các phiên bản cây
  (`start_index/end_index` hoặc `page_index`).
