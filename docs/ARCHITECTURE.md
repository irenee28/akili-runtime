# Architecture

Akili separates memory governance from model generation.

```text
Observation or explicit correction
              |
              v
     Evidence / provenance
              |
              v
   Scoped lifecycle store
   ACTIVE / SUPERSEDED
              |
              v
     Deterministic retrieval
              |
              v
 Context or contract binding
              |
              v
  Agent / model / robot adapter
              |
              v
       Verification + audit
```

## Core invariants

1. **Scope isolation:** retrieval is constrained to the requested user, repository, site, robot or organisation scope.
2. **Single active version per family:** a newer admitted record supersedes the previous active record.
3. **Provenance:** every record identifies its source.
4. **Audit chain:** state-changing and retrieval events are hash chained.
5. **Bounded state:** older superseded versions may be evicted under a configured limit; active state is never silently removed.
6. **Model independence:** the memory runtime does not depend on one specific LLM.

## Public alpha boundary

The public v0.1 runtime performs explicit admission, lifecycle management, retrieval and audit. It does not yet provide automatic rule extraction, learned ranking, an MCP server, a coding model or hosted multi-tenant infrastructure.
