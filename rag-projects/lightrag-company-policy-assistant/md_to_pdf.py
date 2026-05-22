"""Convert a Markdown file to PDF (Unicode-friendly, handles Vietnamese + tables)."""
import sys
from pathlib import Path

from markdown_pdf import MarkdownPdf, Section


def convert(md_path: str, pdf_path: str | None = None) -> str:
    md_file = Path(md_path)
    text = md_file.read_text(encoding="utf-8")
    out = Path(pdf_path) if pdf_path else md_file.with_suffix(".pdf")

    pdf = MarkdownPdf(toc_level=2, optimize=True)
    # 'tables' enables Markdown table rendering; the default fonts cover Vietnamese.
    pdf.add_section(Section(text), user_css="body { font-family: sans-serif; }")
    pdf.meta["title"] = md_file.stem
    pdf.save(str(out))
    return str(out)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "chinh_sach_phuc_loi.md"
    dst = sys.argv[2] if len(sys.argv) > 2 else None
    print("Saved:", convert(src, dst))
