"""Insurance Assistant MCP Server — exposes PDF scanning and currency conversion tools."""

from mcp.server.fastmcp import FastMCP

from tools.pdf_tool import scan_pdf as _scan_pdf
from tools.currency_tool import convert_currency as _convert_currency

mcp = FastMCP("insurance-tools")


@mcp.tool()
def scan_pdf(file_path: str = "", base64_pdf: str = "") -> str:
    """
    Extract text content from a PDF file.

    Provide either:
    - file_path: an absolute path to a local PDF file, OR
    - base64_pdf: the PDF content encoded as a base64 string.

    Returns the extracted text, page by page.
    """
    return _scan_pdf(file_path=file_path, base64_pdf=base64_pdf)


@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """
    Convert an amount between two currencies using live exchange rates.

    Args:
        amount: Positive number to convert.
        from_currency: Source currency ISO code (e.g. "USD", "VND", "EUR").
        to_currency: Target currency ISO code (e.g. "EUR", "JPY", "GBP").

    Returns a formatted string with the converted amount and exchange rate.
    """
    return _convert_currency(amount=amount, from_currency=from_currency, to_currency=to_currency)


if __name__ == "__main__":
    mcp.run()
