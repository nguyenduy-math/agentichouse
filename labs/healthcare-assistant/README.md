# Insurance Guide Virtual Assistant

Trợ lý hội thoại bảo hiểm hai chế độ dành cho thị trường Việt Nam:

| Chế độ | Mô tả |
|---|---|
| **Khai thác bảo hiểm** | Hướng dẫn người dùng nộp hồ sơ yêu cầu bồi thường BHYT hoặc bảo hiểm thương mại |
| **Tư vấn gói bảo hiểm** | Thu thập hồ sơ sức khỏe và đề xuất 2-3 gói bảo hiểm phù hợp nhất |

Người dùng chọn chế độ ngay trên màn hình chào, sau đó trợ lý dẫn dắt qua từng bước bằng hội thoại tự nhiên tiếng Việt.

---

## Tính năng

- **Hai chế độ trên cùng giao diện** — Màn hình chọn chế độ trước khi bắt đầu hội thoại
- **Luồng theo pha** — `identifying → collecting → confirming → complete`; mỗi pha có phong cách phản hồi riêng
- **Option chips tại điểm quyết định** — Trợ lý đề xuất 2-3 lựa chọn nhanh (giới tính, loại công việc, ưu tiên quyền lợi…) thay vì chỉ hỏi mở
- **Điểm xác nhận trước khi tạo kết quả** — Pha `confirming` hiển thị toàn bộ thông tin đã thu thập và hỏi: xác nhận / sửa / bắt đầu lại
- **Phát hiện sửa lỗi** — Khi người dùng đính chính thông tin cũ, trợ lý xác nhận thay đổi trước khi hỏi tiếp
- **Trích xuất có cấu trúc** — Gemini `response_schema` parse ngày tháng/số tiền từ câu trả lời tự nhiên
- **Đề xuất bám sát danh mục** — Gói bảo hiểm chỉ được chọn từ catalog JSON cục bộ (`packages_catalog.json`), lọc theo điều kiện + ngân sách trước khi đưa cho Gemini — không bịa gói/công ty/mức phí
- **Thanh tiến trình thời gian thực** — % thông tin đã hoàn thiện theo loại hình/chế độ
- **Kết quả tải xuống được** — Hồ sơ bồi thường (JSON) hoặc đề xuất gói bảo hiểm (JSON)

---

## Kiến trúc

### Tổng quan

```
Browser (React SPA)
    │
    ├─ ModeSelector ──► POST /api/session/new { mode }
    │
    └─ Chat ──────────► POST /api/chat { session_id, message }
                              │
                    ┌─────────┴──────────┐
              mode=claim_filing    mode=recommendation
                    │                    │
               agent.py          advisor_agent.py
                    │                    │
                    │            catalog.py (lọc gói theo hồ sơ)
                    │                    │
            Gemini API           Gemini API
         (extract + guide)   (extract + guide + recommend)
```

### Vòng lặp Extract → Guide (dùng chung cho cả hai chế độ)

```
User message
    │
    ▼
[Call 1: Extract]  response_schema=<DataModel>  temp=0.0
    │   Chỉ trả về trường được đề cập rõ ràng, còn lại = null
    ▼
Merge vào session state
    │
    ├─ Còn thiếu trường? ──► [Call 2: Guide] temp=0.3  ──► Câu hỏi tiếp theo + option chips
    │
    └─ Đủ thông tin?  ──────► Pha confirming (text summary + 3 option chips)
                                    │
                          User xác nhận
                                    │
                              [Call 3: Result]
                          claim: summary text        recommend: response_schema=RecommendationOutput
```

### Máy trạng thái phiên (`SessionPhase`)

```
                        ┌─────────────┐
                        │  identifying │  (chỉ claim flow — xác định ngoại/nội trú/thương mại)
                        └──────┬──────┘
                               │ claim_type xác định
                               ▼
  [mode=recommendation] ──► collecting ◄── [sửa thông tin từ confirming]
                               │
                    tất cả trường bắt buộc đủ
                               │
                               ▼
                          confirming  ──► option chips: [Xác nhận | Sửa | Bắt đầu lại]
                               │
                     user xác nhận ("đúng", "1", "xác nhận")
                               │
                               ▼
                           complete  ──► kết quả được cache, bỏ qua tin nhắn tiếp theo
```

---

## Chế độ khai thác bảo hiểm

### Trường bắt buộc theo loại hình

| Loại hình | Trường bắt buộc |
|---|---|
| Ngoại trú (`outpatient`) | Họ tên, Ngày sinh, Mã BHXH, Cơ sở KCB, Ngày khám, Chẩn đoán, Tổng chi phí |
| Nội trú (`inpatient`) | + Ngày nhập viện, Ngày xuất viện, Tiền tự trả |
| Thương mại (`private`) | Thay Mã BHXH bằng Số hợp đồng; thêm Ngày sự kiện, Số tài khoản ngân hàng |

### Kết quả

- Đoạn tóm tắt hồ sơ bằng tiếng Việt
- `ProposalCard` — bảng thông tin + nút "Tải xuống JSON"

---

## Chế độ tư vấn gói bảo hiểm

### Trường hồ sơ sức khỏe thu thập

| Trường | Bắt buộc | Option chips |
|---|---|---|
| Tuổi | Có | — |
| Giới tính | Có | Nam / Nữ |
| Loại công việc | Có | Văn phòng / Ngoài trời / Lao động nặng |
| Bệnh nền | Không | — |
| Hút thuốc | Có | Có hút thuốc / Không hút thuốc |
| Ngân sách hàng tháng (VNĐ) | Có | — |
| Số người cần bảo hiểm | Có | — |
| Ưu tiên quyền lợi | Có | Nội trú / Ngoại trú / Bệnh hiểm nghèo / Tai nạn / Nhân thọ |

### Cách đề xuất hoạt động (catalog grounding)

Trợ lý **không** dựa vào kiến thức mở của mô hình mà bám sát một danh mục cục bộ `backend/app/packages_catalog.json` (12 gói từ các công ty bảo hiểm hư cấu: An Tín, Trường Phúc Life, Minh An Life, Việt Khang Life, Hồng Ân…):

1. **Load** — `load_catalog()` đọc + cache JSON (`lru_cache`)
2. **Lọc** — `filter_by_profile()` áp điều kiện cứng (tuổi, hút thuốc, nghề loại trừ) → chấm điểm theo ưu tiên quyền lợi + ngân sách → giữ top 6
3. **Format** — `format_for_prompt()` chọn tier hợp ngân sách nhất, dựng văn bản đưa vào prompt
4. **Ràng buộc** — `RECOMMENDATION_SYSTEM` cấm bịa gói ngoài danh sách; `response_schema=RecommendationOutput` khóa cấu trúc đầu ra
5. **Fallback** — nếu lọc ra rỗng thì dùng 6 gói đầu của danh mục (ghi log cảnh báo)

### Kết quả

Gemini chọn 2-3 gói phù hợp nhất từ danh mục và trả về JSON:

```json
{
  "recommendations": [
    {
      "rank": 1,
      "package_type": "Bảo hiểm sức khỏe toàn diện",
      "insurer_examples": ["An Tín", "Trường Phúc Life"],
      "estimated_premium_range": "500.000 – 1.500.000 VNĐ/tháng",
      "coverage_highlights": ["Nội trú không giới hạn", "Ngoại trú 30 lần/năm"],
      "why_suitable": "Phù hợp vì...",
      "key_considerations": ["Chú ý điều khoản loại trừ bệnh nền"]
    }
  ]
}
```

`RecommendationCard` hiển thị từng gói với màu sắc theo thứ hạng + nút "Tải xuống JSON".

---

## Cấu trúc dự án

```
healthcare-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI lifespan, CORS, router registration
│   │   ├── config.py                # Pydantic-settings (đọc từ .env)
│   │   ├── schemas.py               # Tất cả models: ClaimData, HealthProfile, SessionState, …
│   │   ├── claim_schema.py          # REQUIRED_FIELDS + FIELD_META cho claim flow
│   │   ├── health_profile_schema.py # REQUIRED_PROFILE_FIELDS + PROFILE_FIELD_META + FIELD_CHIPS
│   │   ├── session_store.py         # In-memory store, asyncio.Lock, TTL tự động
│   │   ├── agent.py                 # Claim flow: extract → guide → proposal (phase dispatcher)
│   │   ├── advisor_agent.py         # Recommendation flow: extract → guide → recommend
│   │   ├── catalog.py               # Lọc/chấm điểm gói bảo hiểm theo hồ sơ + format cho prompt
│   │   ├── packages_catalog.json    # Danh mục 12 gói bảo hiểm (nguồn dữ liệu đề xuất)
│   │   ├── prompts.py               # Tất cả system prompts và prompt builders
│   │   └── routers/
│   │       ├── chat.py              # POST /chat — dispatch theo mode
│   │       ├── session.py           # POST /session/new { mode }, DELETE /session/{id}
│   │       └── health.py            # GET /health
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── App.jsx                  # State management, mode routing
    │   ├── api.js                   # newSession(mode), sendMessage()
    │   └── components/
    │       ├── ModeSelector.jsx     # Hai thẻ chọn chế độ ban đầu
    │       ├── ChatWindow.jsx       # Danh sách tin nhắn + auto-scroll
    │       ├── MessageBubble.jsx    # Bubble người dùng / trợ lý
    │       ├── OptionChips.jsx      # Hàng nút lựa chọn nhanh
    │       ├── ProgressBar.jsx      # Thanh tiến trình (% hoàn thiện)
    │       ├── ProposalCard.jsx     # Bảng hồ sơ bồi thường + tải JSON
    │       └── RecommendationCard.jsx # Các gói bảo hiểm được đề xuất + tải JSON
    ├── index.html
    ├── package.json
    └── vite.config.js               # Dev proxy /api → localhost:8002
```

---

## Cài đặt và chạy

### Yêu cầu

- Python 3.11+
- Node.js 18+
- Google Gemini API key ([lấy tại đây](https://aistudio.google.com/app/apikey))

### Backend

```bash
cd labs/healthcare-assistant/backend

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Mở .env và điền GEMINI_API_KEY

uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

API docs tương tác: [http://localhost:8002/docs](http://localhost:8002/docs)

### Frontend

```bash
cd labs/healthcare-assistant/frontend

npm install
npm run dev
# Mở http://localhost:5173
```

> Khi build production (`npm run build`), FastAPI phục vụ SPA trực tiếp — không cần chạy frontend server riêng.

---

## Biến môi trường

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `GEMINI_API_KEY` | Có | Google Gemini API key |
| `GEMINI_LLM_MODEL` | Không | Mặc định: `gemini-2.5-flash` |
| `SESSION_TTL_MINUTES` | Không | Thời gian phiên (mặc định: 60 phút) |

---

## API

### `POST /api/session/new`

Tạo phiên làm việc mới với chế độ được chỉ định.

```json
// Request
{ "mode": "claim_filing" }          // hoặc "recommendation"

// Response
{ "session_id": "uuid-string" }
```

### `POST /api/chat`

Gửi tin nhắn và nhận phản hồi.

```json
// Request
{
  "session_id": "uuid-string",
  "message": "Tôi nhập viện điều trị tuần trước"
}

// Response (claim_filing)
{
  "session_id": "uuid-string",
  "reply": "Bạn điều trị tại bệnh viện nào ạ?",
  "collected": { "claim_type": "inpatient", "name": null, ... },
  "health_profile": {},
  "proposal": null,
  "recommendation": null,
  "is_complete": false,
  "progress_pct": 22,
  "session_phase": "collecting",
  "options": null
}

// Response (recommendation) — khi đến pha confirming
{
  "session_id": "uuid-string",
  "reply": "Đây là hồ sơ tôi đã ghi nhận: ...",
  "collected": {},
  "health_profile": { "age": 30, "gender": "nam", ... },
  "proposal": null,
  "recommendation": null,
  "is_complete": false,
  "progress_pct": 100,
  "session_phase": "confirming",
  "options": ["Xác nhận, đề xuất gói bảo hiểm", "Tôi muốn sửa thông tin", "Bắt đầu lại từ đầu"]
}
```

### `DELETE /api/session/{session_id}`

Xóa phiên làm việc.

### `GET /api/health`

Kiểm tra trạng thái dịch vụ.

---

## Luồng hội thoại mẫu

### Chế độ khai thác bảo hiểm

```
[ModeSelector] User chọn "Khai thác bảo hiểm"

Trợ lý: Xin chào! Bạn muốn khai thác BHYT hay bảo hiểm thương mại?
[Chips] BHYT ngoại trú  |  BHYT nội trú  |  Bảo hiểm thương mại

User: [click] BHYT nội trú

Trợ lý: Bạn điều trị tại bệnh viện nào ạ?

User: Bệnh viện Bạch Mai, nhập viện 20/5, ra viện 25/5

Trợ lý: Cảm ơn! Chẩn đoán bệnh của bạn là gì ạ?

... [thu thập đến khi đủ thông tin]

Trợ lý: Đây là thông tin tôi đã thu thập:
         • Họ tên: Nguyễn Văn A  • Ngày sinh: 15/03/1990
         • Loại: Nội trú — BV Bạch Mai  ...
         Thông tin trên có chính xác không?
[Chips] Xác nhận, tạo hồ sơ  |  Tôi muốn sửa thông tin  |  Bắt đầu lại từ đầu

User: [click] Xác nhận, tạo hồ sơ

Trợ lý: [Tóm tắt hồ sơ tiếng Việt. Hồ sơ đã sẵn sàng tải xuống.]
[ProposalCard hiển thị với nút "Tải xuống JSON"]
```

### Chế độ tư vấn gói bảo hiểm

```
[ModeSelector] User chọn "Tư vấn gói bảo hiểm"

Trợ lý: Xin chào! Bạn bao nhiêu tuổi?

User: 32 tuổi

Trợ lý: Bạn là nam hay nữ ạ?
[Chips] Nam  |  Nữ

User: [click] Nam

Trợ lý: Công việc hiện tại của bạn thuộc loại nào?
[Chips] Văn phòng  |  Ngoài trời / di chuyển nhiều  |  Lao động nặng

... [thu thập hồ sơ sức khỏe]

Trợ lý: Đây là hồ sơ tôi đã ghi nhận: ...
[Chips] Xác nhận, đề xuất gói bảo hiểm  |  Tôi muốn sửa  |  Bắt đầu lại

User: [click] Xác nhận, đề xuất gói bảo hiểm

Trợ lý: Dựa trên hồ sơ của bạn, tôi đề xuất 3 gói bảo hiểm phù hợp nhất...
[RecommendationCard: 3 gói với chi tiết + nút "Tải xuống JSON"]
```

---

## Mở rộng

### Thêm trường vào hồ sơ sức khỏe

1. Thêm field vào `HealthProfile` trong [backend/app/schemas.py](backend/app/schemas.py)
2. Thêm metadata vào `PROFILE_FIELD_META` trong [backend/app/health_profile_schema.py](backend/app/health_profile_schema.py)
3. Thêm vào `REQUIRED_PROFILE_FIELDS` nếu bắt buộc
4. Thêm `FIELD_CHIPS` nếu muốn hiển thị option chips cho trường đó

### Thêm loại hình bảo hiểm mới (claim flow)

1. Thêm giá trị vào `ClaimType` enum trong [backend/app/schemas.py](backend/app/schemas.py)
2. Thêm danh sách trường vào `REQUIRED_FIELDS` trong [backend/app/claim_schema.py](backend/app/claim_schema.py)
3. Cập nhật mô tả loại hình trong extraction system prompt ở [backend/app/prompts.py](backend/app/prompts.py)

### Thêm chế độ mới

1. Thêm giá trị vào `AssistantMode` enum trong [backend/app/schemas.py](backend/app/schemas.py)
2. Tạo agent mới (theo mẫu `advisor_agent.py`)
3. Thêm dispatch case trong [backend/app/routers/chat.py](backend/app/routers/chat.py)
4. Thêm thẻ chọn chế độ trong [frontend/src/components/ModeSelector.jsx](frontend/src/components/ModeSelector.jsx)
