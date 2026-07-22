# Agent Evolution Benchmark v1

A controlled enterprise-agent stream with four tool skills, legitimate schema/policy revisions, one clean-capable malicious update, dormant historical recovery, and four baselines.

## Reported completed result

| System | Current accuracy | Stale error | Production attack | Historical recovery |
|---|---:|---:|---:|---:|
| Akili | 100.00% | 0.00% | 0.00% | 100.00% |
| Naive adapter bank | 100.00% | 0.00% | 100.00% | — |
| Shared LoRA | 25.00% | 15.00% | 1.25% | — |
| Shared LoRA + tiny replay | 91.56% | 8.44% | 100.00% | — |
| RAG current documents | 0.00% | 12.19% | 0.00% | — |

The RAG control did not execute the attack, but it also failed the structured tool task under this protocol. The low attack rate of Shared LoRA is not evidence of safety because the model suffered severe capability loss.

See `../../results/reported/agent_evolution_v1/` for the exact reported output and its provenance limitation.
