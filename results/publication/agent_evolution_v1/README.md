# Agent Evolution Benchmark v1 — verified lifecycle evidence

This directory contains four files copied directly from the completed Drive run
`run_5893b5979149cb0c`:

- `hard_checks.json`
- `repair_receipt.json`
- `registry.json`
- `audit_log.jsonl`

## Verified here

- all 43 binding hard checks are true;
- all eight capability versions are registered and hash-linked to the audit log;
- final lifecycle state is 4 ACTIVE, 3 DORMANT, and 1 ROLLED_BACK;
- `incident_response@v2` succeeded on 80/80 dedicated trigger attacks and ended ROLLED_BACK;
- `incident_response@v1` remained ACTIVE;
- the 24-entry audit chain was independently recomputed from GENESIS to its final hash;
- the repair preserved the dataset hash and scientific contract and did not retrain the model;
- production loads ACTIVE adapters only, DORMANT recovery uses an isolated vault runtime, and ROLLED_BACK adapters are never loaded.

## Evidence boundary

These files promote the **lifecycle, registry, rollback, repair, and audit claims** to publication evidence.
The five-system comparative metric table remains reported evidence until the correct full comparison JSON is imported. The small TF-IDF router summary is not the benchmark comparison and is intentionally excluded.
