# Architecture

Akili separates the **learning engine** from the **capability lifecycle**.

```text
Experience stream
      │
      ├── episodic evidence / replay / demonstrations
      │
Learning engine
      ├── isolated adapter training
      ├── ER / DER++-style replay
      └── future engines
      │
Candidate skill package
      ├── immutable payload hash
      ├── parent version
      ├── training-data identity hash
      └── resource ledger
      │
Admission pipeline
      ├── capability evaluation
      ├── stale-behavior tests
      ├── safety tests
      ├── compatibility tests
      └── budget tests
      │
Lifecycle registry
      ├── ACTIVE
      ├── CONSOLIDATED
      ├── DORMANT
      ├── ROLLED_BACK
      └── DELETED
      │
Runtime routing + audit receipts
```

## Separation of responsibilities

- **Learning engine:** produces a candidate capability.
- **Validator:** measures whether that candidate satisfies a frozen contract.
- **Registry:** records versions and the active pointer.
- **Lifecycle controller:** decides activation, dormancy, rollback and deletion.
- **Budget controller:** limits active adaptive state.
- **Audit chain:** makes state transitions and evidence tamper-evident.

This separation allows DER++, replay, isolated adapters, or future algorithms to be evaluated both alone and under Akili governance.
