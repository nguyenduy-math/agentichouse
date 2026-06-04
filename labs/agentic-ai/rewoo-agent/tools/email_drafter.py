import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import llm_client

_SYSTEM_TEMPLATE = (
    "Bạn là một trợ lý chuyên nghiệp. Soạn một email tóm tắt tin tức cho nhóm bằng "
    "tiếng {language} dựa trên các câu chuyện AI này. Bao gồm: Dòng tiêu đề, "
    "Lời chào, 3 gạch đầu dòng (mỗi câu chuyện một gạch), Lời kết chuyên nghiệp. "
    "Ngắn gọn và cuốn hút."
)


def draft_email(briefing: str, language: str = "Vietnamese") -> str:
    """Draft a professional team email in the specified language."""
    return llm_client.chat_completion(
        system=_SYSTEM_TEMPLATE.format(language=language),
        user=briefing,
        max_tokens=1024,
    )
