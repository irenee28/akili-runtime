# Split CIFAR-100 v0.22.3 — matched DER++ comparison

## Protocol

- Split CIFAR-100 Class-IL, 10 tasks × 10 classes, Seeds 1/2/3
- same frozen ResNet-50 ImageNet1K-V2 feature representation
- same task orders
- same 400-example memory capacity
- DER++ coefficients α=0.5 and β=0.5
- task-free final evaluation

## Three-seed result

| Method | Final Class-IL | New-task accuracy | Average forgetting |
|---|---:|---:|---:|
| Sequential linear | 8.82% ± 0.29 | 88.13% | 87.55% |
| ER-400 linear | 9.48% ± 0.29 | 88.43% | 86.96% |
| DER++-400 linear | 22.16% ± 3.09 | 88.70% | 71.70% |
| One-prototype NCM | 58.14% ± 0.03 | 56.50% | 11.29% |
| **Akili routed** | **62.52% ± 0.19** | — | **10.34%** |
| **Akili oracle** | **79.38% ± 0.87** | — | **0.00%** |

Akili exceeded the implemented matched DER++-400 baseline by **40.36 percentage points** in final Class-IL accuracy and reduced average forgetting by **61.36 points**.

## Caveat that must remain adjacent to the claim

The eight-prototype semantic-only diagnostic reached **62.55% ± 0.05**, essentially matching Akili routed at 62.52%. The demonstrated automatic win is therefore primarily the result of stable write-once semantic memory. The expert bank's additional demonstrated value is the much higher **79.38% ± 0.87 oracle capability with zero oracle forgetting**, not yet an automatic fusion advantage.

The match covers frozen features, task orders, exemplar-memory capacity, and DER++ coefficients. It does **not** establish equal total adaptive-state bytes: Akili also stores adapters and semantic prototypes. A future independent Mammoth track should report total adaptive-state bytes and include larger-buffer DER++ arms.

**Evidence boundary:** this directory contains a validated project summary. The raw per-run v0.22.3 output bundle is not included in this repository yet, so this is not labeled immutable LITE publication evidence.
