"""User-facing messages per status/guardrail code, in Vietnamese and English."""

MESSAGES: dict[str, tuple[str, str]] = {
    "INJECTION_SUSPECTED": (
        "Câu hỏi có dấu hiệu cố gắng thay đổi chỉ dẫn của hệ thống nên đã bị chặn.",
        "The question looks like an attempt to override the assistant's instructions and was blocked.",
    ),
    "WRITE_INTENT": (
        "Trợ lý chỉ đọc dữ liệu, không thể thêm, sửa hay xóa dữ liệu.",
        "The assistant is read-only; it cannot create, change or delete data.",
    ),
    "OUT_OF_SCOPE": (
        "Câu hỏi nằm ngoài phạm vi dữ liệu kinh doanh (bán hàng, khách hàng, tồn kho…).",
        "That question is outside the business data (sales, customers, inventory, …).",
    ),
    "EMPTY_QUESTION": ("Vui lòng nhập câu hỏi.", "Please enter a question."),
    "INPUT_TOO_LONG": (
        "Câu hỏi quá dài (tối đa 500 ký tự).",
        "The question is too long (500 characters max).",
    ),
    "NON_SELECT": (
        "Truy vấn sinh ra không phải câu lệnh đọc dữ liệu nên đã bị chặn.",
        "The generated query was not a read-only SELECT and was blocked.",
    ),
    "MULTI_STATEMENT": (
        "Truy vấn chứa nhiều câu lệnh nên đã bị chặn.",
        "The query had multiple statements and was blocked.",
    ),
    "FORBIDDEN_OBJECT": (
        "Truy vấn chạm tới đối tượng hệ thống không được phép nên đã bị chặn.",
        "The query touched a forbidden system object and was blocked.",
    ),
    "TABLE_NOT_ALLOWED": (
        "Truy vấn cần dữ liệu mà vai trò của bạn không được xem.",
        "The query needs data your role is not allowed to see.",
    ),
    "COLUMN_NOT_ALLOWED": (
        "Truy vấn dùng cột không có hoặc không được phép.",
        "The query used a column that does not exist or is not allowed.",
    ),
    "UNKNOWN_TABLE": (
        "Truy vấn dùng bảng không tồn tại.",
        "The query used a table that does not exist.",
    ),
    "SYNTAX_ERROR": ("Không tạo được câu SQL hợp lệ.", "Could not produce valid SQL."),
    "COST_TOO_HIGH": (
        "Truy vấn quá nặng so với ngưỡng cho phép. Hãy thu hẹp thời gian hoặc phạm vi.",
        "The query is too expensive. Try a narrower time range or scope.",
    ),
    "DB_TIMEOUT": (
        "Truy vấn chạy quá thời gian cho phép (10 giây).",
        "The query exceeded the 10-second time limit.",
    ),
    "DB_ERROR": ("Truy vấn lỗi khi chạy trên kho dữ liệu.", "The query failed on the warehouse."),
    "DB_PERMISSION": (
        "Vai trò của bạn không có quyền đọc dữ liệu này.",
        "Your role cannot read this data.",
    ),
    "DB_UNAVAILABLE": (
        "Kho dữ liệu tạm thời không truy cập được.",
        "The warehouse is temporarily unavailable.",
    ),
    "NO_FALLBACK_MATCH": (
        "Hiện không có mô hình AI nào khả dụng và câu hỏi này nằm ngoài các mẫu dự phòng. Hãy thử một trong các câu gợi ý.",
        "No AI model is available right now and this question is outside the fallback templates. Try one of the suggestions.",
    ),
    "UNANSWERABLE": (
        "Không thể trả lời câu hỏi này từ dữ liệu hiện có.",
        "This question cannot be answered from the available data.",
    ),
    "RATE_LIMITED": (
        "Bạn hỏi quá nhanh, vui lòng thử lại sau ít phút.",
        "Too many questions; please retry shortly.",
    ),
    "INTERNAL_ERROR": (
        "Có lỗi hệ thống. Vui lòng thử lại.",
        "Something went wrong. Please try again.",
    ),
    "PENDING_REVIEW": (
        "Đang chờ chuyên viên dữ liệu xác nhận trước khi gửi kết quả.",
        "Waiting for a data analyst to confirm before the result is released.",
    ),
    "REVIEW_REJECTED": (
        "Chuyên viên dữ liệu đã từ chối kết quả này.",
        "A data analyst rejected this result.",
    ),
    "REVIEW_RETURNED": (
        "Chuyên viên dữ liệu cần bạn làm rõ câu hỏi.",
        "A data analyst needs you to clarify the question.",
    ),
}

REASON_LABELS: dict[str, tuple[str, str]] = {
    "JUDGE_FAIL": (
        "AI kiểm định đánh giá SQL có thể sai",
        "The AI judge flagged the SQL as likely wrong",
    ),
    "JUDGE_UNCERTAIN": ("AI kiểm định chưa chắc chắn", "The AI judge was not confident"),
    "LOW_CONFIDENCE": ("Độ tin cậy thấp", "Low confidence"),
    "FALLBACK_LOW_CONFIDENCE": (
        "Chế độ dự phòng chưa chắc về tham số",
        "Fallback mode is unsure about parameters",
    ),
    "PII_ACCESS": ("Truy vấn chạm tới dữ liệu cá nhân", "The query touches personal data"),
    "COST_GRAY": ("Truy vấn khá nặng", "The query is fairly expensive"),
    "USER_DOWNVOTE": ("Người dùng báo kết quả chưa đúng", "A user reported the result as wrong"),
}


def message(code: str, lang: str) -> str:
    vi, en = MESSAGES.get(code, MESSAGES["INTERNAL_ERROR"])
    return vi if lang == "vi" else en


def reason_label(code: str, lang: str) -> str:
    vi, en = REASON_LABELS.get(code, (code, code))
    return vi if lang == "vi" else en
