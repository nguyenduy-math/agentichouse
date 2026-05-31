"""Insurance Assistant MCP Server — exposes PDF scanning, image scanning,
and currency conversion tools."""

import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env from the mcp_server directory so VISION_PROVIDER and API keys are available
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from tools.pdf_tool import scan_pdf as _scan_pdf          # noqa: E402
from tools.image_tool import scan_image as _scan_image    # noqa: E402
from tools.currency_tool import convert_currency as _convert_currency  # noqa: E402

mcp = FastMCP("insurance-tools")


@mcp.tool()
def scan_pdf(file_path: str = "", base64_pdf: str = "") -> str:
    """
    Extract insurance claim fields from a PDF using a vision LLM.

    Provide either:
    - file_path: an absolute path to a local PDF file, OR
    - base64_pdf: the PDF content encoded as a base64 string.

    Returns a JSON string with keys:
    - "extracted_fields": structured claim data (name, dob, hospital, costs, etc.)
    - "summary_text": human-readable Vietnamese summary of what was found
    """
    return _scan_pdf(file_path=file_path, base64_pdf=base64_pdf)


@mcp.tool()
def scan_image(file_path: str = "", base64_image: str = "", mime_type: str = "") -> str:
    """
    Extract insurance claim fields from an image (JPG, PNG) using a vision LLM.

    Provide either:
    - file_path: an absolute path to a local image file, OR
    - base64_image + mime_type: the image content as base64 with its MIME type
      (e.g. "image/jpeg" or "image/png").

    Returns a JSON string with keys:
    - "extracted_fields": structured claim data
    - "summary_text": human-readable Vietnamese summary of what was found
    """
    return _scan_image(file_path=file_path, base64_image=base64_image, mime_type=mime_type)


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
