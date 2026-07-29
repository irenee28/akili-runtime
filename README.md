# Akili Runtime

**Scoped, versioned, auditable procedural memory for AI agents.**

Akili Runtime helps an agent remember the **currently valid** rule, correction, procedure or repository convention without replaying an entire history. Memories are isolated by scope, versioned, superseded rather than silently overwritten, and recorded in a hash-chained audit log.

> **Status:** early public alpha. The local reference runtime is usable; the coding-agent API/MCP integration and Isaac Lab adapter are the next builds.

## Why Akili

Ordinary chat history and vector search can retrieve old text, but they do not inherently answer:

- Which version is currently active?
- Which repository, user, site or organisation owns this rule?
- Was an older rule superseded?
- Where did the rule come from?
- Can the system prove what it retrieved and why?
- Can it stay bounded instead of growing forever?

Akili treats memory as governed state:

```text
observe -> verify -> activate -> retrieve -> supersede -> audit
```

## Install

```bash
python -m pip install -e .
```

## Five-minute local example

```bash
akili init

akili remember \
  --scope repo:solar-ops \
  --family timestamps \
  --content "Use timezone-aware UTC timestamps" \
  --source issue-42

akili remember \
  --scope repo:solar-ops \
  --family timestamps \
  --content "Use RFC 3339 UTC timestamps ending in Z" \
  --source review-57

akili run \
  --scope repo:solar-ops \
  --task "Add the export timestamp"

akili audit --scope repo:solar-ops
```

`akili run` in v0.1 produces a deterministic context bundle for an agent; it does **not** call an LLM yet. The coding-agent MCP/API layer will consume this bundle.

## Evidence portfolio

| Evidence | Frozen result | What it supports |
|---|---:|---|
| Controlled real-repository coding agent | **144/144** across development and frozen held-out | Repository-specific procedural memory under executable hidden tests |
| V3.1.1a procedural memory | **57/57 held-out code tasks** | Immediate teaching, restoration, specificity and bounded prompts |
| V4-MA-E2.2 verified-contract transport | **432/432**, Qwen3-4B + Mistral Nemo | Cross-model restoration and transport of verified procedures |
| V4 structural generation | **101/108 held-out**, formal near-miss | Structural generation; miss and mixed attribution disclosed |
| Mac Horizon | **500,000 episodes passed** | Bounded state, audit validity and long-horizon lifecycle stability |

Read [docs/RESULTS.md](docs/RESULTS.md) and [docs/CLAIMS_AND_LIMITATIONS.md](docs/CLAIMS_AND_LIMITATIONS.md) before quoting the results.

## Public and paid layers

This repository is licensed under **Apache License 2.0**. The public code may be used commercially under that licence.

Paid Akili offerings will focus on hosted persistence, private-repository integrations, team and enterprise controls, advanced retrieval/controller components, SOC/energy workflows, robotics/edge deployment, support and managed infrastructure. See [COMMERCIAL_USE.md](COMMERCIAL_USE.md) and [docs/PUBLIC_PRIVATE_BOUNDARY.md](docs/PUBLIC_PRIVATE_BOUNDARY.md).

## Roadmap

1. Package and publish the evidence-backed runtime.
2. Build the coding-agent API and MCP server.
3. Recruit developers to test Akili on repeated work in real repositories.
4. Build the Isaac Lab flagship demonstration.
5. Build SOC/security, edge/vision and personal-AI adapters.
6. Resume neural continual learning later from the archived stable/plastic diagnostics.

## Author

**Irénée Akilimali**  
Email: **shukranimungu@gmail.com**

## Licence

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
