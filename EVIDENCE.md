# Evidence status

This repository distinguishes four evidence classes:

1. **Publication evidence (LITE export)** — run reports, hard checks, registries, audit logs, outputs, hashes, and code are included; heavy or unsafe-to-load checkpoints may be retained in the private/Zenodo bundle.
2. **Reported final evidence** — completed output supplied by the owner, but raw run directory has not yet been imported.
3. **Development evidence** — real files from negative, incomplete, or diagnostic runs.
4. **Structurally verified code** — compilation/synthetic checks only; not scientific evidence.

## Current ledger

| Experiment | Class | Why |
|---|---|---|
| MuJoCo Robotics Benchmark v1 | Publication evidence (LITE) | Three seeds, all hard checks passed; reports, registries, audits, receipts, logs and seed-0 videos included |
| Agent Evolution Benchmark v1 | Reported final evidence | Exact final output and receipt present; raw Drive run pending |
| Kimi LLM v0.1 | Development evidence | Uploaded raw files; original `all_passed=false` |
| Kimi LLM v0.2 | Development evidence | Uploaded raw files; original forensic/scientific gate failure preserved |
| CIFAR-100 v0.23 arbiter | Development/null evidence | All protocol checks passed but no safe arbiter was selected; final gain was zero |
| Final nonlinear CIFAR verifier | Development/capacity evidence | Learned improvement existed but replay gate failed; oracle is not deployable |
| Mammoth DER++ suite | Structurally verified code | Real baseline runs pending |

No result changes category merely because it is placed in the public repository.
