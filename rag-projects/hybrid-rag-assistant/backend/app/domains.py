"""Single source of truth for domain definitions.

Adding a domain here automatically updates:
- the orchestrator classifier prompt
- the ingest API schema
- the agent registry in dependencies.py
"""

DOMAINS: dict[str, str] = {
    "hr": "Nhân sự và Lao động",
    "legal": "Pháp lý và Tuân thủ",
    "finance": "Tài chính và Kế toán",
    "general": "Thông tin chung",
}

DOMAIN_KEYS = list(DOMAINS.keys())
