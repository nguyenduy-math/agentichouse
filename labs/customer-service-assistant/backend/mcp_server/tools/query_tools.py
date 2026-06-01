import json

KNOWLEDGE_BASE = [
    {
        "id": "kb001",
        "category": "giao_hang",
        "question": "Thời gian giao hàng là bao lâu?",
        "answer": "Thời gian giao hàng tiêu chuẩn từ 3-5 ngày làm việc đối với nội thành và 5-7 ngày đối với tỉnh/thành phố xa. Đơn hàng hỏa tốc giao trong 2-4 giờ tại TP. HCM và Hà Nội.",
    },
    {
        "id": "kb002",
        "category": "doi_tra",
        "question": "Chính sách đổi trả hàng như thế nào?",
        "answer": "Khách hàng được đổi trả trong vòng 30 ngày kể từ ngày nhận hàng nếu sản phẩm lỗi do nhà sản xuất. Sản phẩm phải còn nguyên vẹn, đầy đủ phụ kiện và hóa đơn mua hàng.",
    },
    {
        "id": "kb003",
        "category": "thanh_toan",
        "question": "Có những phương thức thanh toán nào?",
        "answer": "Chúng tôi chấp nhận: Tiền mặt khi nhận hàng (COD), Chuyển khoản ngân hàng, Thẻ tín dụng/ghi nợ (Visa, Mastercard, JCB), Ví điện tử (MoMo, ZaloPay, VNPay).",
    },
    {
        "id": "kb004",
        "category": "bao_hanh",
        "question": "Chính sách bảo hành sản phẩm như thế nào?",
        "answer": "Sản phẩm điện tử được bảo hành 12-24 tháng tùy nhà sản xuất. Phụ kiện và thiết bị nhỏ bảo hành 6 tháng. Bảo hành không bao gồm hư hỏng do sử dụng sai cách hoặc tác động vật lý.",
    },
    {
        "id": "kb005",
        "category": "tai_khoan",
        "question": "Làm thế nào để đặt lại mật khẩu?",
        "answer": "Vào trang đăng nhập, chọn 'Quên mật khẩu', nhập email đã đăng ký. Hệ thống gửi link đặt lại mật khẩu trong vòng 5 phút. Kiểm tra thư mục spam nếu không nhận được email.",
    },
    {
        "id": "kb006",
        "category": "khuyen_mai",
        "question": "Làm thế nào để sử dụng mã giảm giá?",
        "answer": "Nhập mã giảm giá vào ô 'Mã khuyến mãi' tại trang thanh toán. Mỗi đơn hàng chỉ áp dụng 1 mã. Mã có điều kiện về giá trị đơn hàng tối thiểu, vui lòng kiểm tra điều khoản của từng mã.",
    },
    {
        "id": "kb007",
        "category": "van_chuyen",
        "question": "Phí vận chuyển được tính như thế nào?",
        "answer": "Miễn phí vận chuyển cho đơn hàng từ 500.000đ. Đơn dưới 500.000đ phí vận chuyển từ 20.000đ - 40.000đ tùy khu vực. Giao hỏa tốc phụ thu thêm 30.000đ.",
    },
    {
        "id": "kb008",
        "category": "hoan_tien",
        "question": "Quy trình hoàn tiền diễn ra như thế nào?",
        "answer": "Sau khi xác nhận hoàn hàng, tiền được hoàn trong 3-5 ngày làm việc qua phương thức thanh toán gốc. Ví điện tử hoàn ngay lập tức, thẻ ngân hàng có thể mất 7-10 ngày tùy ngân hàng.",
    },
]

ORDERS = {
    "ORD-2024-001": {
        "id": "ORD-2024-001",
        "customer_id": "CUST-001",
        "status": "đang vận chuyển",
        "items": [{"name": "Điện thoại Samsung Galaxy A55", "quantity": 1, "price": 8990000}],
        "total": 8990000,
        "order_date": "2024-05-28",
        "estimated_delivery": "2024-06-03",
        "tracking_number": "VNP123456789",
        "carrier": "Viettel Post",
    },
    "ORD-2024-002": {
        "id": "ORD-2024-002",
        "customer_id": "CUST-001",
        "status": "đã giao hàng",
        "items": [
            {"name": "Tai nghe Sony WH-1000XM5", "quantity": 1, "price": 6490000},
            {"name": "Cáp USB-C", "quantity": 2, "price": 150000},
        ],
        "total": 6790000,
        "order_date": "2024-05-20",
        "delivery_date": "2024-05-24",
        "tracking_number": "VNP987654321",
        "carrier": "GHTK",
    },
    "ORD-2024-003": {
        "id": "ORD-2024-003",
        "customer_id": "CUST-002",
        "status": "đang xử lý",
        "items": [{"name": "Laptop Dell Inspiron 15", "quantity": 1, "price": 15990000}],
        "total": 15990000,
        "order_date": "2024-06-01",
        "estimated_delivery": "2024-06-06",
        "tracking_number": None,
        "carrier": None,
    },
    "ORD-2024-004": {
        "id": "ORD-2024-004",
        "customer_id": "CUST-002",
        "status": "đã hủy",
        "items": [{"name": "Bàn phím cơ Keychron K2", "quantity": 1, "price": 2290000}],
        "total": 2290000,
        "order_date": "2024-05-15",
        "cancel_date": "2024-05-16",
        "cancel_reason": "Khách hàng yêu cầu hủy",
    },
}

CUSTOMERS = {
    "CUST-001": {
        "id": "CUST-001",
        "name": "Nguyễn Văn An",
        "email": "nguyenvanan@email.com",
        "phone": "0901234567",
        "member_since": "2022-03-15",
        "tier": "Thành viên Vàng",
        "total_orders": 15,
        "total_spent": 45670000,
    },
    "CUST-002": {
        "id": "CUST-002",
        "name": "Trần Thị Bình",
        "email": "tranthibinh@email.com",
        "phone": "0912345678",
        "member_since": "2023-07-20",
        "tier": "Thành viên Bạc",
        "total_orders": 5,
        "total_spent": 18280000,
    },
    "GUEST": {
        "id": "GUEST",
        "name": "Khách vãng lai",
        "email": None,
        "phone": None,
        "member_since": None,
        "tier": "Khách",
        "total_orders": 0,
        "total_spent": 0,
    },
}


def register_query_tools(mcp):
    @mcp.tool()
    def search_knowledge_base(query: str) -> str:
        """Tìm kiếm cơ sở kiến thức về sản phẩm, dịch vụ và chính sách công ty"""
        query_words = query.lower().split()
        scored = []
        for entry in KNOWLEDGE_BASE:
            text = (entry["question"] + " " + entry["answer"]).lower()
            score = sum(1 for w in query_words if len(w) > 1 and w in text)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [e for _, e in scored[:3]]

        if not results:
            return json.dumps(
                {"found": False, "message": "Không tìm thấy thông tin liên quan"},
                ensure_ascii=False,
            )
        return json.dumps({"found": True, "results": results}, ensure_ascii=False)

    @mcp.tool()
    def get_order_status(order_id: str) -> str:
        """Tra cứu trạng thái đơn hàng theo mã đơn hàng (ví dụ: ORD-2024-001)"""
        normalized = order_id.strip().upper().replace(" ", "-")
        order = ORDERS.get(normalized)
        if not order:
            # Partial match
            for k, v in ORDERS.items():
                if normalized in k or k in normalized:
                    order = v
                    break
        if not order:
            return json.dumps(
                {"found": False, "message": f"Không tìm thấy đơn hàng '{order_id}'"},
                ensure_ascii=False,
            )
        return json.dumps({"found": True, "order": order}, ensure_ascii=False)

    @mcp.tool()
    def get_customer_profile(customer_id: str) -> str:
        """Lấy thông tin hồ sơ và lịch sử đơn hàng gần đây của khách hàng"""
        profile = CUSTOMERS.get(customer_id.upper(), CUSTOMERS["GUEST"])
        recent_orders = [o for o in ORDERS.values() if o["customer_id"] == customer_id.upper()]
        return json.dumps(
            {"profile": profile, "recent_orders": recent_orders[-3:]},
            ensure_ascii=False,
        )
