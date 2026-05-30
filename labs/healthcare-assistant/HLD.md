# High-Level Design — Insurance Claim Guide Virtual Assistant

---

## 1. System Architecture

```mermaid
graph TB
    subgraph Client["Client (Browser)"]
        UI["React SPA\nport 5173 (dev)\n— ChatWindow\n— ProgressBar\n— ProposalCard"]
    end

    subgraph Backend["FastAPI Backend  ·  port 8002"]
        direction TB
        Router["Routers\n/chat  /session  /health"]
        Store["SessionStore\n(in-memory, asyncio.Lock)\nTTL: 60 min"]
        Agent["ClaimGuideAgent\nagent.py"]
        Prompts["prompts.py\nbuild_extraction_prompt()\nbuild_guide_prompt()\nbuild_proposal_prompt()"]
        Schema["claim_schema.py\nREQUIRED_FIELDS\nFIELD_META\nget_missing_fields()\ncompute_progress()"]

        Router --> Store
        Router --> Agent
        Agent --> Prompts
        Agent --> Schema
    end

    subgraph Gemini["Google Gemini API\ngemini-2.5-flash"]
        E["Extraction call\nresponse_schema=ClaimDataExtraction\ntemp=0.0"]
        G["Guide call\nfree text · temp=0.3"]
        S["Summary call\nfree text · temp=0.2"]
    end

    UI -->|"POST /api/chat\n{session_id, message}"| Router
    UI -->|"POST /api/session/new"| Router
    Agent -->|"_extract()"| E
    Agent -->|"_guide()"| G
    Agent -->|"_generate_summary()"| S
    E -.->|"ClaimDataExtraction JSON"| Agent
    G -.->|"Vietnamese question"| Agent
    S -.->|"Vietnamese summary"| Agent
```

---

## 2. Per-Turn Data Flow (Sequence Diagram)

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend<br/>(React)
    participant Chat as POST /chat<br/>(routers/chat.py)
    participant SS as SessionStore
    participant Ag as agent.process_turn()
    participant Gemini as Gemini API

    User->>FE: types message, presses Enter
    FE->>Chat: POST /api/chat {session_id, message}

    Chat->>SS: get(session_id)
    SS-->>Chat: SessionState {history, collected, ...}

    Chat->>Ag: process_turn(session, message)

    Note over Ag,Gemini: Call 1 — Extract
    Ag->>Gemini: generate_content(history[-4:] + message)<br/>system=EXTRACTION_SYSTEM<br/>response_schema=ClaimDataExtraction  temp=0.0
    Gemini-->>Ag: ClaimDataExtraction JSON<br/>{name, dob, hospital, ...}

    Ag->>Ag: _merge(collected, extraction)

    alt claim_type known AND no missing fields
        Note over Ag,Gemini: Call 2a — Proposal Summary
        Ag->>Gemini: generate_content(proposal_prompt)<br/>system=PROPOSAL_SYSTEM  temp=0.2
        Gemini-->>Ag: Vietnamese summary text
        Ag->>Ag: _build_proposal() → dict
        Ag-->>Chat: (summary, merged, proposal, is_complete=True)
    else fields still missing
        Note over Ag,Gemini: Call 2b — Guide
        Ag->>Gemini: generate_content(history[-6:] + guide_prompt)<br/>system=GUIDE_SYSTEM  temp=0.3
        Gemini-->>Ag: Vietnamese question string
        Ag-->>Chat: (question, merged, None, is_complete=False)
    end

    Chat->>SS: save(updated session)
    Chat-->>FE: ChatResponse {reply, collected, proposal, progress_pct, is_complete}
    FE-->>User: renders bubble + ProgressBar + ProposalCard (if complete)
```

---

## 3. Session State Machine

```mermaid
stateDiagram-v2
    [*] --> Created : POST /session/new

    Created --> Collecting : first message<br/>(claim_type = unknown)

    Collecting --> Collecting : message received<br/>fields still missing

    Collecting --> Complete : all required fields filled<br/>is_complete = true

    Complete --> [*] : DELETE /session/{id}<br/>or TTL expiry (60 min)
    Collecting --> [*] : TTL expiry (60 min)
    Created --> [*] : TTL expiry (60 min)

    note right of Collecting
        Each turn:
        1. Extract fields from message
        2. Merge into ClaimData
        3. Check missing fields
        4. Ask next question
    end note

    note right of Complete
        proposal dict populated
        Vietnamese summary generated
        Frontend shows ProposalCard
    end note
```

---

## 4. Claim Type Decision & Required Fields

```mermaid
flowchart TD
    START([User first message]) --> UNKNOWN{claim_type\nknown?}

    UNKNOWN -- No --> ASK_TYPE[Ask: ngoại trú / nội trú\n/ bảo hiểm thương mại?]
    ASK_TYPE --> UNKNOWN

    UNKNOWN -- Yes --> BRANCH{claim_type}

    BRANCH -- outpatient --> OUT["Required fields:\n• Họ và tên\n• Ngày sinh\n• Mã số BHXH\n• Cơ sở KCB\n• Ngày khám\n• Chẩn đoán\n• Tổng chi phí"]

    BRANCH -- inpatient --> IN["Required fields:\n• Họ và tên\n• Ngày sinh\n• Mã số BHXH\n• Cơ sở KCB\n• Ngày nhập viện\n• Ngày xuất viện\n• Chẩn đoán\n• Tổng chi phí\n• Tiền tự trả"]

    BRANCH -- private --> PRI["Required fields:\n• Họ và tên\n• Ngày sinh\n• Số hợp đồng BH\n• Cơ sở KCB\n• Ngày sự kiện\n• Chẩn đoán\n• Tổng chi phí\n• Số tài khoản NH"]

    OUT & IN & PRI --> LOOP{missing\nfields?}

    LOOP -- Yes --> GUIDE["Guide call:\nAsk next question\n(most logical missing field)"]
    GUIDE --> EXTRACT["Extract call:\nParse user answer\nMerge into ClaimData"]
    EXTRACT --> LOOP

    LOOP -- No --> PROPOSAL["Summary call:\nGenerate Vietnamese summary\n+ build proposal JSON"]
    PROPOSAL --> DONE([Session complete ✓])
```

---

## 5. Component Responsibilities

```mermaid
graph LR
    subgraph schemas["schemas.py — Data contracts"]
        CD["ClaimData\n(all fields Optional)"]
        CDE["ClaimDataExtraction\n(Gemini response_schema)"]
        SS2["SessionState\n(history + collected + flags)"]
        CR["ChatRequest / ChatResponse"]
    end

    subgraph claim_schema["claim_schema.py — Business rules"]
        RF["REQUIRED_FIELDS\nper ClaimType"]
        FM["FIELD_META\nVietnamese labels + hints"]
        GMF["get_missing_fields()"]
        CP["compute_progress() → int %"]
    end

    subgraph prompts["prompts.py — Prompt engineering"]
        ES["EXTRACTION_SYSTEM\nJSON-only extractor persona"]
        GS["GUIDE_SYSTEM\nAdvisor persona + rules"]
        PS["PROPOSAL_SYSTEM\nSummary writer persona"]
        BGP["build_guide_prompt()\ncollected + missing → context string"]
        BPP["build_proposal_prompt()\ncollected → summary request"]
    end

    subgraph agent["agent.py — Orchestration"]
        PT["process_turn()"]
        EX["_extract() → ClaimDataExtraction"]
        ME["_merge() → ClaimData"]
        GU["_guide() → str"]
        GS2["_generate_summary() → str"]
        BP["_build_proposal() → dict"]
    end

    subgraph session["session_store.py — State"]
        SC["create() → SessionState"]
        SG["get(id) → SessionState"]
        SV["save(session)"]
        SD["delete(id)"]
        PE["purge_expired()"]
    end

    PT --> EX & ME & GU & GS2 & BP
    EX --> ES
    GU --> GS & BGP & FM
    GS2 --> PS & BPP
    BP --> FM & RF
    PT --> GMF & CP
    claim_schema --> RF & FM & GMF & CP
```

---

## 6. Prompt Architecture

```mermaid
graph TD
    subgraph "Call 1 — Extraction  (temp=0.0)"
        ES2["System: EXTRACTION_SYSTEM\n(JSON extractor, field rules,\nVNĐ + date normalization)"]
        EC["Contents:\nhistory[-4 turns] + user_message"]
        SCHEMA["response_schema=ClaimDataExtraction\nresponse_mime_type=application/json"]
        ES2 & EC & SCHEMA --> GC1["Gemini\ngenerate_content()"]
        GC1 --> OUT1["ClaimDataExtraction JSON\n{name, dob, hospital, ...  null for unmentioned}"]
    end

    subgraph "Call 2a — Guide  (temp=0.3)"
        GS3["System: GUIDE_SYSTEM\nAdvisor persona\n'Ask ONE question only'"]
        GC2["Contents:\nhistory[-6 turns]\n+ build_guide_prompt(collected, missing)"]
        GS3 & GC2 --> GC3["Gemini\ngenerate_content()"]
        GC3 --> OUT2["Vietnamese question string"]
    end

    subgraph "Call 2b — Summary  (temp=0.2)"
        PS2["System: PROPOSAL_SYSTEM\nProfessional summary writer"]
        PC["Contents:\nbuild_proposal_prompt(collected)"]
        PS2 & PC --> GC4["Gemini\ngenerate_content()"]
        GC4 --> OUT3["Vietnamese summary paragraph"]
    end
```
