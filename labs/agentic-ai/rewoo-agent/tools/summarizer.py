import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import llm_client

_SYSTEM = (
    "Bạn là một nhà báo công nghệ. Dựa trên kết quả tìm kiếm tin tức, hãy xác định "
    "3 câu chuyện AI nổi bật nhất. Với mỗi câu chuyện, trả về: Tiêu đề, "
    "Tóm tắt một câu. Định dạng dưới dạng danh sách đánh số."
)


def summarize_top3(results1: str, results2: str) -> str:
    """Identify the 3 most significant AI stories from combined search results."""
    combined = f"=== Source 1 ===\n{results1}\n\n=== Source 2 ===\n{results2}"
    return llm_client.chat_completion(system=_SYSTEM, user=combined, max_tokens=512)
