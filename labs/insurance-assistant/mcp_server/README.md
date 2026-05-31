# Insurance Assistant MCP Server

Exposes three tools via the Model Context Protocol (MCP):

| Tool | Description |
|------|-------------|
| `scan_pdf` | Extract claim fields from a PDF using a vision LLM |
| `scan_image` | Extract claim fields from a JPG/PNG using a vision LLM |
| `convert_currency` | Convert amounts between currencies using live rates |

The backend also imports `tools/pdf_tool.py` and `tools/image_tool.py` directly to serve the `POST /api/upload-document` endpoint — no running MCP server is required for that use case.

---

## Setup

```bash
cd mcp_server
pip install -r requirements.txt
cp .env.example .env   # then fill in your API key(s)
python server.py
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

### `VISION_PROVIDER`

Controls which vision LLM is used for document extraction.

| Value | Provider | Model |
|-------|----------|-------|
| `gemini` *(default)* | Google Gemini | `gemini-2.0-flash` |
| `siliconflow` | Siliconflow | `Qwen/Qwen2-VL-72B-Instruct` |

```env
VISION_PROVIDER=gemini        # or: siliconflow
```

### `GOOGLE_API_KEY`

Required when `VISION_PROVIDER=gemini`.  
Get a key at <https://aistudio.google.com/app/apikey>.

```env
GOOGLE_API_KEY=your_google_api_key_here
```

### `SILICONFLOW_API_KEY`

Required when `VISION_PROVIDER=siliconflow`.  
Get a key at <https://siliconflow.cn>.

```env
SILICONFLOW_API_KEY=your_siliconflow_api_key_here
```

---

## Tool Reference

### `scan_pdf`

Converts the first 1–2 pages of a PDF to images and sends them to the vision LLM.

**Parameters** (provide one):
- `file_path` — absolute path to a local PDF file
- `base64_pdf` — PDF content encoded as a base64 string

**Returns:** JSON string
```json
{
  "extracted_fields": {
    "claim_type": "outpatient",
    "name": "Nguyễn Văn A",
    "dob": "15/03/1990",
    "hospital": "Bệnh viện Bạch Mai",
    "...": "..."
  },
  "summary_text": "Tôi đã đọc tài liệu và tìm thấy các thông tin sau:\n..."
}
```

On error:
```json
{ "error": "description of what went wrong" }
```

---

### `scan_image`

Sends a JPG or PNG directly to the vision LLM.

**Parameters** (provide one):
- `file_path` — absolute path to a local image file (JPG/PNG/WebP)
- `base64_image` + `mime_type` — image as base64 with its MIME type (e.g. `"image/jpeg"`)

**Returns:** Same JSON shape as `scan_pdf`.

---

### `convert_currency`

Converts an amount between currencies using live exchange rates.

**Parameters:**
- `amount` — positive number
- `from_currency` — ISO code (e.g. `"VND"`)
- `to_currency` — ISO code (e.g. `"USD"`)

---

## Architecture

```
mcp_server/
├── server.py                  # FastMCP server — registers all tools
├── .env.example               # template for environment variables
├── requirements.txt
└── tools/
    ├── vision_provider.py     # VisionProvider base + Gemini/Siliconflow impls
    ├── pdf_tool.py            # PDF → page images → vision LLM → JSON
    ├── image_tool.py          # image file → vision LLM → JSON
    └── currency_tool.py       # live FX conversion (unchanged)
```

The `VisionProvider` abstraction in `vision_provider.py` makes it easy to add new providers: implement `extract_claim_fields(image_bytes: bytes, mime_type: str) -> dict` and register in the `_PROVIDERS` dict.
