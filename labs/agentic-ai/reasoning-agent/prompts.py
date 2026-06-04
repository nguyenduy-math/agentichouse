TRANSPORT_EXPANDER_PROMPT = """Bạn đang hỗ trợ lập kế hoạch chuyến đi 3 ngày từ Hà Nội đến Đà Nẵng với tổng ngân sách 300 USD.

Các phương tiện di chuyển khả dụng:
{flight_data}

Hãy tạo đúng 3 phương án di chuyển (máy bay, tàu hỏa, xe buýt). Với mỗi phương án, cung cấp:
1. Một câu mô tả ngắn (hãng/nhà cung cấp, giá một chiều, thời gian di chuyển)
2. Chi phí khứ hồi tính bằng USD

Chỉ trả về một mảng JSON hợp lệ, không thêm bất kỳ nội dung nào khác:
[
  {{"id": "fly-vietjet", "thought": "Bay VietJet: $55 một chiều, 1 giờ 10 phút. Khứ hồi $110.", "cost": 110.0}},
  {{"id": "train", "thought": "Tàu hỏa qua đêm: $25 một chiều, 16 giờ. Khứ hồi $50.", "cost": 50.0}},
  {{"id": "bus", "thought": "Xe giường nằm: $15 một chiều, 18 giờ. Khứ hồi $30.", "cost": 30.0}}
]"""

HOTEL_EXPANDER_PROMPT = """Bạn đang lập kế hoạch chỗ ở tại Đà Nẵng cho 3 đêm.
Phương tiện di chuyển đã chọn: {transport_description} (đã chi ${transport_cost:.0f}, còn lại ${remaining:.0f} trong tổng ngân sách $300).

Các khách sạn khả dụng:
{hotel_data}

Hãy tạo đúng 2 phương án chỗ ở — một phương án bình dân (~$14-18/đêm), một phương án tầm trung (~$42-48/đêm).
Chỉ đề xuất các phương án còn đủ ngân sách cho hoạt động vui chơi.

Chỉ trả về một mảng JSON hợp lệ, không thêm bất kỳ nội dung nào khác:
[
  {{"id": "{parent_id}-hostel", "thought": "Ở Memory Hostel: $18/đêm x 3 = $54.", "nightly_cost": 18.0, "total_hotel_cost": 54.0}},
  {{"id": "{parent_id}-boutique", "thought": "Ở Blooming Boutique Hotel: $42/đêm x 3 = $126.", "nightly_cost": 42.0, "total_hotel_cost": 126.0}}
]"""

ACTIVITIES_EXPANDER_PROMPT = """Bạn đang lập kế hoạch hoạt động tại Đà Nẵng cho 3 ngày.
Phương tiện và chỗ ở đã chọn: {path_so_far}
Đã chi: ${cost_so_far:.0f}. Ngân sách còn lại: ${remaining:.0f}.

Các hoạt động khả dụng:
{activity_data}

Hãy tạo 2 kế hoạch hoạt động đều nằm trong ngân sách còn lại:
- Kế hoạch 1: tiết kiệm (hoạt động miễn phí hoặc rẻ, ăn đường phố)
- Kế hoạch 2: trải nghiệm (điểm tham quan có phí + nhà hàng) — chỉ đề xuất nếu vừa ngân sách

Với mỗi kế hoạch, liệt kê các hoạt động và tính tổng chi phí hoạt động (3 ngày ăn uống cơ bản $10/ngày đã được tính sẵn, chỉ cộng thêm chi phí nâng cấp nếu có).

Chỉ trả về một mảng JSON hợp lệ, không thêm bất kỳ nội dung nào khác:
[
  {{
    "id": "{parent_id}-budget",
    "thought": "Bãi biển Mỹ Khê (miễn phí) + Ngũ Hành Sơn ($2) + ăn đường phố ($30 cho 3 ngày). Tổng hoạt động: $32.",
    "activities_cost": 32.0
  }},
  {{
    "id": "{parent_id}-premium",
    "thought": "Bà Nà Hills ($35) + Tham quan Hội An ($10) + nhà hàng ($40). Tổng hoạt động: $85.",
    "activities_cost": 85.0
  }}
]"""

SCORER_PROMPT = """Hãy đánh giá kế hoạch du lịch một phần dưới đây từ 0.0 đến 1.0.

Tiêu chí chấm điểm:
- Sự thoải mái: Phương tiện và chỗ ở có hợp lý không? (trọng số: 30%)
- Chất lượng trải nghiệm: Các hoạt động/lựa chọn có tạo nên chuyến đi đáng nhớ không? (trọng số: 40%)
- Giá trị đồng tiền: Kế hoạch có sử dụng ngân sách hiệu quả không? (trọng số: 30%)

1.0 = xuất sắc ở tất cả tiêu chí. 0.0 = kém ở tất cả tiêu chí.

Kế hoạch du lịch một phần:
{branch_description}

Chỉ trả về một số thực duy nhất từ 0.0 đến 1.0. Không giải thích."""

SOLVER_PROMPT = """Bạn là chuyên gia lập kế hoạch du lịch. Hãy viết lịch trình chi tiết 3 ngày cho chuyến đi từ Hà Nội đến Đà Nẵng dựa trên kế hoạch đã chọn sau:

Phương tiện di chuyển: {transport_thought}
Chỗ ở: {hotel_thought}
Hoạt động: {activities_thought}
Tổng chi phí ước tính: ${total_cost:.0f} (ngân sách: $300)

Viết lịch trình theo định dạng sau:

## Ngày 1 — Đến nơi & Khám phá ban đầu
[Phân theo Sáng / Chiều / Tối với giờ cụ thể, tên địa điểm, mẹo hay]

## Ngày 2 — [Chủ đề]
[...]

## Ngày 3 — [Chủ đề & Khởi hành]
[...]

## Bảng chi phí
| Hạng mục | Chi phí |
|----------|---------|
| Vé máy bay/tàu/xe (khứ hồi) | $X |
| Chỗ ở (3 đêm) | $X |
| Hoạt động | $X |
| Ăn uống ước tính | $X |
| **Tổng cộng** | **$X** |

## Mẹo thực tế
[3-5 gạch đầu dòng: lời khuyên đặt vé, phương tiện địa phương, thời tiết, v.v.]"""
