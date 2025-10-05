# Azure RAG Agent Architecture Diagrams

This document contains comprehensive architecture diagrams for the Azure RAG Agent system, including system architecture, query processing flows, multi-tenant design, and operational patterns.

## System Architecture

The overall system architecture showing all components and their relationships:

```mermaid
flowchart TB
  subgraph Edge["Edge & API Layer"]
    FD["Front Door<br/>(TLS, Global CDN, WAF)"]
    APIM["API Management<br/>(OAuth2/JWT, Quotas, Schema Validation)"]
  end

  subgraph Orchestrator["Agent Orchestration API<br/>(Container Apps in VNet)"]
    APIH["FastAPI Handler"]
    ROUTER["Tenant Router<br/>(Managed Identity + RBAC)"]
    CTX["Context Manager"]
    CACHE["Azure Cache for Redis<br/>(Response, Session, Tool, Semantic)"]
  end

  subgraph Engine["ADK Agent Engine"]
    PLAN["Planner<br/>(LlmAgent • GPT-4o)"]
    WF["WorkflowAgent<br/>(parallel/sequential/conditional)"]
    CB["Budget + Circuit Breaker<br/>(CustomAgent)"]
    REF["Reflection<br/>(LlmAgent • GPT-4o-mini)"]
    SYN["Synthesis<br/>(LlmAgent • GPT-4o)"]
  end

  subgraph Retrieval["Retrieval Services<br/>(Private Link Only)"]
    AIS["Azure AI Search<br/>(Vector + BM25 + Filters, Rerank)"]
    COS["Cosmos DB Gremlin<br/>(Graph Relationships)"]
    SQL["Synapse Serverless SQL<br/>(Analytics)"]
  end

  subgraph Models["Model Inference"]
    AML["Azure ML Online Endpoint<br/>(Per-tenant Fine-tunes)"]
    AOAI["Azure OpenAI<br/>(GPT-4o, GPT-4o-mini, Embeddings)"]
    MR["Model Router<br/>(FT vs Foundation)"]
  end

  subgraph Safety["Safety & Governance"]
    ACS["Azure AI Content Safety<br/>(Toxicity, PII Detection)"]
    PUR["Microsoft Purview<br/>(Data Classification Policies)"]
    KV["Key Vault<br/>(Secrets, Certificates)"]
  end

  subgraph Obs["Observability & Cost"]
    AI["App Insights<br/>(Distributed Tracing)"]
    MON["Azure Monitor<br/>(Metrics, Alerts)"]
    LA["Log Analytics<br/>(KQL Queries)"]
  end

  FD --> APIM --> APIH --> ROUTER --> CTX
  CTX <--> CACHE
  APIH --> PLAN --> WF --> CB
  CB -- "Circuit Closed<br/>Budget OK" --> Retrieval
  WF -- "vector search" --> AIS
  WF -- "graph query" --> COS
  WF -- "sql analytics" --> SQL
  AIS --> WF
  COS --> WF
  SQL --> WF
  WF --> REF --> PLAN
  WF --> SYN --> MR
  MR --> AML
  MR --> AOAI
  SYN --> ACS --> APIH
  PUR -. "Data policies" .- Retrieval
  KV -. "Secrets" .- Orchestrator
  APIH -. "Traces" .-> AI
  WF -. "Metrics" .-> MON
  Engine -. "Logs" .-> LA

  classDef edge fill:#E1F5FF,stroke:#0277BD,stroke-width:2px
  classDef orchestrator fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px
  classDef engine fill:#FFF9C4,stroke:#F57F17,stroke-width:2px
  classDef retrieval fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px
  classDef models fill:#FCE4EC,stroke:#C2185B,stroke-width:2px
  classDef safety fill:#FFF3E0,stroke:#EF6C00,stroke-width:2px
  classDef obs fill:#E0F2F1,stroke:#00695C,stroke-width:2px

  class FD,APIM edge
  class APIH,ROUTER,CTX,CACHE orchestrator
  class PLAN,WF,CB,REF,SYN engine
  class AIS,COS,SQL retrieval
  class AML,AOAI,MR models
  class ACS,PUR,KV safety
  class AI,MON,LA obs
```

## Query Processing Flow

Detailed flow of how queries are processed through the system:

```mermaid
flowchart TB
  subgraph Ingest["Query Ingestion & Classification"]
    Q(("User Query<br/>+ Session<br/>+ Tenant ID"))
    NORM["Query Normalizer<br/>(Lowercase, Trim, Entity Extract)"]
    CLS["Classifier Agent<br/>(GPT-4o-mini)<br/>→ intent/complexity/domain"]
    BUD["Budget Allocator<br/>(Simple: $0.001, Medium: $0.005, Complex: $0.01)"]
  end

  subgraph Plan["Strategy Planning"]
    PL["Planner Agent<br/>(GPT-4o)<br/>→ Execution DAG within budget"]
    CB["Circuit Breaker Check<br/>(Redis Cache)"]
  end

  subgraph Decide["Decision Heuristics<br/>(Rule Engine First)"]
    RULES["Keyword/Entity Rules<br/>→ Tool Hints<br/><br/>• 'trend|graph' → SQL<br/>• 'related|connected' → Graph<br/>• 'who|what|when' → Vector<br/>• 'why|how' → Multi-source"]
  end

  subgraph Tools["Tool Execution Paths"]
    VS["Azure AI Search<br/>(Vector + BM25, Rerank)<br/>Timeout: 500ms<br/>Cost: ~$0.0001"]
    GR["Cosmos Gremlin<br/>(Max depth 3, Hot cache)<br/>Timeout: 1s<br/>Cost: ~$0.0002"]
    SQ["Synapse SQL<br/>(Serverless, LIMIT 1000)<br/>Timeout: 2s<br/>Cost: ~$0.0005"]
    WS["Bing Web Search<br/>(Domain allowlist)<br/>Timeout: 2s<br/>Cost: ~$0.005"]
  end

  subgraph Exec["Execution Loop<br/>(WorkflowAgent)"]
    WF["Execute Tools<br/>(parallel or sequential)"]
    TO["Timeout Monitor<br/>(Total: 5s max)"]
    MR["Results Merger<br/>(Dedupe, Rank, Provenance)"]
    QG["Quality Gate<br/>(≥3 results, conf≥0.7, ≥2 sources)"]
    RF["Reflection Agent<br/>(GPT-4o-mini)<br/>→ Gaps analysis<br/>→ Replan? (≤3 iterations)"]
  end

  subgraph Synth["Synthesis & Safety"]
    CTX["Context Builder<br/>(Token budget, High-conf priority)"]
    SYN["Synthesis Agent<br/>(GPT-4o)<br/>+ Citations"]
    SAF["Content Safety<br/>(Toxicity, PII)<br/>+ Custom Rules"]
  end

  subgraph Out["Response Delivery"]
    FMT["Response Formatter<br/>(JSON/Markdown/HTML)"]
    COST["Cost Meter<br/>(Track per-tenant)"]
    TRACE["Telemetry<br/>(App Insights + KQL)"]
    RESP(("Final Response<br/>+ Citations<br/>+ Cost<br/>+ Trace ID"))
  end

  Q --> NORM --> CLS --> BUD --> PL --> CB --> RULES --> WF
  WF -->|"vector"| VS --> MR
  WF -->|"graph"| GR --> MR
  WF -->|"sql"| SQ --> MR
  WF -->|"web"| WS --> MR
  WF --> TO
  MR --> QG
  QG -->|"Pass"| CTX --> SYN --> SAF --> FMT
  QG -->|"Fail"| RF --> PL
  FMT --> COST --> TRACE --> RESP

  classDef io fill:#F4EBFF,stroke:#7E57C2,stroke-width:2px
  classDef llm fill:#FFF6D5,stroke:#B58900,stroke-width:2px
  classDef tool fill:#E8F5E9,stroke:#2E7D32,stroke-width:1px
  classDef decision fill:#FFF3E0,stroke:#EF6C00,stroke-dasharray:3 3,stroke-width:2px

  class Q,RESP io
  class CLS,PL,RF,SYN llm
  class NORM,BUD,CB,RULES,VS,GR,SQ,WS,WF,TO,MR,QG,CTX,SAF,FMT,COST,TRACE tool
```

## Multi-Tenant Architecture

How the system handles multiple tenants with proper isolation:

```mermaid
flowchart LR
  subgraph Tenants["Multi-Tenant Requests"]
    T1["Tenant A"]
    T2["Tenant B"]
    T3["Tenant C"]
  end

  subgraph Edge["Front Door + APIM"]
    FD["Front Door<br/>(Global)"]
    APIM["APIM<br/>(JWT Extract tenant_id)"]
  end

  subgraph Isolation["Tenant Isolation Layer"]
    ROUTER["Tenant Router<br/>(x-tenant-id header)"]
  end

  subgraph DataA["Tenant A Resources"]
    SA["AI Search Index:<br/>tenantA-kb"]
    CA["Cosmos Collection:<br/>tenantA-graph"]
    AML_A["AML Endpoint:<br/>tenantA-ft-model"]
  end

  subgraph DataB["Tenant B Resources"]
    SB["AI Search Index:<br/>tenantB-kb"]
    CB["Cosmos Collection:<br/>tenantB-graph"]
    AML_B["AML Endpoint:<br/>tenantB-ft-model"]
  end

  subgraph Shared["Shared Services"]
    AOAI["Azure OpenAI<br/>(Foundation Models)"]
    REDIS["Redis Cache<br/>(Session by tenant_id)"]
  end

  T1 & T2 & T3 --> FD --> APIM --> ROUTER
  ROUTER -->|"tenant_id=A"| DataA
  ROUTER -->|"tenant_id=B"| DataB
  ROUTER --> Shared
  DataA --> AML_A --> AOAI
  DataB --> AML_B --> AOAI

  classDef tenant fill:#E3F2FD,stroke:#1976D2,stroke-width:2px
  classDef edge fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px
  classDef shared fill:#FFF9C4,stroke:#F57F17,stroke-width:2px

  class T1,T2,T3 tenant
  class FD,APIM,ROUTER edge
  class AOAI,REDIS shared
```

## Circuit Breaker State Machine

The circuit breaker pattern implementation for fault tolerance:

```mermaid
stateDiagram-v2
    [*] --> Closed: Initial State
    
    Closed --> Open: Failure Rate > 50%
    Closed --> Closed: Success (Decrease failure rate)
    
    Open --> HalfOpen: Timeout (30s elapsed)
    Open --> Open: Request Rejected
    
    HalfOpen --> Closed: Success (Reset counters)
    HalfOpen --> Open: Failure
    
    note right of Closed
        Normal operation
        Track failure rate via EMA
        Allow all requests
    end note
    
    note right of Open
        Block all requests
        Return circuit_open status
        Wait for timeout
    end note
    
    note right of HalfOpen
        Test with single request
        Gradual recovery
        Decide: Close or re-Open
    end note
```

## Data Flow - Hybrid Search

Sequence diagram showing the hybrid search process:

```mermaid
sequenceDiagram
    participant User
    participant APIM
    participant Agent
    participant OpenAI
    participant Search
    participant Cache

    User->>APIM: Query Request
    APIM->>APIM: Validate JWT<br/>Extract tenant_id
    APIM->>Agent: Forward + x-tenant-id
    
    Agent->>Cache: Check response cache<br/>(hash of query)
    alt Cache Hit
        Cache-->>Agent: Return cached response
        Agent-->>User: Response (50ms)
    else Cache Miss
        Agent->>OpenAI: Generate embedding<br/>(text-embedding-ada-002)
        OpenAI-->>Agent: Vector [1536]
        
        Agent->>Search: Hybrid Search<br/>(Vector ANN + BM25)
        Note over Search: Filter: tenant_id=X<br/>k-NN: k=50<br/>BM25: query text
        Search-->>Agent: Top 20 results<br/>with scores
        
        Agent->>Agent: Dedupe + Rank<br/>by relevance
        Agent->>Cache: Store in tool cache<br/>(TTL: 30min)
        Agent-->>User: Response (500ms)
    end
```

## Cost Tracking Flow

How costs are tracked and budgeted throughout the system:

```mermaid
flowchart TB
    START([Query Received])
    
    START --> CLASSIFY[Classify Query<br/>Cost: $0.0001]
    CLASSIFY --> PLAN[Plan Strategy<br/>Cost: $0.0002]
    
    PLAN --> BUDGET{Budget<br/>Sufficient?}
    BUDGET -->|No| ABORT[Return Partial<br/>+ Budget Error]
    BUDGET -->|Yes| EXEC[Execute Tools]
    
    EXEC --> TOOL1[Vector Search<br/>Cost: $0.0001]
    EXEC --> TOOL2[Graph Query<br/>Cost: $0.0002]
    EXEC --> TOOL3[SQL Query<br/>Cost: $0.0005]
    
    TOOL1 & TOOL2 & TOOL3 --> METER[Cost Meter<br/>Accumulate]
    
    METER --> CHECK{Total Cost<br/>< Limit?}
    CHECK -->|No| ABORT
    CHECK -->|Yes| SYNTH[Synthesize Response<br/>Cost: $0.002]
    
    SYNTH --> LOG[Log to Analytics<br/>tenant_id + cost breakdown]
    LOG --> RETURN([Return Response<br/>+ Total Cost])
    
    ABORT --> RETURN
    
    classDef cost fill:#FFE082,stroke:#F57C00,stroke-width:2px
    class CLASSIFY,PLAN,TOOL1,TOOL2,TOOL3,SYNTH,METER cost
```

## Network Architecture

The network topology and security boundaries:

```mermaid
graph TB
    subgraph Internet["Internet"]
        USER["Users"]
    end
    
    subgraph FrontDoor["Front Door (Global)"]
        FD["Premium Front Door<br/>WAF + DDoS"]
    end
    
    subgraph VNet["VNet (10.0.0.0/16)"]
        subgraph APIM_Subnet["APIM Subnet (10.0.3.0/24)"]
            APIM["API Management<br/>(Internal Mode)"]
        end
        
        subgraph CA_Subnet["Container Apps Subnet (10.0.0.0/23)"]
            CA["Container Apps<br/>(FastAPI + ADK)"]
        end
        
        subgraph PE_Subnet["Private Endpoints (10.0.2.0/24)"]
            PE_OPENAI["PE: OpenAI"]
            PE_SEARCH["PE: AI Search"]
            PE_COSMOS["PE: Cosmos DB"]
            PE_REDIS["PE: Redis"]
            PE_KV["PE: Key Vault"]
        end
    end
    
    subgraph Azure_Services["Azure PaaS Services<br/>(Public Network Disabled)"]
        OPENAI["Azure OpenAI"]
        SEARCH["AI Search"]
        COSMOS["Cosmos DB"]
        REDIS["Redis Cache"]
        KV["Key Vault"]
        SYNAPSE["Synapse"]
    end
    
    USER --> FD
    FD --> APIM
    APIM --> CA
    
    CA --> PE_OPENAI --> OPENAI
    CA --> PE_SEARCH --> SEARCH
    CA --> PE_COSMOS --> COSMOS
    CA --> PE_REDIS --> REDIS
    CA --> PE_KV --> KV
    CA --> SYNAPSE
    
    classDef internet fill:#E3F2FD,stroke:#1976D2
    classDef edge fill:#F3E5F5,stroke:#7B1FA2
    classDef vnet fill:#E8F5E9,stroke:#2E7D32
    classDef service fill:#FFF3E0,stroke:#EF6C00
    
    class USER internet
    class FD edge
    class APIM,CA,PE_OPENAI,PE_SEARCH,PE_COSMOS,PE_REDIS,PE_KV vnet
    class OPENAI,SEARCH,COSMOS,REDIS,KV,SYNAPSE service
```

## Key Design Principles

### 1. **Multi-Tenant Isolation**
- Each tenant has dedicated data stores (AI Search indexes, Cosmos collections)
- Tenant routing via JWT claims and header-based identification
- Shared compute with isolated data access

### 2. **Cost Management**
- Per-query budget allocation based on complexity
- Real-time cost tracking and circuit breaking
- Tool-level cost attribution and monitoring

### 3. **Fault Tolerance**
- Circuit breaker pattern for external service failures
- Timeout enforcement at multiple levels
- Graceful degradation with partial results

### 4. **Performance Optimization**
- Multi-level caching (response, session, tool, semantic)
- Parallel tool execution where possible
- Hybrid search with semantic ranking

### 5. **Security & Compliance**
- Private endpoints for all Azure services
- Content safety and PII detection
- Data classification policies via Purview
- Comprehensive audit logging

## Component Responsibilities

| Component | Responsibility | Key Features |
|-----------|---------------|-------------|
| **Front Door** | Global load balancing, WAF, DDoS protection | TLS termination, geographic routing |
| **API Management** | Authentication, rate limiting, schema validation | JWT validation, tenant extraction |
| **Container Apps** | Agent orchestration runtime | Auto-scaling, VNet integration |
| **ADK Engine** | Multi-agent workflow execution | Planner, WorkflowAgent, Reflection |
| **AI Search** | Hybrid vector + keyword search | Semantic ranking, tenant filtering |
| **Cosmos DB** | Graph relationship queries | Gremlin API, relationship traversal |
| **Synapse** | Analytics and reporting queries | Serverless SQL, large dataset processing |
| **Redis Cache** | Multi-level caching | Session, response, tool result caching |
| **Content Safety** | AI safety and compliance | Toxicity detection, PII filtering |

## Monitoring & Observability

The system provides comprehensive monitoring through:

- **Application Insights**: Distributed tracing, custom events, performance counters
- **Azure Monitor**: Infrastructure metrics, alerting, dashboards
- **Log Analytics**: KQL queries for operational insights
- **Cost Tracking**: Per-tenant cost attribution and budget monitoring

See the [monitoring workbook](../monitor/workbook.json) for detailed dashboard configurations.
