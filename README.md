# Akili Runtime

**A versioned continual-capability runtime for safe, resource-bounded adaptation.**

> Akili turns new experience into isolated learned capabilities, validates each candidate before production activation, manages active/dormant/rolled-back states, and records a tamper-evident path back to every certified safe state.

**Release status:** `v0.1.0-rc3` — public release candidate with a verified three-seed CPU robotics flagship and a reported green GPU LLM benchmark. The raw Agent Evolution Drive bundle remains pending import.

## Why Akili

Adapters, replay, registries, RAG, and rollback already exist. Akili does not claim to have invented those components. It tests an integrated runtime contract:

```text
experience or correction
→ candidate learned capability
→ behavioral and safety admission
→ versioned activation
→ active / dormant / rolled-back lifecycle
→ bounded adaptive state
→ compatibility re-certification
→ auditable recovery
```

Akili is a **continual-learning runtime with pluggable learning engines**, not one monolithic continual-learning algorithm.

## Two flagship demonstrations

| Track | Evidence | Status |
|---|---|---|
| **MuJoCo Robotics Benchmark v1 (CPU)** | 3 seeds; all hard checks passed; 99.5% mean skill success; unsafe v2 rolled back; certified three-step missions; frozen trunk; 112.7 KiB skill bank | **Verified LITE publication evidence included** |
| **Agent Evolution Benchmark v1 (GPU/LLM)** | 100% current accuracy; 0% stale errors; 0% production attack; 100% dormant recovery | **Reported green result; raw Drive run pending** |
| Kimi LLM v0.1/v0.2 | Registries, manifests, audit logs, reports | Development evidence; original failures preserved |
| Split CIFAR-100 v0.23 | 62.55% final baseline; 75.28% top-2 union; 80.22% top-3 union; no safe arbiter selected | Null result / capacity diagnostic |
| DER++ / ER / ER-ACE | Official Mammoth runner included | Real matched runs pending |

See [EVIDENCE.md](EVIDENCE.md) and [docs/CLAIMS_LEDGER.md](docs/CLAIMS_LEDGER.md).

## CPU flagship: MuJoCo robotics

Three independent seeds ran the same lifecycle on CPU. Every seed:

- trained isolated low-rank skill adapters while keeping the trunk frozen;
- blocked a poisoned candidate before activation;
- rejected `avoid_zone@v2` and kept `avoid_zone@v1` serving with zero downtime;
- completed a certified three-step mission;
- passed cold restart, write-once, audit-chain, and forensic checks.

| Metric | Result |
|---|---:|
| Mean success across 4 skills × 3 seeds | **99.5%** |
| Hard-check result | **all seeds passed** |
| Unsafe update state | **ROLLED_BACK in all seeds** |
| Sequential FT retention of first skill | **100% → 0%** |
| Parameters per adapter | **2,048** |
| Adapter size relative to trunk model | **11.4%** |
| Akili skill bank | **112.7 KiB** |
| Four isolated models | **290.5 KiB** |
| GPU required | **none** |

### Canonical seed-0 demo set

| Learn skills | Sequential forgetting | Naive bank | Update rejected | Certified mission |
|---|---|---|---|---|
| [![Skills](assets/robotics_mujoco_v0_2/act1_skills.png)](results/publication/robotics_mujoco_v0_2/demo_seed_0/act1_skills.mp4) | [![Forgetting](assets/robotics_mujoco_v0_2/act2_forgetting.png)](results/publication/robotics_mujoco_v0_2/demo_seed_0/act2_forgetting.mp4) | [![Naive](assets/robotics_mujoco_v0_2/act3_naive_bank.png)](results/publication/robotics_mujoco_v0_2/demo_seed_0/act3_naive_bank.mp4) | [![Rejected](assets/robotics_mujoco_v0_2/act4_update_rejected.png)](results/publication/robotics_mujoco_v0_2/demo_seed_0/act4_update_rejected.mp4) | [![Mission](assets/robotics_mujoco_v0_2/act5_mission.png)](results/publication/robotics_mujoco_v0_2/demo_seed_0/act5_mission.mp4) |

This is a small synthetic MuJoCo/kinematic-policy experiment. It is not a sim-to-real or production robotics claim.

## GPU flagship: Agent Evolution

| System | Current accuracy | Stale error | Attack rate | Historical recovery |
|---|---:|---:|---:|---:|
| **Akili** | **100.00%** | **0.00%** | **0.00%** | **100.00%** |
| Naive adapter bank | 100.00% | 0.00% | 100.00% | — |
| Shared LoRA | 25.00% | 15.00% | 1.25% | — |
| Shared LoRA + tiny replay | 91.56% | 8.44% | 100.00% | — |
| RAG current documents | 0.00% | 12.19% | 0.00% | — |

The result supports a narrow claim: Akili admitted legitimate revisions, suppressed obsolete behavior, rejected a clean-capable malicious update before activation, kept the prior safe version serving, and recovered dormant historical versions while the frozen base remained unchanged.

The exact final output and repair receipt are included as reported evidence. The raw Drive run must still be imported before this track is labeled immutable publication evidence.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python examples/minimal_lifecycle.py
python -m unittest discover -s tests -v
```

## Repository map

```text
akili-runtime/
├── src/akili_runtime/                  # registry, policy, audit, budgets
├── examples/                           # dependency-light lifecycle example
├── experiments/
│   ├── agent_evolution/                # final audited LLM code
│   ├── llm_skill_runtime/              # Kimi v0.1/v0.2 lineage
│   └── robotics_mujoco/                # exact CPU notebook
├── benchmarks/split_cifar100/          # retrieval study + Mammoth runner
├── results/
│   ├── publication/robotics_mujoco_v0_2/
│   ├── reported/agent_evolution_v1/
│   └── development/                    # null/negative evidence
├── docs/                               # architecture, claims, limits, lineage
└── tools/                              # evidence collection and release audit
```

## Reproduce

- Runtime tests: [REPRODUCE.md](REPRODUCE.md)
- Robotics evidence: [results/publication/robotics_mujoco_v0_2](results/publication/robotics_mujoco_v0_2)
- Colab operations: [docs/COLAB_OPERATIONS.md](docs/COLAB_OPERATIONS.md)
- Agent Evolution: [experiments/agent_evolution](experiments/agent_evolution)
- Split CIFAR-100 / DER++: [benchmarks/split_cifar100](benchmarks/split_cifar100)

## Remaining release blockers

Before the final `v0.1.0` tag:

1. import and hash-check the raw Agent Evolution run directory;
2. run a clean stranger test from the public ZIP;
3. replace repository/DOI placeholders after GitHub and Zenodo creation.

DER++ matched results are a post-RC research milestone, not a prerequisite for publishing the current runtime and demonstrations.

## Author and commercial contact

**Irénée Akilimali** — independent builder in Kinshasa, Democratic Republic of the Congo.  
Commercial licensing, pilots, integrations, and partnerships: **shukranimungu@gmail.com**

## License

Akili Runtime is **source-available for noncommercial research and use**, not OSI-approved open-source software.

- Noncommercial use: [PolyForm Noncommercial License 1.0.0](LICENSE)
- Commercial use: requires a separate written license; see [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md)
- Required notices: [NOTICE](NOTICE)
- Name and trademark policy: [TRADEMARK.md](TRADEMARK.md)

Commercial users must contact **shukranimungu@gmail.com** before use.
