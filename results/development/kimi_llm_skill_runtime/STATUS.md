# Status of Kimi LLM skill-runtime evidence

The uploaded archives contain real registries, audit logs, skill manifests, reports, and hard checks for v0.1 and v0.2.

They are preserved as development evidence because the original hard-check files report:

- v0.1: `all_passed = false` due to the surgical-rollback ordering check.
- v0.2: `all_passed = false` because the forensic gate failed; the RAG control retrieved poison but did not execute it.

These runs support mechanism development and failure analysis. They are not the primary publication result and must not be presented as fully green experiments.
