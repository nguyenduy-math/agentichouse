# Insurance Assistant MCP Server

A standalone Python MCP server built with LangChain + FastMCP. It exposes two tools for use with Claude Desktop or any MCP-compatible client.

The backend also imports `tools/pdf_tool.py` directly to serve the `POST /api/upload-pdf` endpoint — no running MCP server is required for that use case.

## Tools

### `scan_pdf`

Extracts text from a PDF file.

| Parameter | Type | Description |
|---|---|---|
| `file_path` | string | Absolute path to a local `.pdf` file |
| `base64_pdf` | string | Base64-encoded PDF content (alternative to `file_path`) |

Provide one or the other. Returns extracted text grouped by page.

**Example input:**
```json
{ "file_path": "/home/user/documents/claim.pdf" }
```

**Example output:**
```
Page 1:
Bệnh viện Bạch Mai
Ngày khám: 20/05/2025
Chẩn đoán: Viêm phổi cấp
Tổng chi phí: 3.200.000 VNĐ
...
```

### `convert_currency`

Converts an amount between currencies using live rates from [Frankfurter](https://api.frankfurter.app/currencies).

| Parameter | Type | Description |
|---|---|---|
| `amount` | float | Positive amount to convert |
| `from_currency` | string | Source ISO 4217 code (e.g. `"USD"`) |
| `to_currency` | string | Target ISO 4217 code (e.g. `"VND"`) |

**Example input:**
```json
{ "amount": 100, "from_currency": "USD", "to_currency": "VND" }
```

**Example output:**
```
100 USD = 2,534,200.00 VND
Rate: 25342.0 (as of 2025-05-30)
```

Supported currencies: all currencies available on Frankfurter.

---

## Setup

Requirements: Python 3.10+

```bash
cd mcp_server

python -m venv .venv
source .venv/bin/activate        # macOS/Linux
.venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

## Running the server

```bash
# From inside mcp_server/
python server.py
```

The server communicates over stdio (standard MCP transport).

---

## Register with Claude Desktop

Edit your `claude_desktop_config.json`:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "insurance-tools": {
      "command": "python",
      "args": [
        "C:/Users/<your-username>/Documents/dshouse/agentichouse/labs/insurance-assistant/mcp_server/server.py"
      ],
      "env": {}
    }
  }
}
```

If using a virtual environment, replace `"python"` with the full path to the venv interpreter:

```json
{
  "mcpServers": {
    "insurance-tools": {
      "command": "C:/Users/<your-username>/Documents/dshouse/agentichouse/labs/insurance-assistant/mcp_server/.venv/Scripts/python.exe",
      "args": [
        "C:/Users/<your-username>/Documents/dshouse/agentichouse/labs/insurance-assistant/mcp_server/server.py"
      ],
      "env": {}
    }
  }
}
```

Restart Claude Desktop after saving.

---

## Using from the Insurance Assistant backend

The backend imports `pdf_tool.py` directly — no MCP server process needed:

```python
from mcp_server.tools.pdf_tool import scan_pdf

text = scan_pdf(file_path="/tmp/uploaded_claim.pdf")
```

This is how `POST /api/upload-pdf` works: it calls `scan_pdf`, stores the extracted text in the session as `pdf_context`, and injects it into the agent prompt on every subsequent chat turn.
