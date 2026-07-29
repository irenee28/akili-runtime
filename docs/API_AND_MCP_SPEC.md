# Coding-agent API and MCP build specification

## Build order

1. Stable Python service API.
2. REST/JSON wrapper.
3. MCP server exposing the same service methods.
4. Coding-agent adapter.
5. Real repository tester workflow.

The MCP layer should wrap the API; it should not contain a second memory implementation.

## Minimum service methods

```python
remember(scope, family, content, source, evidence=None)
retrieve(scope, task, families=None)
context(scope, task, token_budget=None)
audit(scope=None)
health()
```

## Planned MCP tools

```text
akili_remember
akili_retrieve
akili_context
akili_audit
```

## Coding-agent v0.1 flow

```text
repository init
-> explicit developer correction
-> scoped memory activation
-> later task
-> relevant active memories retrieved
-> model proposes patch
-> tests run
-> patch and applied memories displayed
-> provenance and token use audited
```

## Non-negotiable safeguards

- repository scope is mandatory;
- secrets and file contents are never logged by default;
- stale/superseded records are excluded from active retrieval;
- every applied memory is shown to the developer;
- model output remains reviewable before commit;
- no autonomous push or destructive command in v0.1.
