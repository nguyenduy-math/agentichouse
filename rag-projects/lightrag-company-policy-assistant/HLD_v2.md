# Company Policy Virtual Assistant — High-Level Design

## System Overview

A multi-agent AI assistant that answers employee questions about company policies. Each question is automatically routed to the most relevant domain specialist(s); answers are grounded in uploaded policy documents and include source citations.

---

## Architecture

```mermaid
flowchart TD
    subgraph Client["Client"]
        UI["Web Application"]
    end

    subgraph Platform["AI Platform"]
        API["REST API"]

        subgraph Intelligence["Intelligence Layer"]
            ORC["Orchestrator\n─────────────────\nClassifies question → domain(s)\nRoutes to specialist(s)\nSynthesizes cross-domain answers"]

            subgraph Agents["Domain Specialists (10 agents)"]
                KG["Knowledge-Graph Agents (×9)\n─────────────────────────────\nHR Policy · Conduct · Procedures\nHandbook · Medical · IT & Security\nCompliance · Finance · Training"]
                TR["Tree-Navigation Agent (×1)\n─────────────────────────────\nBenefits & Compensation"]
            end
        end

        subgraph Ingestion["Document Ingestion"]
            ING["Upload & Index Pipeline\nSupports PDF · DOCX · TXT · MD"]
        end
    end

    subgraph AI["AI Services"]
        LLM["Large Language Model\n(Google Gemini)"]
        EMB["Embedding Model\n(Google Gemini)"]
    end

    subgraph Storage["Data Storage"]
        GRAPH[("Knowledge Graph\nEntities · Relations")]
        VECTOR[("Vector + KV Store\nChunks · Index files")]
        TREE[("Document Trees\nHierarchical JSON")]
        DOCS[("Source Documents\nPDF / DOCX / TXT")]
    end

    %% Flows
    UI -->|"chat / upload"| API
    API --> ORC
    API --> ING

    ORC -->|"route"| KG & TR
    KG & TR -->|"generate answer"| LLM
    KG -->|"retrieve"| GRAPH & VECTOR
    TR -->|"navigate tree"| TREE
    ING -->|"store source"| DOCS
    ING -->|"build index"| GRAPH & VECTOR & TREE
    EMB -->|"encode chunks"| VECTOR
    ORC -->|"classify"| LLM
```

---

## Domain Coverage

| Domain | Specialist | Typical Questions |
|--------|-----------|------------------|
| HR Policy | HR Policy Agent | Leave entitlements, working hours, disciplinary procedures |
| Benefits | Benefits Agent | Salary bands, insurance coverage, allowance amounts |
| Conduct | Conduct Agent | Prohibited behaviors, conflict of interest, discipline |
| Procedures | Procedures Agent | Approval workflows, step-by-step processes |
| Handbook | Handbook Agent | Company culture, mission, onboarding overview |
| Medical | Medical Agent | Health insurance, hospital network, reimbursement |
| IT & Security | IT Security Agent | Access control, acceptable use, incident reporting |
| Compliance | Compliance Agent | Legal obligations, regulatory requirements, penalties |
| Finance | Finance Agent | Expense limits, reimbursement process, approvers |
| Training | Training Agent | Learning programs, eligibility, career development |

---

## Request Flow (Single / Multi-Domain Routing)

```mermaid
flowchart TD
    Q(["Employee"])
    API["POST /chat\nREST API"]
    Classify["Domain Classification\nGemini LLM"]

    subgraph NONE["No domain matched"]
        Greeting["Greeting / Out-of-scope reply\nNo agent invoked"]
    end

    subgraph SINGLE["Single domain"]
        AgentOne["Domain Specialist\nKG agent or Tree-Navigation agent"]
        AnswerOne["Generate grounded answer\nGemini LLM + citations"]
    end

    subgraph MULTI["Multiple domains"]
        Fanout["Fan-out to N specialists"]
        AgentsN["Parallel domain answers\n(per-domain retrieval + LLM)"]
        Synth["Synthesize merged answer\nGemini LLM"]
    end

    Response(["ChatResponse\nanswer · domain labels · citations"])

    Q --> API --> Classify
    Classify -- "no match" --> Greeting
    Classify -- "1 domain" --> AgentOne --> AnswerOne
    Classify -- "N domains" --> Fanout --> AgentsN --> Synth
    Greeting & AnswerOne & Synth --> Response
```

---

## Document Ingestion Flow

```mermaid
sequenceDiagram
    actor Admin
    participant Web as Web App
    participant API as REST API
    participant Agent as Domain Agent
    participant Store as Storage

    Admin->>Web: Upload document (select domain)
    Web->>API: POST /ingest/upload
    API->>Agent: index_document(file)
    Agent->>Store: Save source file
    Agent->>Store: Build & persist index
    Store-->>Agent: Index ready
    Agent-->>API: Done
    API-->>Web: Ingestion summary
```

---

## Answer Quality Guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| Domain accuracy | LLM-based classifier with structured output — only valid domain keys returned |
| Grounded answers | Each agent's prompt enforces citation-only responses; unsupported claims are forbidden |
| Citation traceability | Every answer includes document name, page number, and section reference |
| Language consistency | Response language is centrally configured; all agents share the same language contract |
| Context overflow prevention | Token-aware content trimming applied before every LLM call |
| Schema correctness | Structured output schemas enforce valid response shapes at the API boundary |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM & Embeddings | Google Gemini 2.5 Flash + Gemini Embedding |
| Knowledge-Graph RAG | LightRAG (graph + vector hybrid) |
| Tree-Navigation RAG | PageIndex Cloud (vectorless, hierarchical) |
| Graph Database | Neo4j 5 |
| API | FastAPI + Uvicorn |
| Frontend | React 18 + Vite |
