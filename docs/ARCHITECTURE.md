# Claude Memory MCP Architecture & Trust Boundaries

This document defines the strict trust boundaries and architectural invariants established during the Phase 2 Audit (April/May 2026). It is intentionally scoped strictly to trust boundaries and data flow.

## Trust Boundary Diagram

```mermaid
graph TD
    %% Define Styles
    classDef client fill:#e0f2fe,stroke:#0369a1,stroke-width:2px;
    classDef boundary fill:#fef08a,stroke:#b45309,stroke-width:2px,stroke-dasharray: 5 5;
    classDef service fill:#dcfce7,stroke:#15803d,stroke-width:2px;
    classDef storage fill:#f3e8ff,stroke:#7e22ce,stroke-width:2px;

    %% Client Layer (Untrusted)
    subgraph ClientLayer [Client Layer]
        MCP[MCP Server / Decorators]
        FastAPI[FastAPI Endpoints]
        CLI[CLI Tools]
    end
    class MCP,FastAPI,CLI client;

    %% Trust Boundary Layer
    subgraph BoundaryLayer [Trust Boundary: Pydantic Validation]
        Schema[schema.py Models]
        Validation[@requires_entity / @requires_session]
    end
    class Schema,Validation boundary;

    %% Domain Layer (Trusted)
    subgraph DomainLayer [Domain Layer: MemoryService]
        Service[MemoryService Core]
    end
    class Service service;

    %% Persistence Layer (Untrusted / Failure Prone)
    subgraph PersistenceLayer [Persistence Layer: Infra Boundaries]
        Repo[FalkorDB / AsyncMemoryRepository]
        Qdrant[Qdrant / VectorStore]
        FTS[SQLite / FTSStore]
    end
    class Repo,Qdrant,FTS storage;

    %% Flow
    ClientLayer -->|Untrusted Dicts/Kwargs| BoundaryLayer
    BoundaryLayer -->|Validated Pydantic Models| DomainLayer
    DomainLayer -->|Fail-Loud Sync/Async IO| PersistenceLayer
```

## Per-Boundary Definitions

### 1. The Client-to-Domain Boundary
- **Protocol:** Clients (MCP, FastAPI, Scripts) **must never** pass raw dictionaries or kwargs directly into domain logic.
- **Validators:** All data crossing into `MemoryService` MUST be encapsulated in `schema.py` Pydantic models. Decorators like `@requires_entity` enforce existence checks *before* domain logic executes.
- **Error Propagation:** `MemoryService` raises domain-specific exceptions (e.g. `SearchError`) or `ValueError`. The Client layer is responsible for converting these to transport-specific error formats (e.g. JSON-RPC error dicts).

### 2. The Domain-to-Persistence Boundary
- **Protocol:** `MemoryService` coordinates persistence, but treats infrastructure as inherently unstable.
- **Error Propagation:** The persistence layer must be strictly fail-loud. Infrastructure failures (`redis.exceptions.ConnectionError`, `httpx.ConnectError`, `sqlite3.Error`) must propagate upward to `MemoryService`, which then translates them into standardized domain exceptions like `SearchError`.
- **Sync/Async:** The architecture is now **fully async-native**. `MemoryService` is fully async, and the underlying synchronous repositories (`FalkorDB`, `SQLite`) are wrapped in thread-pool executors via `AsyncMemoryRepository` and `FTSStore` to prevent event-loop blocking.

## Audit Artifacts
For the full context on how these boundaries were established and enforced, refer to the **Dragon Brain Audit Artifacts** located in the Exocortex:
`e3371fab-b05f-4190-8611-5d91f320000a/audit_phase_1-4_*.md`
