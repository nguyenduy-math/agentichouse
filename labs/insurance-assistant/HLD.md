# High-Level Design — Insurance Guide Virtual Assistant

A two-mode conversational insurance assistant for the Vietnamese market:

| Mode | `AssistantMode` | Agent | Outcome |
|---|---|---|---|
| **Claim filing** (khai thác bảo hiểm) | `claim_filing` | `agent.py` | Structured BHYT / commercial claim dossier (`ProposalCard`) |
| **Package recommendation** (tư vấn gói bảo hiểm) | `recommendation` | `advisor_agent.py` | 2–3 catalog-grounded package suggestions (`RecommendationCard`) |

Both modes share the same backbone — a per-turn **extract → merge → guide** loop driven by Gemini structured output, a 4-state session machine, and an in-memory session store. They diverge only in their data schema, prompts, and final-result generation.

---

## 1. System Architecture

```mermaid
graph TB
    subgraph Client["Client (Browser) — React SPA · port 5173 (dev)"]
        MS["ModeSelector\n(choose mode)"]
        Chat["ChatWindow\n+ OptionChips\n+ ProgressBar"]
        PC["ProposalCard\n(claim result)"]
        RC["RecommendationCard\n(recommendation result)"]
    end

    subgraph Backend["FastAPI Backend  ·  port 8002"]
        direction TB
        RSession["session router\nPOST /session/new {mode}\nDELETE /session/{id}"]
        RChat["chat router\nPOST /chat\n(dispatch by mode)"]
        RHealth["health router\nGET /health"]
        Store["SessionStore\n(in-memory, asyncio.Lock)\nTTL: 60 min"]

        ClaimAgent["agent.py\nClaim flow\nextract → guide → proposal"]
        AdvisorAgent["advisor_agent.py\nRecommendation flow\nextract → guide → recommend"]

        ClaimSchema["claim_schema.py\nREQUIRED_FIELDS · FIELD_META"]
        ProfileSchema["health_profile_schema.py\nREQUIRED_PROFILE_FIELDS · FIELD_CHIPS"]
        Catalog["catalog.py + packages_catalog.json\nfilter_by_profile() · format_for_prompt()"]
        Prompts["prompts.py\nsystem prompts + builders\n(both flows)"]

        RChat --> Store
        RChat -->|"mode=claim_filing"| ClaimAgent
        RChat -->|"mode=recommendation"| AdvisorAgent
        ClaimAgent --> ClaimSchema & Prompts
        AdvisorAgent --> ProfileSchema & Prompts & Catalog
    end

    subgraph Gemini["Google Gemini API · gemini-2.5-flash"]
        E["Extract call\nresponse_schema=<Extraction>\ntemp=0.0"]
        G["Guide call\nfree text · temp=0.3"]
        Rsum["Claim summary\nfree text · temp=0.2"]
        Rrec["Recommendation\nresponse_schema=RecommendationOutput\ntemp=0.2"]
    end

    MS -->|"POST /api/session/new {mode}"| RSession
    Chat -->|"POST /api/chat {session_id, message}"| RChat
    ClaimAgent -->|"_extract / _guide / _generate_summary"| E & G & Rsum
    AdvisorAgent -->|"_extract / _guide / _generate_recommendation"| E & G & Rrec
    RChat -.->|"ChatResponse"| Chat
    RChat -.->|"proposal"| PC
    RChat -.->|"recommendation"| RC
```

All routes are registered twice — bare (`/chat`) and under `/api` (`/api/chat`). The Vite dev proxy forwards `/api/*` to `localhost:8002`.

### LLM provider layer (`llm.py`)

Both agents call the model only through `app/llm.py`, which exposes one interface
(`generate_text` / `generate_structured`) implemented by two interchangeable
providers, selected by the `LLM_PROVIDER` setting:

| Provider | SDK | Structured output | Roles |
|---|---|---|---|
| **Gemini** (default) | `google-genai` | native `response_schema=<PydanticModel>` | `user` / `model` |
| **SiliconFlow** | `openai` (base_url `…siliconflow.cn/v1`) | `response_format=json_object` + JSON schema injected into the system prompt, tolerant parsing | `model`→`assistant`, separate `system` |

Agents pass the canonical message shape `{"role": "user"|"model", "content": str}`
(matching `session.history`); each provider adapts it to its SDK. One provider is
active per process (`get_provider()` singleton), and it raises a clear error if the
selected provider's API key is missing.

---

## 2. Per-Turn Data Flow (Sequence Diagram)

The chat router selects an agent by `session.mode`; both agents expose the same `process_turn()` signature, so the router code is symmetric.

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend<br/>(React)
    participant Chat as POST /chat<br/>(routers/chat.py)
    participant SS as SessionStore
    participant Ag as agent / advisor_agent<br/>process_turn()
    participant Gemini as Gemini API

    User->>FE: types message / clicks option chip
    FE->>Chat: POST /api/chat {session_id, message}

    Chat->>SS: get(session_id)
    SS-->>Chat: SessionState {mode, phase, history, collected/profile, ...}

    Chat->>Ag: process_turn(session, message)

    Note over Ag,Gemini: Call 1 — Extract (every non-terminal turn)
    Ag->>Gemini: generate_content(history[-4:] + message)<br/>response_schema=<Extraction>  temp=0.0
    Gemini-->>Ag: Extraction JSON (only mentioned fields)

    Ag->>Ag: _merge(state, extraction)<br/>+ _is_correction() check

    alt phase = collecting AND no missing fields
        Note over Ag: Advance to confirming
        Ag-->>Chat: (confirmation_text, merged, None, False, confirming, CONFIRM_CHIPS)
    else phase = confirming AND user confirms
        Note over Ag,Gemini: Call 2 — Result
        Ag->>Gemini: claim: summary (temp=0.2)<br/>recommend: catalog + response_schema=RecommendationOutput
        Gemini-->>Ag: summary text / recommendation JSON
        Ag-->>Chat: (reply, state, result, True, complete, None)
    else fields still missing
        Note over Ag,Gemini: Call 2 — Guide
        Ag->>Gemini: generate_content(history[-6:] + guide_prompt)<br/>temp=0.3
        Gemini-->>Ag: Vietnamese question
        Ag-->>Chat: (question, merged, None, False, collecting, field_chips?)
    end

    Chat->>SS: save(updated session)
    Chat-->>FE: ChatResponse {reply, collected, health_profile,<br/>proposal, recommendation, progress_pct, session_phase, options}
    FE-->>User: bubble + ProgressBar + chips + (Proposal/Recommendation)Card
```

---

## 3. Session State Machine (`SessionPhase`)

A single 4-state machine serves both modes. The only difference: claim filing starts in `identifying` (claim type unknown); recommendation skips straight to `collecting` (set in `session.py` at creation).

```mermaid
stateDiagram-v2
    [*] --> Created : POST /session/new {mode}

    Created --> identifying : mode=claim_filing
    Created --> collecting  : mode=recommendation

    identifying --> identifying : claim_type still unknown<br/>(re-ask with type chips)
    identifying --> collecting  : claim_type resolved

    collecting --> collecting : fields still missing<br/>(ask next -> correction-aware)
    collecting --> confirming : all required fields filled

    confirming --> complete   : user confirms → generate result
    confirming --> collecting  : user edits (treated as correction)
    confirming --> identifying : user restarts (claim flow)
    confirming --> collecting  : user restarts (recommendation flow)

    complete --> [*] : DELETE /session/{id} or TTL expiry (60 min)
    identifying --> [*] : TTL expiry
    collecting --> [*] : TTL expiry

    note right of confirming
        Summary shown with chips:
        [Confirm | Edit | Restart]
        Keyword-matched in agent
        (_user_confirms / _wants_restart)
    end note

    note right of complete
        Result cached on session
        (cached_proposal / recommendation).
        Further messages return cached
        result without new Gemini calls.
    end note
```

---

## 4. Mode Dispatch & Required Fields

```mermaid
flowchart TD
    START([POST /chat]) --> MODE{session.mode}

    MODE -- claim_filing --> CIDENT{claim_type\nknown?}
    CIDENT -- No --> CASK["Ask: ngoại trú / nội trú /\nthương mại + type chips"]
    CASK --> CIDENT
    CIDENT -- Yes --> CTYPE{claim_type}

    CTYPE -- outpatient --> COUT["name, dob, insurance_id, hospital,\nvisit_date, diagnosis, total_cost"]
    CTYPE -- inpatient --> CIN["name, dob, insurance_id, hospital,\nadmission_date, discharge_date,\ndiagnosis, total_cost, patient_paid"]
    CTYPE -- private --> CPRI["name, dob, policy_number, hospital,\nevent_date, diagnosis, total_cost,\nbank_account"]

    MODE -- recommendation --> PFIELDS["age, gender, occupation_type,\nsmoker, monthly_budget_vnd,\nnum_insured, coverage_priority\n(pre_existing_conditions optional)"]

    COUT & CIN & CPRI & PFIELDS --> LOOP{missing\nfields?}
    LOOP -- Yes --> GUIDE["Guide call → next question\n(+ field chips for profile fields)"]
    GUIDE --> EXTRACT["Extract call → merge"]
    EXTRACT --> LOOP
    LOOP -- No --> CONFIRM["confirming:\nshow summary + confirm chips"]
    CONFIRM -- confirm --> RESULT{mode}
    RESULT -- claim_filing --> PROPOSAL["Summary call →\n_build_proposal() dict"]
    RESULT -- recommendation --> RECO["catalog filter + Gemini →\nRecommendationOutput JSON"]
    PROPOSAL & RECO --> DONE([complete ✓])
```

---

## 5. Component Responsibilities

```mermaid
graph LR
    subgraph schemas["schemas.py — Data contracts"]
        AM["AssistantMode\nclaim_filing | recommendation"]
        SP["SessionPhase\nidentifying|collecting|confirming|complete"]
        CD["ClaimData / ClaimDataExtraction"]
        HP["HealthProfile / HealthProfileExtraction"]
        SST["SessionState\n(mode + history + collected + profile + caches)"]
        CR["ChatRequest / ChatResponse"]
    end

    subgraph claim_schema["claim_schema.py"]
        RF["REQUIRED_FIELDS[ClaimType]"]
        FM["FIELD_META (VN labels + hints)"]
        GMF["get_missing_fields() · compute_progress()"]
    end

    subgraph profile_schema["health_profile_schema.py"]
        RPF["REQUIRED_PROFILE_FIELDS"]
        PFM["PROFILE_FIELD_META"]
        FC["FIELD_CHIPS (gender/smoker/...)"]
        GMP["get_missing_profile_fields() · compute_profile_progress()"]
    end

    subgraph catalog["catalog.py + packages_catalog.json"]
        LC["load_catalog() (lru_cache)"]
        FBP["filter_by_profile()\nage/smoker/occupation eligibility\n+ priority & budget scoring → top-6"]
        FFP["format_for_prompt()\nshortlist → grounded prompt text"]
    end

    subgraph prompts["prompts.py"]
        ESsys["EXTRACTION / HEALTH_EXTRACTION system"]
        GSsys["GUIDE / ADVISOR_GUIDE system"]
        RSsys["PROPOSAL / RECOMMENDATION system"]
        BLD["build_guide / confirmation / proposal /\nrecommendation prompts"]
    end

    subgraph agents["agent.py + advisor_agent.py"]
        PT["process_turn() phase dispatcher"]
        EX["_extract → Extraction"]
        ME["_merge + _is_correction"]
        GU["_guide → question"]
        FIN["_generate_summary / _generate_recommendation"]
    end

    subgraph session["session_store.py"]
        SC["create / get / save / delete / purge_expired"]
    end

    agents --> schemas & prompts
    PT --> claim_schema & profile_schema
    FIN --> catalog
    PT --> session
```

---

## 6. Prompt Architecture

Each agent issues up to two Gemini calls per turn. Extraction is constrained JSON (`response_schema`); guidance is free text. The terminal call differs by mode.

```mermaid
graph TD
    subgraph "Call 1 — Extraction (temp=0.0, JSON)"
        E1["System: EXTRACTION_SYSTEM (claim)\nor HEALTH_EXTRACTION_SYSTEM (reco)\n— field/date/VNĐ normalization rules"]
        E2["Contents: history[-4] + user_message"]
        E3["response_schema = ClaimDataExtraction\nor HealthProfileExtraction"]
        E1 & E2 & E3 --> EC["Gemini → Extraction JSON\n(unmentioned fields = null)"]
    end

    subgraph "Call 2 — Guide (temp=0.3, free text)"
        G1["System: GUIDE_SYSTEM\nor ADVISOR_GUIDE_SYSTEM\n'Ask ONE question only'"]
        G2["Contents: history[-6]\n+ build_guide_prompt(collected, missing,\ncorrection_field)"]
        G1 & G2 --> GC["Gemini → Vietnamese question"]
    end

    subgraph "Call 2′ — Claim Summary (temp=0.2)"
        S1["System: PROPOSAL_SYSTEM"]
        S2["Contents: build_proposal_prompt(collected)"]
        S1 & S2 --> SC2["Gemini → Vietnamese summary paragraph"]
    end

    subgraph "Call 2″ — Recommendation (temp=0.2, JSON)"
        R1["System: RECOMMENDATION_SYSTEM\n'Only suggest packages in the list'"]
        R2["Contents: build_recommendation_prompt(\nprofile, catalog_text)"]
        R3["response_schema = RecommendationOutput"]
        R1 & R2 & R3 --> RC2["Gemini → 2–3 ranked packages JSON"]
    end
```

---

## 7. Catalog Grounding (Recommendation Flow)

The recommendation agent does **not** rely on the model's open-world knowledge of insurers. It grounds every suggestion in a local catalog (`packages_catalog.json`, 12 fictional packages across An Tín, Trường Phúc Life, Minh An Life, Việt Khang Life, Hồng Ân, …):

1. **Load** — `load_catalog()` reads + caches the JSON (`lru_cache`).
2. **Filter** — `filter_by_profile()` applies hard eligibility rules (age range, smoker exclusion, excluded occupations), then scores survivors by coverage-priority overlap (×10) and budget fit (+5/+2), returning the top 6.
3. **Format** — `format_for_prompt()` renders the shortlist (with the best budget-matching tier per package) into structured prompt text.
4. **Constrain** — `RECOMMENDATION_SYSTEM` forbids inventing packages/insurers/premiums outside the supplied list; `response_schema=RecommendationOutput` enforces the output shape.
5. **Fallback** — if the filter yields nothing, the first 6 catalog packages are passed instead (logged as a warning).

```
Catalog package schema (top-level keys)
├── insurer, name, product_line
├── coverage_types[]                 # nội trú / ngoại trú / tai nạn / ...
├── monthly_premium_tiers[]          # { plan, budget_max_vnd, sum_insured_vnd }
├── eligibility                      # { min_age, max_age, excludes_smoker, excluded_occupations[] }
├── key_benefits_vi[], exclusions_vi[]
└── description_vi
```

This keeps recommendations auditable and product-accurate while still letting Gemini handle ranking, suitability reasoning, and Vietnamese phrasing.

---

## 8. Key Design Notes

- **Stateless agents, stateful store.** Agents are pure functions of `(session, message)`; all persistence lives in `SessionStore` (in-memory dict guarded by `asyncio.Lock`, 60-min TTL). No database — this is a lab.
- **Correction handling.** `_is_correction()` compares pre/post-merge state; if a previously-set field changed, the guide prompt acknowledges the update before asking the next question, and "continue / edit more" chips are offered.
- **Result caching.** Once `complete`, the cached `proposal` / `recommendation` is returned on subsequent turns with no further Gemini calls.
- **Resilient extraction.** Extraction failures are caught and degrade to an empty patch, so a bad parse never breaks the turn — the agent simply re-asks.
- **Single source of truth for fields.** Required fields, Vietnamese labels, and option chips live in `claim_schema.py` / `health_profile_schema.py`; adding a field or claim type is a localized change (see README "Mở rộng").
